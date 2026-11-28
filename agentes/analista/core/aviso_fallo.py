"""Aviso a quien creó la historia cuando un agente no pudo terminar (después de los reintentos automáticos).

Llega a Notificaciones con la categoría «Falló un agente» y el botón Retomar. No se repite mientras haya uno sin
leer del mismo flujo, y se cierra solo (queda leído) cuando el flujo vuelve a avanzar.
"""
from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import ValidationError

from agentes.analista.core.reintento import codigo_de
from agentes.metricas.metricas_service import NOMBRE_AGENTE

logger = logging.getLogger(__name__)

TIPO_AVISO_FALLO = "fallo"
_ADMINISTRADOR = " Avise a quien administra la aplicación."
MOTIVO_POR_CODIGO = {
    "TURN_TIMEOUT": "tardó más de lo permitido",
    "WORKFLOW_TIMEOUT": "tardó más de lo permitido",
    "OPENCODE_UNAVAILABLE": "el proveedor del modelo no respondió",
    "OPENCODE_RATE_LIMITED": "se agotó la cuota del modelo",
    "OPENCODE_AUTH_FAILED": "el servicio rechazó la clave del modelo." + _ADMINISTRADOR,
    "MODEL_UNAVAILABLE": "el modelo configurado no está disponible." + _ADMINISTRADOR,
    "OPENCODE_INCOMPATIBLE": "la versión del servicio del modelo no es compatible." + _ADMINISTRADOR,
    "AGENT_OUTPUT_INVALID": "su respuesta no tuvo el formato esperado",
    "CONTRACT_INVALID": "su respuesta no tuvo el formato esperado",
    "MCP_UNAVAILABLE": "no pudo consultar sus fuentes de conocimiento",
    "DEPENDENCY_UNAVAILABLE": "no pudo consultar un servicio que necesita",
    "PRESUPUESTO_AGOTADO": "se alcanzó el tope de gasto del modelo; el flujo quedó detenido para que una persona decida",
}
_NOMBRE_ERROR = {
    "WriterOutputError": "AGENT_OUTPUT_INVALID",
    "TechnicalAdvisorOutputError": "AGENT_OUTPUT_INVALID",
    "ChangeManagerError": "AGENT_OUTPUT_INVALID",
    "SalidaAgenteInvalidaError": "AGENT_OUTPUT_INVALID",
    "TechnicalAdvisorError": "MCP_UNAVAILABLE",
    "WorkflowDependencyError": "DEPENDENCY_UNAVAILABLE",
}


def zona_horaria() -> tzinfo:
    """Hora local para el aviso (``ZONA_HORARIA``, por defecto Costa Rica). Sin base de zonas: UTC−6 fijo."""
    nombre = os.environ.get("ZONA_HORARIA", "").strip() or "America/Costa_Rica"
    try:
        return ZoneInfo(nombre)
    except (ZoneInfoNotFoundError, ValueError):
        logger.info("zona_horaria_no_disponible", extra={"event": "zona_horaria_no_disponible"})
        return timezone(timedelta(hours=-6))


def es_fallo_de_agente(exc: BaseException) -> bool:
    """Una respuesta de la persona que no corresponde (ValueError) no es un fallo del agente; lo demás sí."""
    if isinstance(exc, ValidationError):
        return True  # la salida del agente no cumplió su contrato
    return not isinstance(exc, ValueError) and type(exc).__name__ != "WorkflowNotInterruptedError"


def _hora(momento: datetime) -> str:
    local = momento.astimezone(zona_horaria())
    hora = local.hour % 12 or 12
    return f"{hora}:{local.minute:02d} {'a. m.' if local.hour < 12 else 'p. m.'}"


def detalle_fallo(exc: BaseException, *, agente: str | None, ahora: datetime | None = None) -> str:
    """El texto del aviso: qué agente falló, por qué, si se reintentó y qué hacer. Sin detalles internos."""
    codigo = codigo_de(exc)
    codigo = _NOMBRE_ERROR.get(type(exc).__name__, codigo)
    if isinstance(exc, ValidationError):
        codigo = "AGENT_OUTPUT_INVALID"
    nombre = NOMBRE_AGENTE.get(agente or "", "Un agente")
    motivo = MOTIVO_POR_CODIGO.get(codigo, "ocurrió un error inesperado")
    partes = [f"{nombre} no pudo terminar: {motivo}" + ("" if motivo.endswith(".") else ".")]
    intentos = getattr(exc, "intentos_agente", 1) or 1
    if intentos > 1:
        partes.append(f"Se intentó {intentos} veces de forma automática.")
    vuelve = getattr(exc, "retry_at", None)
    if codigo == "OPENCODE_RATE_LIMITED" and isinstance(vuelve, datetime) and vuelve > (ahora or datetime.now(UTC)):
        partes.append(f"La cuota vuelve a las {_hora(vuelve)}.")
    if codigo == "PRESUPUESTO_AGOTADO":
        partes.append("El avance quedó guardado: puede terminar la historia en modo manual o pedir a quien "
                      "administra la aplicación que revise el consumo en Mantenimiento › Observabilidad.")
    else:
        partes.append("El avance quedó guardado: use Retomar para volver a intentarlo.")
    return " ".join(partes)


def agente_del_error(exc: BaseException, valores: dict[str, Any] | None) -> str | None:
    agente = getattr(exc, "agente_fallido", None)
    if agente:
        return str(agente)
    activo = (valores or {}).get("active_agent")
    return str(getattr(activo, "value", activo)) if activo else None
