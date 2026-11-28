"""Diagnostica con el Agente de Pruebas los casos fallidos de una ejecución.

Lo usa el workflow ``pruebas-e2e.yml`` cuando hay fallos (dentro del contenedor de la aplicación, donde
corre OpenCode):

    python -m agentes.pruebas.diagnosticar < resumen.json > diagnostico.json

Entrada: el ``resumen.json`` del reportero de Playwright. Salida (solo JSON por la salida estándar; los
registros van a la salida de error):

    {"diagnosticos": {"<id del caso>": {...}}, "omitidos": 2, "consumo": {"llamadas": 7, "tokens_total": ..., "costo_usd": ...}}

Un mismo caso que falla en web, tablet y móvil se diagnostica una vez. Como máximo se diagnostican
``PROBADOR_MAXIMO_CASO`` casos (3 por defecto) para cuidar la cuota del modelo.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from typing import Any

from pydantic import ValidationError

from agentes.equipo.probador.probador_service import CasoFallido, ProbadorService
from agentes.metricas.registro_consumo import (
    MODO_PRUEBA, AcumuladorConsumo, agregar_registrador, contexto_consumo, quitar_registrador,
)
from agentes.pruebas.navegador_playwright_service import NavegadorPlaywrightService

logger = logging.getLogger("agentes.pruebas.diagnosticar")
_ORDEN_DISPOSITIVO = {"web": 0, "tablet": 1, "movil": 2}


def _entero(nombre: str, defecto: int, maximo: int) -> int:
    try:
        return max(1, min(int(os.environ.get(nombre, defecto)), maximo))
    except ValueError:
        logger.warning("valor_invalido", extra={"event": "valor_invalido", "variable": nombre})
        return defecto


def agrupar_fallidos(resumen: dict[str, Any], maximo: int) -> tuple[list[tuple[CasoFallido, list[str]]], int]:
    """Agrupa por título (el mismo caso en varios dispositivos) y elige primero la versión web."""
    grupo: dict[str, list[CasoFallido]] = {}
    for crudo in resumen.get("casos") or []:
        if not isinstance(crudo, dict) or crudo.get("estado") != "fallido":
            continue
        try:
            caso = CasoFallido.model_validate(crudo)
        except ValidationError:
            logger.warning("caso_invalido", extra={"event": "caso_invalido"})
            continue
        grupo.setdefault(caso.titulo, []).append(caso)
    lista = [
        (sorted(casos, key=lambda c: _ORDEN_DISPOSITIVO.get(c.dispositivo, 9))[0], [c.id for c in casos])
        for casos in grupo.values()
    ]
    return lista[:maximo], max(0, len(lista) - maximo)


async def diagnosticar(resumen: dict[str, Any]) -> dict[str, Any]:
    base_url = os.environ.get("BASE_URL_DIAGNOSTICO", "http://aplicacion:10000").strip()
    url_mcp = os.environ.get("NAVEGADOR_MCP_URL", "http://navegador:8931/mcp").strip()
    seleccion, omitidos = agrupar_fallidos(resumen, _entero("PROBADOR_MAXIMO_CASO", 3, 10))
    servicio = ProbadorService(lambda: NavegadorPlaywrightService(url_mcp, base_url), base_url)
    salida: dict[str, Any] = {"diagnosticos": {}, "omitidos": omitidos}
    # El consumo del modelo se suma en memoria: este proceso corre en GitHub y su base no se conserva.
    acumulador = AcumuladorConsumo()
    agregar_registrador(acumulador)
    try:
        with contexto_consumo(modo=MODO_PRUEBA, titulo="Diagnóstico de pruebas"):
            await _diagnosticar_seleccion(servicio, seleccion, salida)
    finally:
        quitar_registrador(acumulador)
    salida["consumo"] = acumulador.resumen()
    return salida


async def _diagnosticar_seleccion(servicio: ProbadorService, seleccion: list[tuple[CasoFallido, list[str]]],
                                  salida: dict[str, Any]) -> None:
    for caso, lista_id in seleccion:
        try:
            diagnostico, exploracion = await servicio.diagnosticar(caso)
            dato = {"estado": "listo", **diagnostico.model_dump(), "exploracion": exploracion.resumen()}
        except Exception as exc:
            # Un caso sin diagnóstico no detiene a los demás; se informa sin el contenido del modelo.
            logger.warning("diagnostico_fallido", extra={"event": "diagnostico_fallido", "error": type(exc).__name__})
            dato = {"estado": "sin_diagnostico", "motivo": f"El Agente de Pruebas no pudo diagnosticar ({type(exc).__name__})."}
        for caso_id in lista_id:
            salida["diagnosticos"][caso_id] = dato


def main() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    try:
        resumen = json.load(sys.stdin)
    except ValueError:
        logger.error("resumen_invalido", extra={"event": "resumen_invalido"})
        resumen = {}
    json.dump(asyncio.run(diagnosticar(resumen)), sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
