"""Métricas: consumo de tokens y costo del modelo por historia, por agente y por día.

Ver ``agentes/metricas/metricas_service.py`` y ``docs/metricas.md``.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Path, Query, Request

from agentes.analista.api.errors import WorkflowApiError
from agentes.analista.api.sesion import requiere_accion
from agentes.analista.core.models import ErrorCode
from agentes.metricas.metricas_service import MetricasService, PeriodoInvalidoError
from agentes.metricas.observabilidad_service import ObservabilidadService
from agentes.seguridad.catalogo import ACCION

router = APIRouter()


def _servicio(request: Request) -> MetricasService:
    servicio = getattr(request.app.state, "metricas", None)
    if servicio is None:
        raise WorkflowApiError(ErrorCode.DEPENDENCY_UNAVAILABLE, "Las métricas no están disponibles.", status_code=503)
    return servicio


@router.get("/metricas/consumo", dependencies=[requiere_accion(ACCION.METRICA_VER)])
def leer_consumo(request: Request, periodo: str = Query(default="30", max_length=10)) -> dict[str, Any]:
    try:
        return _servicio(request).panel(periodo)
    except PeriodoInvalidoError as exc:
        raise WorkflowApiError(ErrorCode.INVALID_INPUT, str(exc), status_code=400) from exc


@router.get("/metricas/consumo/historias/{historia_id}", dependencies=[requiere_accion(ACCION.METRICA_VER)])
def leer_consumo_historia(
    request: Request, historia_id: str = Path(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.:-]+$"),
) -> dict[str, Any]:
    return _servicio(request).historia(historia_id)


@router.get("/metricas/observabilidad", dependencies=[requiere_accion(ACCION.OBSERVABILIDAD_VER)])
def leer_observabilidad(request: Request, periodo: str = Query(default="7", max_length=10)) -> dict[str, Any]:
    """Latencia por paso (agentes y herramientas MCP), alertas con los umbrales aprobados y estado de cada traza."""
    servicio: ObservabilidadService | None = getattr(request.app.state, "observabilidad", None)
    if servicio is None:
        raise WorkflowApiError(ErrorCode.DEPENDENCY_UNAVAILABLE, "La observabilidad no está disponible.", status_code=503)
    try:
        return servicio.panel(periodo)
    except PeriodoInvalidoError as exc:
        raise WorkflowApiError(ErrorCode.INVALID_INPUT, str(exc), status_code=400) from exc
