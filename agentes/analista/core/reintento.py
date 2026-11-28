"""Reintentos automáticos de un agente, con espera creciente y algo de azar.

Regla (saber cuándo dejar de insistir):

- **Fallos pasajeros** (tiempo agotado, proveedor del modelo caído): hasta 3 reintentos, esperando unos 2, 4 y
  8 segundos, más un poco de azar para que varios flujos no reintenten todos a la vez.
- **Cuota agotada**: se espera solo si OpenCode dice que vuelve en un minuto o menos. Si tarda más, no se insiste:
  el error sube con la hora en que vuelve (la pantalla la muestra y le llega el aviso a quien creó la historia).
- **Fallos que no se arreglan solos** (clave inválida, modelo inexistente, respuesta sin el formato pedido,
  errores del propio sistema): no se reintentan.
- **Tiempo máximo**: no se empieza un reintento si el paso ya lleva más de ``REINTENTO_TIEMPO_MAXIMO_SEGUNDOS``
  (240 por defecto), para que la persona no espere indefinidamente.

Cada turno queda registrado (agente, si respondió, intentos, duración y código del error) para la fiabilidad por
agente en Mantenimiento › Consumo del modelo y Mantenimiento › Observabilidad.
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, TypeVar

from agentes.analista.core.avance import emitir
from agentes.metricas.registro_consumo import TurnoAgente, registrar_turno

logger = logging.getLogger(__name__)

_T = TypeVar("_T")

ESPERA_SEGUNDO: tuple[float, ...] = (2.0, 4.0, 8.0)
AZAR_PROPORCION = 0.25  # hasta un 25 % más de espera, al azar
ESPERA_CUOTA_MAXIMA_SEGUNDO = 60.0
TIEMPO_MAXIMO_PREDETERMINADO = 240.0
CODIGO_PASAJERO = frozenset({"TURN_TIMEOUT", "OPENCODE_UNAVAILABLE", "WORKFLOW_TIMEOUT"})
CODIGO_CUOTA = "OPENCODE_RATE_LIMITED"

# Costuras de prueba: el reloj, la espera y el azar se pueden sustituir.
_dormir: Callable[[float], Awaitable[Any]] = asyncio.sleep
_reloj: Callable[[], float] = time.monotonic
_azar: Callable[[float, float], float] = random.uniform


@dataclass(frozen=True, slots=True)
class Decision:
    reintentar: bool
    espera: float = 0.0
    motivo: str = ""


def codigo_de(exc: BaseException) -> str:
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return "TURN_TIMEOUT"
    codigo = getattr(exc, "code", None)
    codigo = getattr(codigo, "value", codigo)
    return str(codigo) if codigo else type(exc).__name__


def tiempo_maximo() -> float:
    valor = os.environ.get("REINTENTO_TIEMPO_MAXIMO_SEGUNDOS", "").strip()
    try:
        return max(10.0, float(valor)) if valor else TIEMPO_MAXIMO_PREDETERMINADO
    except ValueError:
        logger.warning("tiempo_reintento_invalido", extra={"event": "tiempo_reintento_invalido"})
        return TIEMPO_MAXIMO_PREDETERMINADO


def decidir(exc: BaseException, intento: int, *, ahora: datetime | None = None) -> Decision:
    """¿Se reintenta este error? ``intento`` = reintentos ya hechos (0 = falló el primer intento)."""
    if intento >= len(ESPERA_SEGUNDO):
        return Decision(False, motivo="sin_reintentos")
    codigo = codigo_de(exc)
    base = ESPERA_SEGUNDO[intento]
    if codigo in CODIGO_PASAJERO:
        return Decision(True, base + _azar(0, base * AZAR_PROPORCION), "pasajero")
    if codigo == CODIGO_CUOTA:
        vuelve = getattr(exc, "retry_at", None)
        if vuelve is None:
            return Decision(True, base + _azar(0, base * AZAR_PROPORCION), "cuota_sin_hora")
        faltan = (vuelve - (ahora or datetime.now(UTC))).total_seconds()
        if faltan <= ESPERA_CUOTA_MAXIMA_SEGUNDO:
            return Decision(True, max(0.0, faltan) + _azar(1, 3), "cuota_vuelve_pronto")
        return Decision(False, motivo="cuota_tarda")
    return Decision(False, motivo="permanente")


def _marcar(exc: BaseException, agente: str, intentos: int) -> None:
    """Deja en el error qué agente falló y con cuántos intentos (para el aviso a quien creó la historia)."""
    try:
        exc.agente_fallido = agente  # type: ignore[attr-defined]
        exc.intentos_agente = intentos  # type: ignore[attr-defined]
    except AttributeError:
        logger.info("error_sin_atributos", extra={"event": "error_sin_atributos", "error": type(exc).__name__})


async def con_reintento(agente: str, operacion: Callable[[], Awaitable[_T]]) -> _T:
    """Ejecuta el turno de un agente y lo reintenta según la regla del módulo."""
    inicio = _reloj()
    limite = tiempo_maximo()
    intento = 0
    emitir("agente_inicio", agente=agente)
    while True:
        try:
            resultado = await operacion()
        except Exception as exc:
            decision = decidir(exc, intento)
            transcurrido = _reloj() - inicio
            if not decision.reintentar or transcurrido + decision.espera > limite:
                await registrar_turno(TurnoAgente(
                    agente=agente, exitoso=False, intentos=intento + 1,
                    duracion_ms=int((_reloj() - inicio) * 1000), codigo_error=codigo_de(exc),
                ))
                _marcar(exc, agente, intento + 1)
                emitir("agente_fin", agente=agente, exitoso=False, intentos=intento + 1,
                       duracion_ms=int((_reloj() - inicio) * 1000), codigo=codigo_de(exc))
                if intento:
                    logger.warning("agente_fallo_tras_reintentos", extra={
                        "event": "agente_fallo_tras_reintentos", "agente": agente, "intentos": intento + 1,
                        "error_code": codigo_de(exc), "motivo": decision.motivo or "tiempo_maximo",
                    })
                raise
            intento += 1
            logger.warning("agente_reintento", extra={
                "event": "agente_reintento", "agente": agente, "intento": intento, "error_code": codigo_de(exc),
                "espera_ms": int(decision.espera * 1000), "motivo": decision.motivo,
            })
            emitir("agente_reintento", agente=agente, intento=intento, de=len(ESPERA_SEGUNDO),
                   espera_ms=int(decision.espera * 1000), motivo=decision.motivo, codigo=codigo_de(exc))
            await _dormir(decision.espera)
            continue
        duracion = int((_reloj() - inicio) * 1000)
        await registrar_turno(TurnoAgente(agente=agente, exitoso=True, intentos=intento + 1, duracion_ms=duracion))
        emitir("agente_fin", agente=agente, exitoso=True, intentos=intento + 1, duracion_ms=duracion)
        return resultado
