"""Pruebas automatizadas: tablero de ejecuciones de Playwright que corren en GitHub Actions.

Ver ``agentes/pruebas/pruebas_service.py`` y ``docs/pruebas-automatizadas.md``.
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Request

from agentes.analista.api.errors import WorkflowApiError
from agentes.analista.api.sesion import requiere_accion, usuario_actual
from agentes.analista.core.models import ErrorCode
from agentes.pruebas.pruebas_service import ErrorPrueba, PruebasService, SolicitudEjecucion
from agentes.seguridad.catalogo import ACCION

router = APIRouter()

_ID = r"^[0-9a-fA-F-]{36}$"
_CODIGO = {400: ErrorCode.INVALID_INPUT, 404: ErrorCode.REPOSITORY_NOT_FOUND, 409: ErrorCode.CAPACITY_EXCEEDED}


def _servicio(request: Request) -> PruebasService:
    servicio = getattr(request.app.state, "pruebas", None)
    if servicio is None:
        raise WorkflowApiError(ErrorCode.DEPENDENCY_UNAVAILABLE, "Las pruebas automatizadas no están disponibles.",
                               status_code=503)
    return servicio


def _error(exc: ErrorPrueba) -> WorkflowApiError:
    codigo = _CODIGO.get(exc.status_code, ErrorCode.DEPENDENCY_UNAVAILABLE)
    return WorkflowApiError(codigo, exc.mensaje, status_code=exc.status_code)


@router.get("/pruebas/configuracion", dependencies=[requiere_accion(ACCION.PRUEBA_VER)])
async def leer_configuracion(request: Request) -> dict[str, Any]:
    return await _servicio(request).configuracion_con_token()


@router.get("/pruebas/ejecuciones", dependencies=[requiere_accion(ACCION.PRUEBA_VER)])
async def listar_ejecucion(request: Request) -> dict[str, Any]:
    servicio = _servicio(request)
    activa = servicio.repositorio.activa()
    if activa is not None:
        await servicio.sincronizar(activa)
    return servicio.panel()


@router.post("/pruebas/ejecuciones", status_code=201, dependencies=[requiere_accion(ACCION.PRUEBA_EJECUTAR)])
async def crear_ejecucion(
    body: SolicitudEjecucion, request: Request, usuario: Annotated[dict[str, Any], Depends(usuario_actual)],
) -> dict[str, Any]:
    try:
        return await _servicio(request).ejecutar(body, usuario)
    except ErrorPrueba as exc:
        raise _error(exc) from exc


@router.get("/pruebas/ejecuciones/{ejecucion_id}", dependencies=[requiere_accion(ACCION.PRUEBA_VER)])
async def obtener_ejecucion(ejecucion_id: Annotated[str, Path(pattern=_ID)], request: Request) -> dict[str, Any]:
    servicio = _servicio(request)
    try:
        ejecucion = await servicio.sincronizar(servicio.obtener(ejecucion_id))
    except ErrorPrueba as exc:
        raise _error(exc) from exc
    return servicio.detalle(ejecucion)


@router.post("/pruebas/ejecuciones/{ejecucion_id}/repetir-fallidos", status_code=201,
             dependencies=[requiere_accion(ACCION.PRUEBA_EJECUTAR)])
async def repetir_fallidos(
    ejecucion_id: Annotated[str, Path(pattern=_ID)], request: Request,
    usuario: Annotated[dict[str, Any], Depends(usuario_actual)],
) -> dict[str, Any]:
    try:
        return await _servicio(request).repetir_fallidos(ejecucion_id, usuario)
    except ErrorPrueba as exc:
        raise _error(exc) from exc


@router.post("/pruebas/ejecuciones/{ejecucion_id}/cancelar", dependencies=[requiere_accion(ACCION.PRUEBA_EJECUTAR)])
async def cancelar_ejecucion(ejecucion_id: Annotated[str, Path(pattern=_ID)], request: Request) -> dict[str, Any]:
    servicio = _servicio(request)
    try:
        return servicio.publica(await servicio.cancelar(ejecucion_id))
    except ErrorPrueba as exc:
        raise _error(exc) from exc
