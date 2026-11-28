"""Observabilidad: latencia por paso, alertas y estado de cada traza (cada creación o cambio de una HU).

Es una pantalla aparte de «Consumo del modelo»: el consumo responde «¿cuánto gastamos?», la observabilidad
responde «¿está funcionando bien ahora?». Los datos salen de las mismas tablas (turnos de los agentes,
consultas MCP y consumo del modelo); no se guarda contenido, solo tiempos, estados y cantidades.

Umbrales de alerta aprobados (``UMBRAL``):

1. Costo de una historia mayor a 2 veces el promedio de los últimos 30 días.
2. Un paso (el turno de un agente) que tardó más de 3 minutos.
3. Un agente con más de 10 % de turnos fallidos en las últimas 24 horas (con al menos 5 turnos).
4. Un error de cuota del modelo en la última hora.
5. Llamadas con costo estimado o sin precio (el costo no es exacto).
6. El tope de gasto: el mes pasó el 80 % (o el 100 %) o una historia se detuvo por su tope.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from agentes.metricas.metricas_service import LISTA_PERIODO, NOMBRE_AGENTE, PeriodoInvalidoError
from agentes.metricas.presupuesto_service import PROPORCION_ADVERTENCIA, PresupuestoService
from agentes.metricas.repositorio_consumo import RepositorioConsumo, desde_dias

UMBRAL = {
    "costo_multiplo": 2.0,
    "costo_dias_promedio": 30,
    "costo_flujo_minimo": 3,  # con menos historias el promedio no dice nada
    "paso_ms": 3 * 60 * 1000,
    "fallo_porcentaje": 10.0,
    "fallo_horas": 24,
    "fallo_turno_minimo": 5,
    "cuota_horas": 1,
}
CODIGO_CUOTA = "OPENCODE_RATE_LIMITED"
CODIGO_PRESUPUESTO = "PRESUPUESTO_AGOTADO"
NIVEL_CRITICA = "critica"
NIVEL_ADVERTENCIA = "advertencia"

ESTADO_OK = "ok"
ESTADO_REINTENTO = "con_reintento"
ESTADO_FALLO = "fallo"
ESTADO_DETENIDA = "detenida"

NOMBRE_HERRAMIENTA = {
    "buscar_hu_similares": "HU similares",
    "consultar_glosario": "Glosario",
    "consultar_estandares": "Estándares",
    "consultar_lecciones": "Lecciones aprendidas",
    "aplicar_checklist_vacios": "Checklist de vacíos",
    "consultar_codigo_demo": "Código",
    "buscar_referencias_codigo": "Referencias en el código",
    "leer_archivo_codigo": "Archivo de código",
}
_DIAS_POR_PERIODO = {periodo["codigo"]: periodo["dias"] for periodo in LISTA_PERIODO}


def percentil(lista_valor: list[int], porcentaje: float) -> int:
    """Percentil por rango más cercano (p50 = mediana, p95 = el 95 % tardó esto o menos)."""
    if not lista_valor:
        return 0
    ordenada = sorted(lista_valor)
    posicion = max(1, math.ceil(porcentaje / 100 * len(ordenada)))
    return int(ordenada[posicion - 1])


def _latencia(lista_valor: list[int]) -> dict[str, int]:
    return {
        "cantidad": len(lista_valor),
        "p50_ms": percentil(lista_valor, 50),
        "p95_ms": percentil(lista_valor, 95),
        "maxima_ms": max(lista_valor) if lista_valor else 0,
    }


def _hace(**delta: float) -> str:
    return (datetime.now(UTC) - timedelta(**delta)).isoformat(timespec="milliseconds")


def _nombre(agente: str) -> str:
    return NOMBRE_AGENTE.get(agente, agente)


class ObservabilidadService:
    def __init__(self, repositorio: RepositorioConsumo, presupuesto: PresupuestoService) -> None:
        self.repositorio = repositorio
        self.presupuesto = presupuesto

    @staticmethod
    def _desde(periodo: str) -> str | None:
        if periodo not in _DIAS_POR_PERIODO:
            raise PeriodoInvalidoError("El periodo no es válido.")
        return desde_dias(_DIAS_POR_PERIODO[periodo])

    def panel(self, periodo: str = "7") -> dict[str, Any]:
        desde = self._desde(periodo)
        # Las alertas miran ventanas fijas (24 h, 1 h): se leen los turnos desde lo más antiguo que se necesite.
        desde_turno = min(desde, _hace(hours=UMBRAL["fallo_horas"])) if desde else None
        lista_turno = self.repositorio.lista_turno(desde=desde_turno)
        turno_periodo = [turno for turno in lista_turno if not desde or turno["creado_en"] >= desde]
        lista_herramienta = self.repositorio.lista_herramienta(desde=desde)
        costo_flujo = self.repositorio.costo_por_flujo(desde=desde)
        presupuesto = self.presupuesto.estado()
        return {
            "periodo": periodo,
            "lista_periodo": [{"codigo": p["codigo"], "nombre": p["nombre"]} for p in LISTA_PERIODO],
            "umbral": UMBRAL,
            "presupuesto": presupuesto,
            "alerta": self._alertas(lista_turno, turno_periodo, costo_flujo, presupuesto, desde),
            "latencia_agente": self._latencia_agente(turno_periodo),
            "latencia_herramienta": self._latencia_herramienta(lista_herramienta),
            "traza": self._trazas(turno_periodo, lista_herramienta, costo_flujo),
        }

    # --- Latencia ------------------------------------------------------------------------------------
    @staticmethod
    def _latencia_agente(lista_turno: list[dict[str, Any]]) -> list[dict[str, Any]]:
        por_agente: dict[str, list[int]] = defaultdict(list)
        lento: dict[str, int] = defaultdict(int)
        for turno in lista_turno:
            por_agente[turno["agente"]].append(int(turno["duracion_ms"] or 0))
            if (turno["duracion_ms"] or 0) > UMBRAL["paso_ms"]:
                lento[turno["agente"]] += 1
        lista = [
            {"agente": agente, "nombre": _nombre(agente), **_latencia(valores), "lentos": lento[agente]}
            for agente, valores in por_agente.items()
        ]
        return sorted(lista, key=lambda item: item["p95_ms"], reverse=True)

    @staticmethod
    def _latencia_herramienta(lista_herramienta: list[dict[str, Any]]) -> list[dict[str, Any]]:
        por_herramienta: dict[str, list[int]] = defaultdict(list)
        fallida: dict[str, int] = defaultdict(int)
        for llamada in lista_herramienta:
            por_herramienta[llamada["herramienta"]].append(int(llamada["duracion_ms"] or 0))
            if llamada["estado"] != "ok":
                fallida[llamada["herramienta"]] += 1
        lista = [
            {"herramienta": nombre, "nombre": NOMBRE_HERRAMIENTA.get(nombre, nombre), **_latencia(valores),
             "fallidas": fallida[nombre]}
            for nombre, valores in por_herramienta.items()
        ]
        return sorted(lista, key=lambda item: item["p95_ms"], reverse=True)

    # --- Alertas -------------------------------------------------------------------------------------
    def _alertas(self, lista_turno: list[dict[str, Any]], turno_periodo: list[dict[str, Any]],
                 costo_flujo: dict[str, dict[str, Any]], presupuesto: dict[str, Any],
                 desde: str | None) -> list[dict[str, Any]]:
        lista: list[dict[str, Any]] = []

        # 6. Tope de gasto.
        porcentaje = presupuesto.get("porcentaje_mes")
        if porcentaje is not None and porcentaje >= 100:
            lista.append({"id": "presupuesto_mes", "nivel": NIVEL_CRITICA, "titulo": "Se alcanzó el tope de gasto del mes",
                          "detalle": "Los agentes no hacen llamadas al modelo hasta el próximo mes o hasta que se suba el tope."})
        elif porcentaje is not None and porcentaje >= 100 * PROPORCION_ADVERTENCIA:
            lista.append({"id": "presupuesto_mes", "nivel": NIVEL_ADVERTENCIA, "titulo": f"El mes lleva el {porcentaje:.0f} % del tope de gasto",
                          "detalle": "Al llegar al 100 % los agentes se detienen y las historias pasan a modo manual."})
        detenida = {turno["workflow_id"] for turno in turno_periodo if turno["codigo_error"] == CODIGO_PRESUPUESTO and turno["workflow_id"]}
        if detenida:
            lista.append({"id": "presupuesto_historia", "nivel": NIVEL_CRITICA,
                          "titulo": f"{len(detenida)} historia(s) detenida(s) por el tope de gasto",
                          "detalle": "Una persona debe terminarlas en modo manual o revisar por qué gastaron tanto.",
                          "lista": self._titulos(detenida, costo_flujo)})

        # 4. Cuota agotada en la última hora.
        hace_hora = _hace(hours=UMBRAL["cuota_horas"])
        cuota = [turno for turno in lista_turno if turno["codigo_error"] == CODIGO_CUOTA and turno["creado_en"] >= hace_hora]
        if cuota:
            lista.append({"id": "cuota", "nivel": NIVEL_CRITICA, "titulo": "Se agotó la cuota del modelo en la última hora",
                          "detalle": f"{len(cuota)} paso(s) no pudieron terminar. Revise el uso del plan en la consola de OpenCode."})

        # 3. Tasa de fallo por agente en 24 h.
        hace_dia = _hace(hours=UMBRAL["fallo_horas"])
        conteo: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for turno in lista_turno:
            if turno["creado_en"] >= hace_dia:
                conteo[turno["agente"]][0] += 1
                conteo[turno["agente"]][1] += 0 if turno["exitoso"] else 1
        for agente, (total, fallido) in sorted(conteo.items()):
            tasa = 100 * fallido / total if total else 0
            if total >= UMBRAL["fallo_turno_minimo"] and tasa > UMBRAL["fallo_porcentaje"]:
                lista.append({"id": f"fallo_{agente}", "nivel": NIVEL_CRITICA,
                              "titulo": f"{_nombre(agente)} falla en el {tasa:.0f} % de sus turnos",
                              "detalle": f"{fallido} de {total} turnos fallaron en las últimas 24 horas (umbral: 10 %)."})

        # 2. Pasos lentos.
        lento = [turno for turno in turno_periodo if (turno["duracion_ms"] or 0) > UMBRAL["paso_ms"]]
        if lento:
            nombres = sorted({_nombre(turno["agente"]) for turno in lento})
            lista.append({"id": "paso_lento", "nivel": NIVEL_ADVERTENCIA,
                          "titulo": f"{len(lento)} paso(s) tardaron más de 3 minutos",
                          "detalle": "Agentes: " + ", ".join(nombres) + ".",
                          "lista": self._titulos({turno["workflow_id"] for turno in lento if turno["workflow_id"]}, costo_flujo)})

        # 1. Historias que costaron más del doble del promedio de 30 días.
        promedio_base = self.repositorio.costo_por_flujo(desde=desde_dias(UMBRAL["costo_dias_promedio"]))
        lista_costo = [dato["costo_usd"] for dato in promedio_base.values()]
        if len(lista_costo) >= UMBRAL["costo_flujo_minimo"]:
            promedio = sum(lista_costo) / len(lista_costo)
            caro = {flujo for flujo, dato in costo_flujo.items() if promedio > 0 and dato["costo_usd"] > UMBRAL["costo_multiplo"] * promedio}
            if caro:
                lista.append({"id": "costo_alto", "nivel": NIVEL_ADVERTENCIA,
                              "titulo": f"{len(caro)} historia(s) costaron más del doble del promedio",
                              "detalle": f"Promedio de los últimos 30 días: US${promedio:.4f} por historia.",
                              "lista": self._titulos(caro, costo_flujo)})

        # 5. Costo no exacto.
        inexacto = sum(dato["costo_inexacto"] for dato in costo_flujo.values())
        if inexacto:
            lista.append({"id": "costo_inexacto", "nivel": NIVEL_ADVERTENCIA,
                          "titulo": f"{inexacto} llamada(s) con costo estimado o sin precio",
                          "detalle": "OpenCode no informó el costo; el tope de gasto puede quedarse corto. Los tokens sí son exactos."})
        return sorted(lista, key=lambda alerta: alerta["nivel"] != NIVEL_CRITICA)

    @staticmethod
    def _titulos(lista_flujo: set[str], costo_flujo: dict[str, dict[str, Any]], limite: int = 5) -> list[dict[str, Any]]:
        return [
            {"workflow_id": flujo, "titulo": (costo_flujo.get(flujo) or {}).get("titulo") or "Sin título"}
            for flujo in sorted(lista_flujo)[:limite]
        ]

    # --- Trazas --------------------------------------------------------------------------------------
    @staticmethod
    def _trazas(lista_turno: list[dict[str, Any]], lista_herramienta: list[dict[str, Any]],
                costo_flujo: dict[str, dict[str, Any]], limite: int = 30) -> list[dict[str, Any]]:
        por_flujo: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for turno in lista_turno:
            if turno["workflow_id"]:
                por_flujo[turno["workflow_id"]].append(turno)
        consulta: dict[str, int] = defaultdict(int)
        for llamada in lista_herramienta:
            if llamada["workflow_id"]:
                consulta[llamada["workflow_id"]] += 1
        lista = []
        for flujo, turnos in por_flujo.items():
            turnos = sorted(turnos, key=lambda item: item["creado_en"])
            ultimo = turnos[-1]
            if ultimo["exitoso"]:
                estado = ESTADO_REINTENTO if any(item["intentos"] > 1 for item in turnos) else ESTADO_OK
            else:
                estado = ESTADO_DETENIDA if ultimo["codigo_error"] == CODIGO_PRESUPUESTO else ESTADO_FALLO
            dato = costo_flujo.get(flujo) or {}
            lista.append({
                "workflow_id": flujo,
                "titulo": dato.get("titulo") or "Sin título",
                "modo": ultimo["modo"],
                "estado": estado,
                "inicio": turnos[0]["creado_en"],
                "fin": ultimo["creado_en"],
                "duracion_ms": sum(int(item["duracion_ms"] or 0) for item in turnos),
                "costo_usd": dato.get("costo_usd", 0.0),
                "consultas_mcp": consulta[flujo],
                "lento": any((item["duracion_ms"] or 0) > UMBRAL["paso_ms"] for item in turnos),
                "paso": [
                    {"agente": item["agente"], "nombre": _nombre(item["agente"]), "duracion_ms": int(item["duracion_ms"] or 0),
                     "intentos": item["intentos"], "exitoso": bool(item["exitoso"]), "codigo_error": item["codigo_error"]}
                    for item in turnos
                ],
            })
        return sorted(lista, key=lambda item: item["fin"], reverse=True)[:limite]


__all__ = ["ObservabilidadService", "UMBRAL", "percentil"]
