"""Tabla del consumo del modelo: una fila por respuesta de OpenCode, con sus tokens y su costo.

La clave de idempotencia es el id del mensaje de OpenCode: si la misma respuesta se registra dos veces,
cuenta una sola. No se guarda contenido (ni la consulta ni la respuesta), solo cantidades.
"""
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Boolean, Column, Float, Index, Integer, MetaData, String, Table, case, func, insert, select
from sqlalchemy.exc import IntegrityError

from agentes.metricas.registro_consumo import (
    MODO_CAMBIO, MODO_CREACION, ORIGEN_ESTIMADO, ORIGEN_SIN_PRECIO, ContextoConsumo, TurnoAgente, UsoModelo,
)

logger = logging.getLogger(__name__)

_metadata = MetaData()

consumo_modelo = Table(
    "consumo_modelo", _metadata,
    Column("id", String(36), primary_key=True),
    Column("mensaje_id", String(80), nullable=False, unique=True),
    Column("workflow_id", String(36)),
    Column("historia_id", String(100)),  # la HU: el mismo flujo al crearla, la HU aprobada en un cambio
    Column("titulo", String(200)),
    Column("modo", String(20), nullable=False),  # creacion | cambio | prueba | otro
    Column("agente", String(40), nullable=False),
    Column("proveedor", String(60)),
    Column("modelo", String(160)),
    Column("tokens_entrada", Integer, nullable=False),
    Column("tokens_salida", Integer, nullable=False),
    Column("tokens_razonamiento", Integer, nullable=False),
    Column("tokens_cache_lectura", Integer, nullable=False),
    Column("tokens_cache_escritura", Integer, nullable=False),
    Column("costo_usd", Float, nullable=False),
    Column("costo_origen", String(20), nullable=False),
    Column("duracion_ms", Integer),
    Column("exitosa", Boolean, nullable=False),
    Column("creado_en", String(40), nullable=False),
    Index("ix_consumo_modelo_historia", "historia_id"),
    Index("ix_consumo_modelo_workflow", "workflow_id"),
    Index("ix_consumo_modelo_creado", "creado_en"),
)

# Un turno de un agente en el flujo: si respondió, cuántos intentos usó (1 = sin reintentos) y cuánto tardó.
turno_agente = Table(
    "turno_agente", _metadata,
    Column("id", String(36), primary_key=True),
    Column("workflow_id", String(36)),
    Column("historia_id", String(100)),
    Column("modo", String(20), nullable=False),
    Column("agente", String(40), nullable=False),
    Column("exitoso", Boolean, nullable=False),
    Column("intentos", Integer, nullable=False),
    Column("codigo_error", String(40)),
    Column("duracion_ms", Integer, nullable=False),
    Column("creado_en", String(40), nullable=False),
    Index("ix_turno_agente_creado", "creado_en"),
)

_C = consumo_modelo.c
_T = turno_agente.c
_TOKENS_TOTAL = _C.tokens_entrada + _C.tokens_salida + _C.tokens_razonamiento + _C.tokens_cache_lectura + _C.tokens_cache_escritura


def _totales() -> list[Any]:
    """Columnas de suma comunes a todas las agrupaciones."""
    return [
        func.count(_C.id).label("llamadas"),
        func.coalesce(func.sum(_C.tokens_entrada), 0).label("tokens_entrada"),
        func.coalesce(func.sum(_C.tokens_salida), 0).label("tokens_salida"),
        func.coalesce(func.sum(_C.tokens_razonamiento), 0).label("tokens_razonamiento"),
        func.coalesce(func.sum(_C.tokens_cache_lectura + _C.tokens_cache_escritura), 0).label("tokens_cache"),
        func.coalesce(func.sum(_TOKENS_TOTAL), 0).label("tokens_total"),
        func.coalesce(func.sum(_C.costo_usd), 0).label("costo_usd"),
        func.coalesce(func.sum(func.coalesce(_C.duracion_ms, 0)), 0).label("duracion_ms"),
    ]


def _limpiar(fila) -> dict[str, Any]:
    datos = dict(fila._mapping)
    for campo in ("llamadas", "tokens_entrada", "tokens_salida", "tokens_razonamiento", "tokens_cache",
                  "tokens_total", "duracion_ms", "fallidas", "estimadas", "sin_precio"):
        if campo in datos:
            datos[campo] = int(datos[campo] or 0)
    if "costo_usd" in datos:
        datos["costo_usd"] = round(float(datos["costo_usd"] or 0), 8)
    return datos


