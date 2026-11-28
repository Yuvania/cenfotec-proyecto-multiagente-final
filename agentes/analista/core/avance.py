"""Eventos de avance de un flujo: qué agente trabaja, qué consulta, si reintenta y cuándo termina.

Los emiten los agentes sin saber quién escucha (``emitir``). Quien ejecuta el flujo en segundo plano abre
``escuchar`` alrededor de la ejecución y recibe cada evento (ver ``segundo_plano.py``). Fuera de eso, ``emitir``
no hace nada. Los eventos solo llevan nombres y cantidades, nunca lo que el modelo generó.
"""
from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

Oyente = Callable[[dict[str, Any]], None]

_oyente: ContextVar[Oyente | None] = ContextVar("oyente_avance", default=None)


@contextmanager
def escuchar(oyente: Oyente) -> Iterator[None]:
    marca = _oyente.set(oyente)
    try:
        yield
    finally:
        _oyente.reset(marca)


def emitir(tipo: str, **datos: Any) -> None:
    oyente = _oyente.get()
    if oyente is None:
        return
    try:
        oyente({"tipo": tipo, "momento": datetime.now(UTC).isoformat(timespec="milliseconds"), **datos})
    except Exception as exc:
        logger.warning("avance_no_emitido", extra={"event": "avance_no_emitido", "tipo": tipo, "error": type(exc).__name__})
