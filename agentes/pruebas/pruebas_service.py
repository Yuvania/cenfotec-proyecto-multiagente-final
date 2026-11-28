"""Ejecuciones de pruebas: pedirlas a GitHub Actions, seguirlas y guardar su resumen.

Flujo:
1. La persona pide una ejecución (alcance, ambiente y navegador). Solo puede haber una a la vez.
2. Se registra con un número legible (#013) y se arranca el workflow ``pruebas-e2e.yml``.
3. Mientras el tablero está abierto, cada consulta sincroniza con GitHub (como máximo una vez cada pocos
   segundos, para no gastar el límite de la API): estado, pasos y, al terminar, el resumen de los casos.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from agentes.notificaciones.teams_service import url_aplicacion
from agentes.pruebas.catalogo_pruebas import (
    AMBIENTE_PRODUCCION, CODIGO_AMBIENTE, CODIGO_NAVEGADOR, LISTA_AMBIENTE, LISTA_NAVEGADOR, alcance_de, como_dict,
    nombre_de, nombre_de_etiqueta,
)
from agentes.pruebas.github_actions_service import GitHubActionsError, GitHubActionsService
from agentes.pruebas.repositorio_pruebas import ESTADO_ACTIVO, ESTADO_FINAL, RepositorioPrueba

logger = logging.getLogger(__name__)

SEGUNDOS_ENTRE_SINCRONIZACION = 4
MINUTOS_SIN_INICIAR = 5
MAXIMO_CASO = 500
_MAXIMO_FILTRO = 2000

# Línea de tiempo del tablero. Cada etapa se reconoce por el inicio del nombre del paso del workflow.
LISTA_ETAPA = (
    ("solicitud", "Solicitud registrada", None),
    ("preparacion", "Se preparó el navegador y la aplicación", "Preparar"),
    ("ejecucion", "Pruebas en ejecución", "Ejecutar"),
    ("diagnostico", "Diagnóstico de los fallos (Agente de Pruebas)", "Diagnosticar"),
    ("publicacion", "Publicación de resultados", "Publicar"),
)
_ESTADO_COLA = {"queued", "waiting", "requested", "pending"}


class ErrorPrueba(Exception):
    def __init__(self, mensaje: str, *, status_code: int = 400) -> None:
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.status_code = status_code


class ExploracionResumen(BaseModel):
    model_config = ConfigDict(extra="ignore")
    rondas: int = Field(default=0, ge=0, le=20)
    acciones: list[str] = Field(default_factory=list, max_length=20)
    limitaciones: list[str] = Field(default_factory=list, max_length=10)


class DiagnosticoCaso(BaseModel):
    """Lo que explica el Agente de Pruebas de un caso fallido (agentes/pruebas/diagnosticar.py)."""
    model_config = ConfigDict(extra="ignore")
    estado: Literal["listo", "sin_diagnostico"]
    que_fallo: str | None = Field(default=None, max_length=400)
    causa_probable: str | None = Field(default=None, max_length=600)
    tipo: Literal["error_aplicacion", "prueba_desactualizada", "ambiente", "indeterminado"] | None = None
    confianza: Literal["alta", "media", "baja"] | None = None
    evidencia: list[str] = Field(default_factory=list, max_length=4)
    sugerencia: str | None = Field(default=None, max_length=600)
    motivo: str | None = Field(default=None, max_length=300)
    exploracion: ExploracionResumen | None = None


class CasoResumen(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default="", max_length=200)
    titulo: str = Field(max_length=300)
    modulo: str = Field(default="", max_length=60)
    archivo: str = Field(default="", max_length=200)
    dispositivo: str = Field(default="", max_length=30)
    estado: Literal["aprobado", "fallido", "omitido", "inestable"]
    duracion_ms: int = Field(default=0, ge=0)
    error: str | None = None
    pasos: list[str] = Field(default_factory=list, max_length=40)
    diagnostico: DiagnosticoCaso | None = None

    @field_validator("diagnostico", mode="before")
    @classmethod
    def _diagnostico_valido(cls, valor: Any) -> Any:
        # Un diagnóstico mal formado no invalida el resumen: el caso queda sin diagnóstico.
        try:
            return DiagnosticoCaso.model_validate(valor) if valor is not None else None
        except ValidationError:
            logger.warning("diagnostico_no_valido", extra={"event": "diagnostico_no_valido"})
            return None

    @field_validator("error")
    @classmethod
    def _recortar_error(cls, valor: str | None) -> str | None:
        return valor[:1500] if valor else valor

    @field_validator("pasos")
    @classmethod
    def _recortar_paso(cls, valor: list[str]) -> list[str]:
        return [paso[:200] for paso in valor]


class ResumenEjecucion(BaseModel):
    """Lo que publica ``e2e/soporte/reportero-resumen.js``. Se valida antes de guardarlo."""
    model_config = ConfigDict(extra="ignore")
    total: int = Field(default=0, ge=0)
    aprobados: int = Field(default=0, ge=0)
    fallidos: int = Field(default=0, ge=0)
    omitidos: int = Field(default=0, ge=0)
    inestables: int = Field(default=0, ge=0)
    duracion_ms: int = Field(default=0, ge=0)
    inicio: str | None = Field(default=None, max_length=40)
    navegador: str | None = Field(default=None, max_length=20)
    casos: list[CasoResumen] = Field(default_factory=list)

    @field_validator("casos")
    @classmethod
    def _limitar(cls, valor: list[CasoResumen]) -> list[CasoResumen]:
        return valor[:MAXIMO_CASO]


class SolicitudEjecucion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    alcance: str = Field(max_length=40)
    navegador: str = Field(default="chromium", max_length=20)
    ambiente: str = Field(default="pruebas", max_length=20)


def _ahora() -> datetime:
    return datetime.now(UTC)


def _fecha(valor: str | None) -> datetime | None:
    if not valor:
        return None
    try:
        return datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError:
        logger.warning("fecha_invalida", extra={"event": "fecha_invalida"})
        return None


def nombre_artefacto_resumen(ejecucion_id: str) -> str:
    return f"resumen-{ejecucion_id}"


def filtro_casos(lista_titulo: list[str]) -> str:
    """Expresión para ``--grep`` que elige exactamente esos casos (al repetir los fallidos)."""
    lista_unica = list(dict.fromkeys(titulo.strip() for titulo in lista_titulo if titulo.strip()))
    filtro = "|".join(re.escape(titulo) for titulo in lista_unica)
    if len(filtro) > _MAXIMO_FILTRO:
        raise ErrorPrueba("Hay demasiados casos fallidos para repetirlos uno por uno; ejecute el módulo completo.")
    return filtro


def linea_de_tiempo(lista_paso: list[dict[str, Any]], estado: str) -> list[dict[str, str]]:
    """Convierte los pasos de GitHub en las cuatro etapas que ve la persona."""
    lista_etapa = []
    for codigo, nombre, prefijo in LISTA_ETAPA:
        if prefijo is None:
            situacion = "completa"
        else:
            coincidencia = [p for p in lista_paso if p.get("nombre", "").startswith(prefijo)]
            if not coincidencia:
                situacion = "pendiente"
            elif any(p.get("conclusion") == "failure" for p in coincidencia):
                situacion = "fallida"
            elif all(p.get("estado") == "completed" for p in coincidencia):
                situacion = "omitida" if all(p.get("conclusion") == "skipped" for p in coincidencia) else "completa"
            elif any(p.get("estado") == "in_progress" for p in coincidencia):
                situacion = "en_curso"
            else:
                situacion = "pendiente"
        lista_etapa.append({"codigo": codigo, "nombre": nombre, "estado": situacion})
    if estado == "cancelada":
        for etapa in lista_etapa:
            if etapa["estado"] in ("pendiente", "en_curso"):
                etapa["estado"] = "cancelada"
    return lista_etapa


def estado_final(conclusion: str | None, resumen: ResumenEjecucion | None) -> tuple[str, str | None]:
    if conclusion == "cancelled":
        return "cancelada", "La ejecución se canceló."
    if resumen is None:
        return "error", "La ejecución terminó sin publicar resultados. Revise el registro en GitHub."
    if resumen.total == 0:
        return "error", "No se ejecutó ningún caso con ese filtro."
    if resumen.fallidos > 0:
        return "con_fallos", None
    return "aprobada", None


class PruebasService:
    def __init__(self, repositorio: RepositorioPrueba, github: GitHubActionsService | None = None) -> None:
        self.repositorio = repositorio
        self.github = github or GitHubActionsService()
        self._candado = asyncio.Lock()

    # --- Lectura ----------------------------------------------------------
    def configuracion(self) -> dict[str, Any]:
        return {
            **como_dict(),
            "configurado": self.github.configurado,
            "faltante": self.github.configuracion.faltante(),
            "repositorio": self.github.repositorio or None,
            "rama": self.github.rama,
            "url_produccion": url_aplicacion() or None,
        }

    def panel(self) -> dict[str, Any]:
        lista_ejecucion = [self.publica(e) for e in self.repositorio.listar(20)]
        lista_final = [e for e in lista_ejecucion if e["estado"] in ESTADO_FINAL]
        con_resumen = next((e for e in lista_final if e.get("resumen")), None)
        ultimas = [e for e in lista_final if e["estado"] in ("aprobada", "con_fallos")][:10]
        indicador = {
            "ultima": con_resumen and {
                "id": con_resumen["id"], "numero": con_resumen["numero"], "total": con_resumen["resumen"]["total"],
                "aprobados": con_resumen["resumen"]["aprobados"], "fallidos": con_resumen["resumen"]["fallidos"],
                "duracion_ms": con_resumen["resumen"]["duracion_ms"],
            },
            "tasa_exito": round(100 * sum(e["estado"] == "aprobada" for e in ultimas) / len(ultimas)) if ultimas else None,
        }
        activa = next((e for e in lista_ejecucion if e["estado"] in ESTADO_ACTIVO), None)
        return {"indicador": indicador, "activa": activa, "lista_ejecucion": lista_ejecucion}

    @staticmethod
    def publica(ejecucion: dict[str, Any]) -> dict[str, Any]:
        """Lo que ve el tablero. Los casos completos solo van en el detalle."""
        alcance = alcance_de(ejecucion["alcance"])
        resumen = ejecucion.get("resumen")
        return {
            "id": ejecucion["id"], "numero": ejecucion["numero"], "estado": ejecucion["estado"],
            "alcance": ejecucion["alcance"], "alcance_nombre": alcance.nombre if alcance else ejecucion["alcance"],
            "navegador": ejecucion["navegador"], "navegador_nombre": nombre_de(LISTA_NAVEGADOR, ejecucion["navegador"]),
            "ambiente": ejecucion["ambiente"], "ambiente_nombre": nombre_de(LISTA_AMBIENTE, ejecucion["ambiente"]),
            "solo_fallidos": bool(ejecucion.get("casos")),
            "iniciada_por": ejecucion.get("iniciada_por"), "run_url": ejecucion.get("run_url"),
            "mensaje": ejecucion.get("mensaje"), "pasos": ejecucion.get("pasos") or linea_de_tiempo([], ejecucion["estado"]),
            "creado_en": ejecucion["creado_en"], "finalizado_en": ejecucion.get("finalizado_en"),
            "resumen": resumen and {clave: valor for clave, valor in resumen.items() if clave != "casos"},
        }

    def detalle(self, ejecucion: dict[str, Any]) -> dict[str, Any]:
        resumen = ejecucion.get("resumen") or {}
        lista_caso = [{**caso, "modulo_nombre": nombre_de_etiqueta(caso.get("modulo") or "")}
                      for caso in resumen.get("casos", [])]
        return {**self.publica(ejecucion), "casos": lista_caso}

    def obtener(self, ejecucion_id: str) -> dict[str, Any]:
        ejecucion = self.repositorio.obtener(ejecucion_id)
        if ejecucion is None:
            raise ErrorPrueba("La ejecución no existe.", status_code=404)
        return ejecucion

    # --- Ejecutar ---------------------------------------------------------
    async def ejecutar(self, solicitud: SolicitudEjecucion, usuario: dict[str, Any], *,
                       casos: str | None = None) -> dict[str, Any]:
        alcance = alcance_de(solicitud.alcance)
        if alcance is None:
            raise ErrorPrueba("Ese alcance de pruebas no existe.")
        if solicitud.navegador not in CODIGO_NAVEGADOR:
            raise ErrorPrueba("Ese navegador no está disponible.")
        if solicitud.ambiente not in CODIGO_AMBIENTE:
            raise ErrorPrueba("Ese ambiente no existe.")
        url = ""
        if solicitud.ambiente == AMBIENTE_PRODUCCION:
            if not alcance.permite_produccion:
                raise ErrorPrueba("En producción solo se ejecutan las pruebas básicas, que no crean ni cambian datos.")
            url = url_aplicacion()
            if not url.startswith("https://"):
                raise ErrorPrueba("Para probar producción el servicio necesita APP_URL (o RENDER_EXTERNAL_URL) con https.",
                                  status_code=503)
        if not self.github.configurado:
            raise ErrorPrueba("Las pruebas automatizadas no están configuradas: falta "
                              + " y ".join(self.github.configuracion.faltante()) + ".", status_code=503)
        async with self._candado:
            await self._sincronizar_activa()
            activa = self.repositorio.activa()
            if activa is not None:
                raise ErrorPrueba(f"Ya hay una ejecución en curso (#{activa['numero']:03d}). Espere a que termine o "
                                  "cancélela.", status_code=409)
            ejecucion = self.repositorio.crear(
                alcance=alcance.codigo, navegador=solicitud.navegador, ambiente=solicitud.ambiente, casos=casos,
                repositorio=self.github.repositorio, iniciada_por=usuario.get("nombre") or usuario.get("usuario"),
                iniciada_por_usuario=usuario.get("id"))
        entradas = {
            "ejecucion": ejecucion["id"], "numero": f"#{ejecucion['numero']:03d}", "alcance": alcance.codigo,
            "navegador": solicitud.navegador, "ambiente": solicitud.ambiente, "url": url, "casos": casos or "",
        }
        try:
            arranque = await self.github.disparar(entradas)
        except GitHubActionsError as exc:
            self.repositorio.actualizar(ejecucion["id"], estado="error", mensaje=exc.mensaje)
            raise ErrorPrueba(exc.mensaje, status_code=exc.status_code) from exc
        logger.info("prueba_solicitada", extra={"event": "prueba_solicitada", "numero": ejecucion["numero"],
                                                "alcance": alcance.codigo, "ambiente": solicitud.ambiente})
        ejecucion = self.repositorio.actualizar(
            ejecucion["id"], estado="en_cola", run_id=arranque["run_id"], run_url=arranque["run_url"],
            pasos=linea_de_tiempo([], "en_cola"))
        return self.publica(ejecucion)

    async def repetir_fallidos(self, ejecucion_id: str, usuario: dict[str, Any]) -> dict[str, Any]:
        anterior = self.obtener(ejecucion_id)
        lista_fallido = [c["titulo"] for c in (anterior.get("resumen") or {}).get("casos", [])
                         if c.get("estado") == "fallido"]
        if not lista_fallido:
            raise ErrorPrueba("Esa ejecución no tiene casos fallidos.")
        solicitud = SolicitudEjecucion(alcance=anterior["alcance"], navegador=anterior["navegador"],
                                       ambiente=anterior["ambiente"])
        return await self.ejecutar(solicitud, usuario, casos=filtro_casos(lista_fallido))

    async def cancelar(self, ejecucion_id: str) -> dict[str, Any]:
        ejecucion = await self.sincronizar(self.obtener(ejecucion_id), forzar=True)
        if ejecucion["estado"] not in ESTADO_ACTIVO:
            raise ErrorPrueba("La ejecución ya terminó.", status_code=409)
        if ejecucion.get("run_id"):
            try:
                await self.github.cancelar(ejecucion["run_id"])
            except GitHubActionsError as exc:
                raise ErrorPrueba(exc.mensaje, status_code=exc.status_code) from exc
            return self.repositorio.actualizar(ejecucion["id"], mensaje="Cancelación solicitada.")
        return self.repositorio.actualizar(ejecucion["id"], estado="cancelada", mensaje="La ejecución se canceló.",
                                           pasos=linea_de_tiempo([], "cancelada"))

    # --- Sincronizar con GitHub --------------------------------------------
    async def _sincronizar_activa(self) -> None:
        activa = self.repositorio.activa()
        if activa is not None:
            await self.sincronizar(activa, forzar=True)

    async def sincronizar(self, ejecucion: dict[str, Any], *, forzar: bool = False) -> dict[str, Any]:
        if ejecucion["estado"] not in ESTADO_ACTIVO or not self.github.configurado:
            return ejecucion
        ultima = _fecha(ejecucion.get("sincronizado_en"))
        if not forzar and ultima and (_ahora() - ultima).total_seconds() < SEGUNDOS_ENTRE_SINCRONIZACION:
            return ejecucion
        try:
            return await self._sincronizar(ejecucion)
        except GitHubActionsError as exc:
            # Si GitHub no responde, el tablero sigue mostrando el último estado conocido.
            logger.warning("prueba_sin_sincronizar", extra={"event": "prueba_sin_sincronizar", "numero": ejecucion["numero"]})
            return self.repositorio.actualizar(ejecucion["id"], mensaje=exc.mensaje,
                                               sincronizado_en=_ahora().isoformat(timespec="milliseconds"))

    async def _sincronizar(self, ejecucion: dict[str, Any]) -> dict[str, Any]:
        marca = _ahora().isoformat(timespec="milliseconds")
        run_id = ejecucion.get("run_id")
        if not run_id:
            run = await self.github.buscar_run(ejecucion["id"])
            if run is None:
                creada = _fecha(ejecucion["creado_en"])
                if creada and (_ahora() - creada).total_seconds() > MINUTOS_SIN_INICIAR * 60:
                    return self.repositorio.actualizar(
                        ejecucion["id"], estado="error", sincronizado_en=marca,
                        mensaje="GitHub no inició la ejecución. Revise que el workflow esté habilitado en Actions.")
                return self.repositorio.actualizar(ejecucion["id"], sincronizado_en=marca)
            run_id = str(run["id"])
        else:
            run = await self.github.obtener_run(run_id)
        lista_paso = await self.github.listar_paso(run_id)
        cambios: dict[str, Any] = {"run_id": run_id, "run_url": run.get("html_url"), "sincronizado_en": marca}
        if run.get("status") != "completed":
            estado = "en_cola" if run.get("status") in _ESTADO_COLA else "en_ejecucion"
            return self.repositorio.actualizar(ejecucion["id"], estado=estado, pasos=linea_de_tiempo(lista_paso, estado),
                                               **cambios)
        resumen = None
        if run.get("conclusion") != "cancelled":
            crudo = await self.github.descargar_resumen(run_id, nombre_artefacto_resumen(ejecucion["id"]))
            if crudo is not None:
                try:
                    resumen = ResumenEjecucion.model_validate(crudo)
                except ValidationError:
                    logger.warning("resumen_no_valido", extra={"event": "resumen_no_valido", "numero": ejecucion["numero"]})
        estado, mensaje = estado_final(run.get("conclusion"), resumen)
        logger.info("prueba_finalizada", extra={"event": "prueba_finalizada", "numero": ejecucion["numero"],
                                                "estado": estado})
        return self.repositorio.actualizar(
            ejecucion["id"], estado=estado, mensaje=mensaje, pasos=linea_de_tiempo(lista_paso, estado),
            resumen=resumen.model_dump() if resumen else None, **cambios)
