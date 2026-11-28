"""Registro de las ejecuciones de pruebas: quién la pidió, qué se probó y el resumen de resultados.

Las evidencias completas (reporte HTML, JUnit, capturas, videos y trazas) quedan en GitHub como artefactos
de la ejecución; aquí solo se guarda el resumen para el tablero y el enlace a GitHub.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Column, Index, Integer, MetaData, String, Table, Text, func, insert, select, update
from sqlalchemy.dialects import mysql

logger = logging.getLogger(__name__)

_Largo = Text().with_variant(mysql.MEDIUMTEXT(), "mysql")
_metadata = MetaData()

# solicitada → en_cola → en_ejecucion → aprobada | con_fallos | cancelada | error
ESTADO_ACTIVO = ("solicitada", "en_cola", "en_ejecucion")
ESTADO_FINAL = ("aprobada", "con_fallos", "cancelada", "error")
_CAMPO_JSON = ("pasos", "resumen")

prueba_ejecucion = Table(
    "prueba_ejecucion", _metadata,
    Column("id", String(36), primary_key=True),
    Column("numero", Integer, nullable=False),  # consecutivo legible: #001, #002...
    Column("alcance", String(40), nullable=False),
    Column("navegador", String(20), nullable=False),
    Column("ambiente", String(20), nullable=False),
    Column("casos", Text),  # solo estos casos (al repetir los fallidos)
    Column("estado", String(20), nullable=False),
    Column("run_id", String(30)),  # id de la ejecución en GitHub Actions
    Column("run_url", String(300)),
    Column("repositorio", String(120)),
    Column("iniciada_por", String(120)),
    Column("iniciada_por_usuario", String(60)),
    Column("mensaje", String(300)),
    Column("pasos", _Largo),
    Column("resumen", _Largo),
    Column("creado_en", String(40), nullable=False),
    Column("actualizado_en", String(40), nullable=False),
    Column("sincronizado_en", String(40)),
    Column("finalizado_en", String(40)),
    Index("ix_prueba_ejecucion_estado", "estado"),
    Index("ix_prueba_ejecucion_numero", "numero"),
)


def _ahora() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _fila(fila) -> dict[str, Any]:
    datos = dict(fila._mapping)
    for campo in _CAMPO_JSON:
        valor = datos.get(campo)
        if not valor:
            datos[campo] = None
            continue
        try:
            datos[campo] = json.loads(valor)
        except ValueError:
            logger.warning("prueba_json_invalido", extra={"event": "prueba_json_invalido", "campo": campo})
            datos[campo] = None
    return datos


class RepositorioPrueba:
    def __init__(self, motor) -> None:
        self.motor = motor
        _metadata.create_all(motor)

    def crear(self, *, alcance: str, navegador: str, ambiente: str, casos: str | None, repositorio: str,
              iniciada_por: str | None, iniciada_por_usuario: str | None) -> dict[str, Any]:
        ejecucion_id = str(uuid.uuid4())
        ahora = _ahora()
        with self.motor.begin() as conexion:
            numero = (conexion.execute(select(func.max(prueba_ejecucion.c.numero))).scalar() or 0) + 1
            conexion.execute(insert(prueba_ejecucion).values(
                id=ejecucion_id, numero=numero, alcance=alcance, navegador=navegador, ambiente=ambiente,
                casos=casos or None, estado="solicitada", repositorio=repositorio[:120],
                iniciada_por=(iniciada_por or None) and iniciada_por[:120],
                iniciada_por_usuario=(iniciada_por_usuario or None) and iniciada_por_usuario[:60],
                creado_en=ahora, actualizado_en=ahora))
        return self.obtener(ejecucion_id)

    def obtener(self, ejecucion_id: str) -> dict[str, Any] | None:
        with self.motor.connect() as conexion:
            fila = conexion.execute(select(prueba_ejecucion).where(prueba_ejecucion.c.id == ejecucion_id)).first()
        return _fila(fila) if fila is not None else None

    def listar(self, limite: int = 20) -> list[dict[str, Any]]:
        consulta = select(prueba_ejecucion).order_by(prueba_ejecucion.c.numero.desc()).limit(limite)
        with self.motor.connect() as conexion:
            return [_fila(fila) for fila in conexion.execute(consulta)]

    def listar_finalizada_desde(self, desde: str | None, limite: int = 500) -> list[dict[str, Any]]:
        consulta = select(prueba_ejecucion).where(prueba_ejecucion.c.estado.in_(ESTADO_FINAL))
        if desde:
            consulta = consulta.where(prueba_ejecucion.c.finalizado_en >= desde)
        with self.motor.connect() as conexion:
            return [_fila(fila) for fila in conexion.execute(consulta.order_by(prueba_ejecucion.c.numero.desc()).limit(limite))]

    def activa(self) -> dict[str, Any] | None:
        """La ejecución que todavía no termina, si hay. Solo se permite una a la vez."""
        consulta = (select(prueba_ejecucion).where(prueba_ejecucion.c.estado.in_(ESTADO_ACTIVO))
                    .order_by(prueba_ejecucion.c.numero.desc()).limit(1))
        with self.motor.connect() as conexion:
            fila = conexion.execute(consulta).first()
        return _fila(fila) if fila is not None else None

    def actualizar(self, ejecucion_id: str, **cambios: Any) -> dict[str, Any] | None:
        valores = {clave: valor for clave, valor in cambios.items() if clave in prueba_ejecucion.c}
        for campo in _CAMPO_JSON:
            if campo in valores and valores[campo] is not None:
                valores[campo] = json.dumps(valores[campo], ensure_ascii=False)
        if "mensaje" in valores and valores["mensaje"]:
            valores["mensaje"] = str(valores["mensaje"])[:300]
        if valores.get("estado") in ESTADO_FINAL and "finalizado_en" not in valores:
            valores["finalizado_en"] = _ahora()
        valores["actualizado_en"] = _ahora()
        with self.motor.begin() as conexion:
            conexion.execute(update(prueba_ejecucion).where(prueba_ejecucion.c.id == ejecucion_id).values(**valores))
        return self.obtener(ejecucion_id)
