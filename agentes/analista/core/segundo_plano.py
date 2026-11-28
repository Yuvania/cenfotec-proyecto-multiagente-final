"""Agentes en segundo plano: una cola de flujos, sus eventos de avance y quién los sigue en vivo.

En lugar de que la solicitud HTTP espere minutos a los agentes, la API responde al instante (202) y el flujo corre
aquí, en una tarea aparte:

- **Cola**: como máximo ``FLUJOS_SIMULTANEOS`` flujos a la vez (2 por defecto). Los demás esperan su turno y lo
  ven («En cola, puesto 1»). Así un pico de pedidos no satura el servidor ni la cuota del modelo.
- **Avance**: cada flujo guarda sus eventos (``avance.emitir``): en cola, inicia, qué agente empieza, qué consulta,
  si reintenta, cuándo termina y cómo terminó. Quien se conecta tarde recibe los anteriores y sigue en vivo.
- **Fin**: el último evento dice si quedó listo (y qué espera ahora) o el error, ya traducido para la persona.

Límite conocido: vive en la memoria del proceso (una instancia). Con varias instancias, la cola y los eventos
pasarían a un servicio compartido (por ejemplo, una cola en la base o Redis); la API no cambiaría.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from agentes.analista.core.avance import emitir, escuchar

logger = logging.getLogger(__name__)

MAXIMO_EVENTO = 300
CONSERVAR_TERMINADO_SEGUNDO = 15 * 60
FLUJOS_SIMULTANEOS_PREDETERMINADO = 2


def flujos_simultaneos() -> int:
    valor = os.environ.get("FLUJOS_SIMULTANEOS", "").strip()
    try:
        return max(1, min(int(valor), 10)) if valor else FLUJOS_SIMULTANEOS_PREDETERMINADO
    except ValueError:
        logger.warning("flujos_simultaneos_invalido", extra={"event": "flujos_simultaneos_invalido"})
        return FLUJOS_SIMULTANEOS_PREDETERMINADO


@dataclass(slots=True)
class EjecucionFlujo:
    workflow_id: UUID
    eventos: list[dict[str, Any]] = field(default_factory=list)
    suscriptores: set[asyncio.Queue] = field(default_factory=set)
    tarea: asyncio.Task | None = None
    resultado: dict[str, Any] | None = None
    terminado_en: float | None = None
    puesto: int | None = None  # último puesto en la cola que se avisó

    @property
    def en_curso(self) -> bool:
        return self.resultado is None

    def estado(self) -> dict[str, Any]:
        return {"workflow_id": str(self.workflow_id), "en_curso": self.en_curso, "eventos": list(self.eventos),
                "resultado": self.resultado}


# Lo que hace la ruta al terminar: avisos y qué espera ahora el flujo. Recibe el resultado de la operación y si
# alguien estaba mirando; devuelve datos para el evento «fin» (por ejemplo, {"espera": "business_answers"}).
AlTerminar = Callable[[Any, bool], Awaitable[dict[str, Any] | None] | dict[str, Any] | None]
TraducirError = Callable[[BaseException], dict[str, Any]]


class SegundoPlanoService:
    def __init__(self, maximo_simultaneo: int | None = None) -> None:
        self._semaforo = asyncio.Semaphore(maximo_simultaneo or flujos_simultaneos())
        self._ejecucion: dict[UUID, EjecucionFlujo] = {}
        self._en_espera: list[UUID] = []

    # --- Consulta -------------------------------------------------------------------------------------
    def en_curso(self, workflow_id: UUID) -> bool:
        ejecucion = self._ejecucion.get(workflow_id)
        return ejecucion is not None and ejecucion.en_curso

    def lista_en_curso(self) -> set[str]:
        return {str(wid) for wid, ejecucion in self._ejecucion.items() if ejecucion.en_curso}

    def estado(self, workflow_id: UUID) -> dict[str, Any] | None:
        ejecucion = self._ejecucion.get(workflow_id)
        return ejecucion.estado() if ejecucion else None

    # --- Eventos --------------------------------------------------------------------------------------
    def _agregar(self, ejecucion: EjecucionFlujo, evento: dict[str, Any]) -> None:
        if len(ejecucion.eventos) >= MAXIMO_EVENTO:
            ejecucion.eventos.pop(1)  # se conserva el primero (cuándo empezó)
        ejecucion.eventos.append(evento)
        for cola in list(ejecucion.suscriptores):
            cola.put_nowait(evento)

    def suscribir(self, workflow_id: UUID) -> tuple[list[dict[str, Any]], asyncio.Queue | None]:
        """Los eventos que ya pasaron y, si sigue en curso, una cola por la que llegan los nuevos hasta el «fin».
        Quien se suscribe cuenta como «mirando» (no se le manda el aviso de lista). Siempre ``desuscribir``."""
        ejecucion = self._ejecucion.get(workflow_id)
        if ejecucion is None:
            return [], None
        anteriores = list(ejecucion.eventos)
        if not ejecucion.en_curso:
            return anteriores, None
        cola: asyncio.Queue = asyncio.Queue()
        ejecucion.suscriptores.add(cola)
        return anteriores, cola

    def desuscribir(self, workflow_id: UUID, cola: asyncio.Queue | None) -> None:
        ejecucion = self._ejecucion.get(workflow_id)
        if ejecucion is not None and cola is not None:
            ejecucion.suscriptores.discard(cola)

    async def seguir(self, workflow_id: UUID) -> AsyncIterator[dict[str, Any]]:
        """Los eventos anteriores y luego los nuevos, hasta el «fin» (para pruebas y lectores internos)."""
        anteriores, cola = self.suscribir(workflow_id)
        try:
            for evento in anteriores:
                yield evento
                if evento["tipo"] == "fin":
                    return
            while cola is not None:
                evento = await cola.get()
                yield evento
                if evento["tipo"] == "fin":
                    return
        finally:
            self.desuscribir(workflow_id, cola)

    # --- Ejecutar -------------------------------------------------------------------------------------
    def _limpiar(self) -> None:
        ahora = time.monotonic()
        for wid in [wid for wid, e in self._ejecucion.items()
                    if e.terminado_en is not None and ahora - e.terminado_en > CONSERVAR_TERMINADO_SEGUNDO]:
            self._ejecucion.pop(wid, None)

    def lanzar(self, workflow_id: UUID, operacion: Callable[[], Awaitable[Any]], *,
               al_terminar: AlTerminar | None = None, traducir_error: TraducirError) -> EjecucionFlujo:
        """Pone el flujo en la cola y responde enseguida. ``operacion`` corre cuando le toque."""
        if self.en_curso(workflow_id):
            raise RuntimeError("El flujo ya tiene una ejecución en curso.")
        self._limpiar()
        ejecucion = EjecucionFlujo(workflow_id)
        self._ejecucion[workflow_id] = ejecucion
        ejecucion.tarea = asyncio.create_task(
            self._correr(ejecucion, operacion, al_terminar, traducir_error), name=f"flujo-{workflow_id}")
        return ejecucion

    async def _correr(self, ejecucion: EjecucionFlujo, operacion: Callable[[], Awaitable[Any]],
                      al_terminar: AlTerminar | None, traducir_error: TraducirError) -> None:
        wid = ejecucion.workflow_id
        resultado: dict[str, Any]
        try:
            with escuchar(lambda evento: self._agregar(ejecucion, evento)):
                if self._semaforo.locked():
                    self._en_espera.append(wid)
                    ejecucion.puesto = self._en_espera.index(wid) + 1
                    emitir("en_cola", puesto=ejecucion.puesto)
                async with self._semaforo:
                    if wid in self._en_espera:
                        self._en_espera.remove(wid)
                    emitir("inicio")
                    salida = await operacion()
                mirando = bool(ejecucion.suscriptores)
                extra = None
                if al_terminar is not None:
                    try:
                        extra = await _llamar(al_terminar, salida, mirando)
                    except Exception as aviso:
                        # Los avisos de después nunca cambian el resultado del flujo.
                        logger.warning("al_terminar_fallido", extra={"event": "al_terminar_fallido", "error": type(aviso).__name__})
                resultado = {"estado": "listo", **(extra or {})}
        except asyncio.CancelledError:
            resultado = {"estado": "error", "error": {"code": "TURN_CANCELLED", "status": 499,
                                                       "message": "La ejecución se canceló.", "retryable": True}}
            self._terminar(ejecucion, resultado)
            raise
        except Exception as exc:
            if wid in self._en_espera:
                self._en_espera.remove(wid)
            logger.warning("flujo_en_segundo_plano_fallido", extra={
                "event": "flujo_en_segundo_plano_fallido", "workflow_id": str(wid), "error": type(exc).__name__})
            try:
                error = traducir_error(exc)
            except Exception as traduccion:
                logger.error("error_no_traducido", extra={"event": "error_no_traducido", "error": type(traduccion).__name__})
                error = {"code": "INTERNAL_ERROR", "status": 500, "message": "Ocurrió un error inesperado.", "retryable": True}
            resultado = {"estado": "error", "error": error}
        self._terminar(ejecucion, resultado)

    def _terminar(self, ejecucion: EjecucionFlujo, resultado: dict[str, Any]) -> None:
        ejecucion.resultado = resultado
        ejecucion.terminado_en = time.monotonic()
        self._agregar(ejecucion, {"tipo": "fin", "momento": _ahora(), **resultado})
        # Los que siguen en la cola avanzan un puesto (solo se avisa si el puesto cambió).
        for wid, otra in self._ejecucion.items():
            if wid in self._en_espera and otra.en_curso:
                puesto = self._en_espera.index(wid) + 1
                if puesto != otra.puesto:
                    otra.puesto = puesto
                    self._agregar(otra, {"tipo": "en_cola", "momento": _ahora(), "puesto": puesto})

    async def cerrar(self) -> None:
        """Al apagar el servicio: se cancelan las ejecuciones (lo hecho queda en el último punto guardado)."""
        tareas = [e.tarea for e in self._ejecucion.values() if e.tarea is not None and not e.tarea.done()]
        for tarea in tareas:
            tarea.cancel()
        if tareas:
            await asyncio.gather(*tareas, return_exceptions=True)


def _ahora() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


async def _llamar(funcion: AlTerminar, salida: Any, mirando: bool) -> dict[str, Any] | None:
    respuesta = funcion(salida, mirando)
    if asyncio.iscoroutine(respuesta):
        respuesta = await respuesta
    return respuesta
