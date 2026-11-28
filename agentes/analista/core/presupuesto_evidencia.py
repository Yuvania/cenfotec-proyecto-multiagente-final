"""Presupuesto de tokens de evidencia por agente.

Cada herramienta MCP ya limita su propio resultado, pero un agente junta varias rondas y varias consultas: sin un
tope total, el mensaje final puede crecer sin límite (más costo, más demora, peor calidad y, al pasar la ventana
del modelo, un paso que falla). Antes de enviarle la evidencia al modelo se aplica este presupuesto:

1. Se quitan los resultados repetidos: la misma consulta a la misma herramienta y los elementos que ya
   aparecieron en otra consulta (por su ``id`` o ``source_id``).
2. Si todavía se pasa del presupuesto, se quita el último elemento (el menos relevante: las herramientas los
   devuelven ordenados) de la lista más larga, hasta que alcance. Así se recorta parejo y no se pierde una
   herramienta entera.
3. Si un solo texto es enorme, se recorta su contenido y queda la marca «recortado por presupuesto».

Lo recortado queda marcado en la evidencia (``recortado`` y ``omitidos``) para que el agente sepa que hay más.
Los tokens se estiman en 4 caracteres por token (suficiente para un tope; el costo real lo informa OpenCode).

El presupuesto se ajusta con ``PRESUPUESTO_EVIDENCIA_TOKENS`` (12 000 por defecto).
"""
from __future__ import annotations

import copy
import json
import logging
import math
import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

PRESUPUESTO_PREDETERMINADO = 12_000
PRESUPUESTO_MINIMO = 1_000
CARACTER_POR_TOKEN = 4
MINIMO_TEXTO = 1_500  # un texto no se recorta por debajo de esto mientras haya otra cosa que quitar
MARCA_RECORTE = "\n… [recortado por presupuesto]"
_CLAVE_ID = ("id", "source_id", "source_ref")


@dataclass(frozen=True, slots=True)
class AjusteEvidencia:
    """Lo que hizo el presupuesto, sin contenido (para el registro y las limitaciones)."""

    presupuesto: int
    tokens_antes: int
    tokens_despues: int
    repetidos: int = 0
    omitidos: int = 0
    textos_recortados: int = 0

    @property
    def recortado(self) -> bool:
        return bool(self.repetidos or self.omitidos or self.textos_recortados)

    def limitacion(self) -> str | None:
        if not (self.omitidos or self.textos_recortados):
            return None
        return (f"La evidencia superó el presupuesto de {self.presupuesto:,} tokens: se dejaron los resultados más "
                "relevantes y lo recortado quedó marcado.").replace(",", ".")


def presupuesto_configurado() -> int:
    valor = os.environ.get("PRESUPUESTO_EVIDENCIA_TOKENS", "").strip()
    if not valor:
        return PRESUPUESTO_PREDETERMINADO
    try:
        return max(PRESUPUESTO_MINIMO, int(valor))
    except ValueError:
        logger.warning("presupuesto_invalido", extra={"event": "presupuesto_invalido"})
        return PRESUPUESTO_PREDETERMINADO


def estimar_token(valor: Any) -> int:
    texto = valor if isinstance(valor, str) else json.dumps(valor, ensure_ascii=False, separators=(",", ":"), default=str)
    return math.ceil(len(texto) / CARACTER_POR_TOKEN)


def _firma(elemento: Any) -> str:
    if isinstance(elemento, Mapping):
        for clave in _CLAVE_ID:
            if isinstance(elemento.get(clave), str) and elemento[clave]:
                return f"{clave}:{elemento[clave]}"
    return json.dumps(elemento, ensure_ascii=False, sort_keys=True, default=str)


def _listas(datos: Any) -> list[tuple[str, list[Any]]]:
    """Las listas de resultados de una herramienta (definiciones, historias, fuentes…), sin las citas."""
    if not isinstance(datos, dict):
        return []
    return [(clave, valor) for clave, valor in datos.items() if isinstance(valor, list) and clave != "sources" and valor]


def _textos_largos(valor: Any, ruta: tuple = ()) -> list[tuple[tuple, str]]:
    """Rutas a los textos más largos dentro de un valor (para recortar contenido enorme)."""
    if isinstance(valor, str):
        return [(ruta, valor)] if len(valor) > MINIMO_TEXTO else []
    if isinstance(valor, Mapping):
        return [item for clave, hijo in valor.items() for item in _textos_largos(hijo, (*ruta, clave))]
    if isinstance(valor, list):
        return [item for indice, hijo in enumerate(valor) for item in _textos_largos(hijo, (*ruta, indice))]
    return []


def _asignar(raiz: Any, ruta: tuple, valor: Any) -> None:
    destino = raiz
    for paso in ruta[:-1]:
        destino = destino[paso]
    destino[ruta[-1]] = valor