class RepositorioConsumo:
    def __init__(self, motor) -> None:
        self.motor = motor
        _metadata.create_all(motor)

    def guardar(self, uso: UsoModelo, contexto: ContextoConsumo) -> bool:
        """Guarda una respuesta. Devuelve False si ya estaba registrada."""
        try:
            with self.motor.begin() as conexion:
                conexion.execute(insert(consumo_modelo).values(
                    id=str(uuid.uuid4()), mensaje_id=uso.mensaje_id,
                    workflow_id=contexto.workflow_id, historia_id=contexto.historia_id,
                    titulo=(contexto.titulo or None) and contexto.titulo[:200], modo=contexto.modo,
                    agente=uso.agente, proveedor=uso.proveedor, modelo=uso.modelo,
                    tokens_entrada=uso.tokens_entrada, tokens_salida=uso.tokens_salida,
                    tokens_razonamiento=uso.tokens_razonamiento, tokens_cache_lectura=uso.tokens_cache_lectura,
                    tokens_cache_escritura=uso.tokens_cache_escritura, costo_usd=uso.costo_usd,
                    costo_origen=uso.costo_origen, duracion_ms=uso.duracion_ms, exitosa=uso.exitosa,
                    creado_en=uso.creado_en,
                ))
            return True
        except IntegrityError:
            logger.info("consumo_duplicado", extra={"event": "consumo_duplicado", "agente": uso.agente})
            return False

    def guardar_turno(self, turno: TurnoAgente, contexto: ContextoConsumo) -> None:
        with self.motor.begin() as conexion:
            conexion.execute(insert(turno_agente).values(
                id=str(uuid.uuid4()), workflow_id=contexto.workflow_id, historia_id=contexto.historia_id,
                modo=contexto.modo, agente=turno.agente[:40], exitoso=turno.exitoso, intentos=turno.intentos,
                codigo_error=(turno.codigo_error or None) and turno.codigo_error[:40],
                duracion_ms=max(0, turno.duracion_ms), creado_en=turno.creado_en,
            ))

    def fiabilidad_por_agente(self, *, desde: str | None = None) -> list[dict[str, Any]]:
        """Por agente: turnos, fallidos, con reintento, tasa de fallo y duración (promedio y máxima)."""
        consulta = select(
            _T.agente,
            func.count(_T.id).label("turnos"),
            func.coalesce(func.sum(case((_T.exitoso.is_(False), 1), else_=0)), 0).label("fallidos"),
            func.coalesce(func.sum(case((_T.intentos > 1, 1), else_=0)), 0).label("con_reintento"),
            func.coalesce(func.sum(_T.intentos - 1), 0).label("reintentos"),
            func.avg(_T.duracion_ms).label("duracion_promedio_ms"),
            func.max(_T.duracion_ms).label("duracion_maxima_ms"),
        ).group_by(_T.agente)
        if desde:
            consulta = consulta.where(_T.creado_en >= desde)
        with self.motor.connect() as conexion:
            lista = [
                {
                    "agente": fila.agente, "turnos": int(fila.turnos), "fallidos": int(fila.fallidos or 0),
                    "con_reintento": int(fila.con_reintento or 0), "reintentos": int(fila.reintentos or 0),
                    "tasa_fallo": round(100 * int(fila.fallidos or 0) / int(fila.turnos), 1) if fila.turnos else 0.0,
                    "duracion_promedio_ms": int(round(float(fila.duracion_promedio_ms or 0))),
                    "duracion_maxima_ms": int(fila.duracion_maxima_ms or 0),
                }
                for fila in conexion.execute(consulta)
            ]
        return sorted(lista, key=lambda item: (item["tasa_fallo"], item["turnos"]), reverse=True)

    # --- Consultas ----------------------------------------------------------------------------------
    @staticmethod
    def _filtro(consulta, desde: str | None, historia_id: str | None = None):
        if desde:
            consulta = consulta.where(_C.creado_en >= desde)
        if historia_id:
            consulta = consulta.where(_C.historia_id == historia_id)
        return consulta

    def total(self, *, desde: str | None = None, historia_id: str | None = None) -> dict[str, Any]:
        fallidas = func.coalesce(func.sum(case((_C.exitosa.is_(False), 1), else_=0)), 0).label("fallidas")
        consulta = self._filtro(select(*_totales(), fallidas), desde, historia_id)
        with self.motor.connect() as conexion:
            return _limpiar(conexion.execute(consulta).one())

    def por_agente(self, *, desde: str | None = None, historia_id: str | None = None) -> list[dict[str, Any]]:
        consulta = self._filtro(select(_C.agente, *_totales()), desde, historia_id).group_by(_C.agente)
        with self.motor.connect() as conexion:
            lista = [_limpiar(fila) for fila in conexion.execute(consulta)]
        return sorted(lista, key=lambda item: item["costo_usd"], reverse=True)

    def por_modelo(self, *, desde: str | None = None) -> list[dict[str, Any]]:
        consulta = self._filtro(
            select(
                _C.proveedor, _C.modelo,
                func.coalesce(func.sum(case((_C.costo_origen == ORIGEN_ESTIMADO, 1), else_=0)), 0).label("estimadas"),
                func.coalesce(func.sum(case((_C.costo_origen == ORIGEN_SIN_PRECIO, 1), else_=0)), 0).label("sin_precio"),
                *_totales(),
            ),
            desde,
        ).group_by(_C.proveedor, _C.modelo)
        with self.motor.connect() as conexion:
            lista = [_limpiar(fila) for fila in conexion.execute(consulta)]
        return sorted(lista, key=lambda item: item["tokens_total"], reverse=True)

    def por_flujo(self, *, desde: str | None = None, historia_id: str | None = None, limite: int = 50) -> list[dict[str, Any]]:
        """Cada creación o cambio de una HU, del más reciente al más antiguo."""
        consulta = self._filtro(
            select(
                _C.workflow_id, func.max(_C.historia_id).label("historia_id"), func.max(_C.titulo).label("titulo"),
                func.max(_C.modo).label("modo"), func.min(_C.creado_en).label("inicio"),
                func.max(_C.creado_en).label("fin"), func.count(func.distinct(_C.agente)).label("agentes"), *_totales(),
            ).where(_C.workflow_id.is_not(None)),
            desde, historia_id,
        ).group_by(_C.workflow_id).order_by(func.max(_C.creado_en).desc()).limit(limite)
        with self.motor.connect() as conexion:
            return [_limpiar(fila) | {"agentes": int(fila.agentes or 0)} for fila in conexion.execute(consulta)]

    def por_dia(self, *, desde: str | None = None) -> list[dict[str, Any]]:
        dia = func.substr(_C.creado_en, 1, 10)
        consulta = self._filtro(select(dia.label("dia"), *_totales()), desde).group_by(dia).order_by(dia)
        with self.motor.connect() as conexion:
            return [_limpiar(fila) for fila in conexion.execute(consulta)]

    def promedio_por_modo(self, *, desde: str | None = None) -> dict[str, dict[str, Any]]:
        """Costo y tokens promedio de un flujo de creación y de uno de cambio."""
        por_flujo = self._filtro(
            select(_C.workflow_id, func.max(_C.modo).label("modo"), *_totales())
            .where(_C.workflow_id.is_not(None), _C.modo.in_((MODO_CREACION, MODO_CAMBIO))),
            desde,
        ).group_by(_C.workflow_id).subquery()
        consulta = select(
            por_flujo.c.modo, func.count().label("flujos"),
            func.avg(por_flujo.c.costo_usd).label("costo_usd"), func.avg(por_flujo.c.tokens_total).label("tokens_total"),
            func.avg(por_flujo.c.llamadas).label("llamadas"),
        ).group_by(por_flujo.c.modo)
        with self.motor.connect() as conexion:
            return {
                fila.modo: {
                    "flujos": int(fila.flujos or 0),
                    "costo_usd": round(float(fila.costo_usd or 0), 8),
                    "tokens_total": int(round(float(fila.tokens_total or 0))),
                    "llamadas": round(float(fila.llamadas or 0), 1),
                }
                for fila in conexion.execute(consulta)
            }


def desde_dias(dias: int | None) -> str | None:
    if not dias:
        return None
    return (datetime.now(UTC) - timedelta(days=dias)).isoformat(timespec="milliseconds")
