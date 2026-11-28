"""Métricas del consumo del modelo: cuánto cuesta cada historia, cada agente y cada día.

``registrar`` es el registrador que la aplicación conecta al arrancar (ver ``registro_consumo``): guarda cada
respuesta del modelo en la base y, si Langfuse está configurado, la envía como una generación con sus tokens
y su costo (sin contenido), para verla también en los tableros de Langfuse.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from agentes.metricas.registro_consumo import (
    MODO_CAMBIO, MODO_CREACION, ORIGEN_ESTIMADO, ORIGEN_SIN_PRECIO, ContextoConsumo, TurnoAgente, UsoModelo,
)
from agentes.metricas.repositorio_consumo import RepositorioConsumo, desde_dias

logger = logging.getLogger(__name__)

LISTA_PERIODO = (
    {"codigo": "7", "nombre": "Últimos 7 días", "dias": 7},
    {"codigo": "30", "nombre": "Últimos 30 días", "dias": 30},
    {"codigo": "todo", "nombre": "Todo", "dias": None},
)
_DIAS_POR_PERIODO = {periodo["codigo"]: periodo["dias"] for periodo in LISTA_PERIODO}

# Nombre legible de cada agente de OpenCode (opencode.jsonc). Lo que no esté aquí se muestra con su id.
NOMBRE_AGENTE = {
    "analista": "Agente Analista",
    "asesor_tecnico": "Asesor Técnico",
    "redactor_revisor": "Redactor-Revisor",
    "gestor_cambios": "Gestor de Cambios",
    "probador": "Agente de Pruebas",
}

# Consumo del Agente de Pruebas, que corre en GitHub: lo entrega el servicio de pruebas desde sus resúmenes.
ConsumoPrueba = Callable[[str | None], dict[str, Any]]


class PeriodoInvalidoError(ValueError):
    pass


class MetricasService:
    def __init__(self, repositorio: RepositorioConsumo, *, observability: Any = None,
                 consumo_prueba: ConsumoPrueba | None = None) -> None:
        self.repositorio = repositorio
        self.observability = observability
        self.consumo_prueba = consumo_prueba

    # --- Registro -----------------------------------------------------------------------------------
    async def registrar(self, uso: UsoModelo, contexto: ContextoConsumo) -> None:
        nuevo = await asyncio.to_thread(self.repositorio.guardar, uso, contexto)
        if nuevo:
            self._enviar_a_langfuse(uso, contexto)

    async def registrar_turno(self, turno: TurnoAgente, contexto: ContextoConsumo) -> None:
        await asyncio.to_thread(self.repositorio.guardar_turno, turno, contexto)

    def _enviar_a_langfuse(self, uso: UsoModelo, contexto: ContextoConsumo) -> None:
        cliente = getattr(self.observability, "client", None)
        if cliente is None:
            return
        try:
            generacion = cliente.start_observation(
                as_type="generation",
                name=f"modelo-{uso.agente}",
                model=uso.modelo or None,
                usage_details={
                    "input": uso.tokens_entrada, "output": uso.tokens_salida, "reasoning": uso.tokens_razonamiento,
                    "cache_read": uso.tokens_cache_lectura, "cache_write": uso.tokens_cache_escritura,
                },
                cost_details={"total": uso.costo_usd},
                metadata={
                    "agente": uso.agente, "modo": contexto.modo, "workflow_id": contexto.workflow_id,
                    "historia_id": contexto.historia_id, "costo_origen": uso.costo_origen,
                    "duracion_ms": uso.duracion_ms,
                },
                level="DEFAULT" if uso.exitosa else "ERROR",
            )
            generacion.end()
        except Exception as exc:
            logger.warning("langfuse_consumo_fallido", extra={"event": "langfuse_consumo_fallido", "error": type(exc).__name__})

    # --- Consultas ----------------------------------------------------------------------------------
    @staticmethod
    def _desde(periodo: str) -> str | None:
        if periodo not in _DIAS_POR_PERIODO:
            raise PeriodoInvalidoError("El periodo no es válido.")
        return desde_dias(_DIAS_POR_PERIODO[periodo])

    @staticmethod
    def _con_nombre(lista: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [item | {"nombre": NOMBRE_AGENTE.get(item["agente"], item["agente"])} for item in lista]

    def _aviso_costo(self, lista_modelo: list[dict[str, Any]]) -> str | None:
        estimadas = sum(item["estimadas"] for item in lista_modelo)
        sin_precio = sum(item["sin_precio"] for item in lista_modelo)
        if sin_precio:
            return (f"{sin_precio} llamadas no tienen costo: OpenCode no informó el costo y el modelo no anuncia "
                    "su precio. Los tokens sí son exactos.")
        if estimadas:
            return (f"{estimadas} llamadas tienen el costo estimado con el precio del modelo, porque OpenCode no "
                    "lo informó. Los tokens son exactos.")
        return None

    def panel(self, periodo: str = "30") -> dict[str, Any]:
        desde = self._desde(periodo)
        repositorio = self.repositorio
        lista_modelo = repositorio.por_modelo(desde=desde)
        promedio = repositorio.promedio_por_modo(desde=desde)
        prueba = None
        if self.consumo_prueba is not None:
            try:
                prueba = self.consumo_prueba(desde)
            except Exception as exc:
                logger.warning("consumo_prueba_no_disponible", extra={"event": "consumo_prueba_no_disponible", "error": type(exc).__name__})
        return {
            "periodo": periodo,
            "lista_periodo": [{"codigo": p["codigo"], "nombre": p["nombre"]} for p in LISTA_PERIODO],
            "total": repositorio.total(desde=desde),
            "promedio_creacion": promedio.get(MODO_CREACION),
            "promedio_cambio": promedio.get(MODO_CAMBIO),
            "por_agente": self._con_nombre(repositorio.por_agente(desde=desde)),
            "fiabilidad": self._con_nombre(repositorio.fiabilidad_por_agente(desde=desde)),
            "por_modelo": lista_modelo,
            "por_dia": repositorio.por_dia(desde=desde),
            "por_flujo": repositorio.por_flujo(desde=desde, limite=50),
            "prueba": prueba,
            "aviso_costo": self._aviso_costo(lista_modelo),
        }

    def historia(self, historia_id: str) -> dict[str, Any]:
        """Lo que costó una HU: su creación y cada cambio, por agente."""
        historia_id = historia_id.strip()[:100]
        return {
            "historia_id": historia_id,
            "total": self.repositorio.total(historia_id=historia_id),
            "por_agente": self._con_nombre(self.repositorio.por_agente(historia_id=historia_id)),
            "por_flujo": self.repositorio.por_flujo(historia_id=historia_id, limite=20),
        }


__all__ = ["LISTA_PERIODO", "MetricasService", "NOMBRE_AGENTE", "ORIGEN_ESTIMADO", "ORIGEN_SIN_PRECIO", "PeriodoInvalidoError"]