def _recortar_texto(lista: list[Any], total: int, presupuesto: int) -> tuple[int, int]:
    """Recorta el texto más largo de la lista hasta alcanzar el presupuesto. Devuelve (total, textos recortados)."""
    recortados: set[tuple] = set()
    while total > presupuesto:
        candidato = max(
            ((indice, ruta, texto) for indice, elemento in enumerate(lista) for ruta, texto in _textos_largos(elemento)),
            key=lambda item: len(item[2]), default=None,
        )
        if candidato is None:
            break
        indice, ruta, texto = candidato
        sobra = (total - presupuesto) * CARACTER_POR_TOKEN
        nuevo_largo = max(MINIMO_TEXTO, len(texto) - sobra - len(MARCA_RECORTE))
        if nuevo_largo >= len(texto) - len(MARCA_RECORTE):
            break
        if ruta:
            _asignar(lista[indice], ruta, texto[:nuevo_largo] + MARCA_RECORTE)
        else:
            lista[indice] = texto[:nuevo_largo] + MARCA_RECORTE
        if isinstance(lista[indice], dict):
            lista[indice]["recortado"] = True
        recortados.add((indice, ruta))
        total = estimar_token(lista)
    return total, len(recortados)


def ajustar_observacion(lista_observacion: list[dict[str, Any]], presupuesto: int | None = None,
                        *, agente: str = "") -> tuple[list[dict[str, Any]], AjusteEvidencia]:
    """Aplica el presupuesto a la evidencia del ciclo MCP (``ResultadoCiclo.observacion``). No cambia la original."""
    presupuesto = presupuesto or presupuesto_configurado()
    antes = estimar_token(lista_observacion)
    lista = copy.deepcopy(lista_observacion)

    # 1. Repetidos: la misma consulta a la misma herramienta y los elementos ya vistos en otra consulta.
    repetidos = 0
    consulta_vista: set[tuple[str, str]] = set()
    elemento_visto: set[tuple[str, str]] = set()
    sin_repetir: list[dict[str, Any]] = []
    for observacion in lista:
        clave = (str(observacion.get("nombre")), str(observacion.get("consulta")))
        if clave in consulta_vista:
            repetidos += 1
            continue
        consulta_vista.add(clave)
        for nombre_lista, elementos in _listas(observacion.get("datos")):
            unicos = []
            for elemento in elementos:
                firma = (nombre_lista, _firma(elemento))
                if firma in elemento_visto:
                    repetidos += 1
                    continue
                elemento_visto.add(firma)
                unicos.append(elemento)
            observacion["datos"][nombre_lista] = unicos
        sin_repetir.append(observacion)
    lista = sin_repetir

    # 2. Si se pasa, se quita el último elemento de la lista más larga (el menos relevante de esa herramienta).
    total = estimar_token(lista)
    omitidos = 0
    while total > presupuesto:
        candidato = max(
            ((observacion, nombre_lista) for observacion in lista
             for nombre_lista, elementos in _listas(observacion.get("datos")) if len(elementos) > 1),
            key=lambda item: estimar_token(item[0]["datos"][item[1]]), default=None,
        )
        if candidato is None:
            break
        observacion, nombre_lista = candidato
        observacion["datos"][nombre_lista].pop()
        observacion["recortado"] = True
        observacion["omitidos"] = observacion.get("omitidos", 0) + 1
        omitidos += 1
        total = estimar_token(lista)

    # 3. Si un solo texto es enorme, se recorta su contenido.
    total, textos = _recortar_texto(lista, total, presupuesto)

    ajuste = AjusteEvidencia(presupuesto, antes, total, repetidos, omitidos, textos)
    if ajuste.recortado:
        logger.info("evidencia_ajustada", extra={
            "event": "evidencia_ajustada", "agente": agente, "tokens_antes": antes, "tokens_despues": total,
            "repetidos": repetidos, "omitidos": omitidos, "textos_recortados": textos,
        })
    return lista, ajuste


def ajustar_fuente(lista_fuente: list[dict[str, Any]], presupuesto: int | None = None,
                   *, agente: str = "", reservado: int = 0) -> tuple[list[dict[str, Any]], AjusteEvidencia]:
    """Presupuesto para una lista de fuentes citables (el Asesor Técnico). Mantiene el orden: primero lo que el
    agente leyó o encontró primero; recorta los textos más largos y, si aún no alcanza, quita las últimas fuentes.

    ``reservado``: tokens que ya ocupa otra evidencia del mismo mensaje (por ejemplo, las HU similares).
    """
    presupuesto = max(PRESUPUESTO_MINIMO, (presupuesto or presupuesto_configurado()) - reservado)
    antes = estimar_token(lista_fuente)
    lista = copy.deepcopy(lista_fuente)

    repetidos = 0
    vista: set[str] = set()
    sin_repetir = []
    for fuente in lista:
        firma = _firma(fuente)
        if firma in vista:
            repetidos += 1
            continue
        vista.add(firma)
        sin_repetir.append(fuente)
    lista = sin_repetir

    total, textos = _recortar_texto(lista, estimar_token(lista), presupuesto)
    omitidos = 0
    while total > presupuesto and len(lista) > 1:
        lista.pop()
        omitidos += 1
        total = estimar_token(lista)

    ajuste = AjusteEvidencia(presupuesto, antes, total, repetidos, omitidos, textos)
    if ajuste.recortado:
        logger.info("evidencia_ajustada", extra={
            "event": "evidencia_ajustada", "agente": agente, "tokens_antes": antes, "tokens_despues": total,
            "repetidos": repetidos, "omitidos": omitidos, "textos_recortados": textos,
        })
    return lista, ajuste
