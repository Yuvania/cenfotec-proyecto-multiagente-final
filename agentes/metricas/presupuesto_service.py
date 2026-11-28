"""Kill-switch financiero: tope de gasto por historia y por mes.

Antes de cada llamada al modelo, ``OpenCodeClient.submit_prompt`` llama a ``verificar_presupuesto`` (ver
``registro_consumo``), que consulta a este servicio. Si el flujo (la creación o el cambio de una HU) o el mes
alcanzaron su tope, la llamada no se hace: el flujo se congela con el error ``PRESUPUESTO_AGOTADO``, no se
reintenta solo y le llega el aviso «Falló un agente» a quien creó la historia, que puede terminarla en modo
manual. Es la supervisión humana por excepción.

Topes (variables de entorno, en dólares; ``0`` lo desactiva):

- ``PRESUPUESTO_HISTORIA_USD`` (0,50 por defecto): lo máximo que puede gastar una creación o un cambio de HU.
- ``PRESUPUESTO_MENSUAL_USD`` (60 por defecto, el uso mensual que incluye OpenCode Go): lo máximo del mes
  calendario, en la hora local (``ZONA_HORARIA``).

Este tope es la segunda barrera. La primera, la que garantiza que no se pague más que la suscripción, está en la
consola de OpenCode: «Use balance» apagado y sin créditos de Zen.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from agentes.metricas.registro_consumo import (
    ALCANCE_HISTORIA, ALCANCE_MES, ContextoConsumo, PresupuestoAgotadoError,
)
from agentes.metricas.repositorio_consumo import RepositorioConsumo

logger = logging.getLogger(__name__)

PRESUPUESTO_HISTORIA_PREDETERMINADO = 0.50
PRESUPUESTO_MENSUAL_PREDETERMINADO = 60.0
PROPORCION_ADVERTENCIA = 0.8  # a partir del 80 % del mes se avisa en Observabilidad


def _monto(nombre: str, predeterminado: float) -> float:
    valor = os.environ.get(nombre, "").strip().replace(",", ".")
    if not valor:
        return predeterminado
    try:
        return max(0.0, float(valor))
    except ValueError:
        logger.warning("presupuesto_invalido", extra={"event": "presupuesto_invalido", "variable": nombre})
        return predeterminado


def presupuesto_historia() -> float:
    return _monto("PRESUPUESTO_HISTORIA_USD", PRESUPUESTO_HISTORIA_PREDETERMINADO)


def presupuesto_mensual() -> float:
    return _monto("PRESUPUESTO_MENSUAL_USD", PRESUPUESTO_MENSUAL_PREDETERMINADO)


def _zona() -> tzinfo:
    nombre = os.environ.get("ZONA_HORARIA", "").strip() or "America/Costa_Rica"
    try:
        return ZoneInfo(nombre)
    except (ZoneInfoNotFoundError, ValueError):
        logger.info("zona_horaria_no_disponible", extra={"event": "zona_horaria_no_disponible"})
        return timezone(timedelta(hours=-6))


def inicio_mes(ahora: datetime | None = None) -> str:
    """Primer instante del mes en curso (hora local), en UTC ISO como se guarda en la base."""
    local = (ahora or datetime.now(UTC)).astimezone(_zona())
    primero = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return primero.astimezone(UTC).isoformat(timespec="milliseconds")


class PresupuestoService:
    def __init__(self, repositorio: RepositorioConsumo) -> None:
        self.repositorio = repositorio

    async def __call__(self, contexto: ContextoConsumo) -> None:
        """Guardián: se registra con ``agregar_guardian``. Lanza PresupuestoAgotadoError si se pasó un tope."""
        await asyncio.to_thread(self.verificar, contexto)

    def verificar(self, contexto: ContextoConsumo) -> None:
        tope_mes = presupuesto_mensual()
        if tope_mes > 0:
            gastado = self.repositorio.costo(desde=inicio_mes())
            if gastado >= tope_mes:
                logger.warning("presupuesto_mes_agotado", extra={"event": "presupuesto_mes_agotado"})
                raise PresupuestoAgotadoError(ALCANCE_MES, tope_mes, gastado)
        tope_historia = presupuesto_historia()
        if tope_historia > 0 and contexto.workflow_id:
            gastado = self.repositorio.costo(workflow_id=contexto.workflow_id)
            if gastado >= tope_historia:
                logger.warning("presupuesto_historia_agotado", extra={
                    "event": "presupuesto_historia_agotado", "workflow_id": contexto.workflow_id,
                })
                raise PresupuestoAgotadoError(ALCANCE_HISTORIA, tope_historia, gastado)

    def estado(self) -> dict[str, Any]:
        """Lo gastado en el mes contra su tope, para Observabilidad."""
        tope_mes = presupuesto_mensual()
        gastado = self.repositorio.costo(desde=inicio_mes())
        proporcion = (gastado / tope_mes) if tope_mes > 0 else None
        return {
            "mensual_usd": tope_mes or None,
            "historia_usd": presupuesto_historia() or None,
            "gastado_mes_usd": gastado,
            "porcentaje_mes": round(100 * proporcion, 1) if proporcion is not None else None,
        }


__all__ = ["PROPORCION_ADVERTENCIA", "PresupuestoService", "inicio_mes", "presupuesto_historia", "presupuesto_mensual"]
