"""Registro del consumo del modelo: cada respuesta de OpenCode trae sus tokens y su costo. También el resultado
de cada turno de un agente (si respondió, con cuántos intentos y cuánto tardó), para la fiabilidad por agente.

Cómo llega cada dato al registro, sin tocar a los agentes:

1. ``WorkflowRuntime`` abre un ``contexto_consumo`` (flujo, historia, título y modo) antes de ejecutar el grafo.
   Los nodos de LangGraph corren en tareas que copian ese contexto, así que cada agente lo hereda.
2. ``OpenCodeClient.wait_for_assistant`` lee los tokens y el costo de cada respuesta terminada (también de las
   que fallaron: igual se pagan) y llama a ``registrar_uso``.
3. ``registrar_uso`` le pasa el uso y el contexto a los registradores configurados al arrancar (la base de datos
   en la aplicación, una lista en memoria en el diagnóstico de pruebas). Si nadie se configuró, no hace nada.

Nunca se guarda lo que se le pidió al modelo ni lo que respondió: solo cantidades.
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

MODO_CREACION = "creacion"
MODO_CAMBIO = "cambio"
MODO_PRUEBA = "prueba"
MODO_OTRO = "otro"

# De dónde sale el costo: lo calculó OpenCode, se estimó con el precio del modelo o no hay precio.
ORIGEN_OPENCODE = "opencode"
ORIGEN_ESTIMADO = "estimado"
ORIGEN_SIN_PRECIO = "sin_precio"


@dataclass(frozen=True, slots=True)
class ContextoConsumo:
    """A qué trabajo pertenece una llamada al modelo."""

    workflow_id: str | None = None
    historia_id: str | None = None
    titulo: str | None = None
    modo: str = MODO_OTRO


@dataclass(frozen=True, slots=True)
class UsoModelo:
    """Lo que costó una respuesta del modelo. Solo cantidades, nunca contenido."""

    mensaje_id: str
    agente: str
    proveedor: str
    modelo: str
    tokens_entrada: int = 0
    tokens_salida: int = 0
    tokens_razonamiento: int = 0
    tokens_cache_lectura: int = 0
    tokens_cache_escritura: int = 0
    costo_usd: float = 0.0
    costo_origen: str = ORIGEN_SIN_PRECIO
    duracion_ms: int | None = None
    exitosa: bool = True
    creado_en: str = field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="milliseconds"))

    @property
    def tokens_total(self) -> int:
        return (self.tokens_entrada + self.tokens_salida + self.tokens_razonamiento
                + self.tokens_cache_lectura + self.tokens_cache_escritura)

    def como_dict(self) -> dict[str, Any]:
        return asdict(self) | {"tokens_total": self.tokens_total}


@dataclass(frozen=True, slots=True)
class TurnoAgente:
    """Cómo terminó el turno de un agente en el flujo: si respondió, cuántos intentos usó y cuánto tardó."""

    agente: str
    exitoso: bool
    intentos: int
    duracion_ms: int
    codigo_error: str | None = None
    creado_en: str = field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="milliseconds"))


@dataclass(frozen=True, slots=True)
class LlamadaHerramienta:
    """Una consulta de un agente a su servidor MCP: cuál herramienta, cómo terminó y cuánto tardó."""

    agente: str
    herramienta: str
    estado: str  # ok | timeout | error | rechazada
    duracion_ms: int
    creado_en: str = field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="milliseconds"))


class PresupuestoAgotadoError(RuntimeError):
    """Kill-switch financiero: la historia o el mes alcanzaron su tope de gasto. El flujo se congela y pasa
    a una persona; no se reintenta solo."""

    def __init__(self, alcance: str, limite_usd: float, gastado_usd: float) -> None:
        self.alcance = alcance  # historia | mes
        self.limite_usd = limite_usd
        self.gastado_usd = gastado_usd
        if alcance == ALCANCE_MES:
            mensaje = (f"Se alcanzó el tope de gasto del mes (US${limite_usd:,.2f}). Los agentes se detienen hasta el "
                       "próximo mes o hasta que quien administra la aplicación suba el tope.")
        else:
            mensaje = (f"Esta historia alcanzó su tope de gasto (US${limite_usd:,.2f}). El avance quedó guardado; "
                       "termínela a mano o pida a quien administra la aplicación que revise el consumo.")
        super().__init__(mensaje)


ALCANCE_HISTORIA = "historia"
ALCANCE_MES = "mes"

Registrador = Callable[[UsoModelo, ContextoConsumo], Awaitable[None]]
RegistradorTurno = Callable[[TurnoAgente, ContextoConsumo], Awaitable[None]]
RegistradorHerramienta = Callable[[LlamadaHerramienta, ContextoConsumo], Awaitable[None]]
# Revisa el presupuesto antes de cada llamada al modelo; lanza PresupuestoAgotadoError si se pasó.
Guardian = Callable[[ContextoConsumo], Awaitable[None]]

_contexto: ContextVar[ContextoConsumo] = ContextVar("contexto_consumo", default=ContextoConsumo())
_lista_registrador: list[Registrador] = []
_lista_registrador_turno: list[RegistradorTurno] = []
_lista_registrador_herramienta: list[RegistradorHerramienta] = []
_lista_guardian: list[Guardian] = []


@contextmanager
def contexto_consumo(**valores: Any) -> Iterator[ContextoConsumo]:
    """Asocia las llamadas al modelo que ocurran dentro del bloque a un flujo o historia."""
    contexto = ContextoConsumo(**valores)
    marca = _contexto.set(contexto)
    try:
        yield contexto
    finally:
        _contexto.reset(marca)


def contexto_actual() -> ContextoConsumo:
    return _contexto.get()


def agregar_registrador(registrador: Registrador) -> None:
    if registrador not in _lista_registrador:
        _lista_registrador.append(registrador)


def quitar_registrador(registrador: Registrador) -> None:
    if registrador in _lista_registrador:
        _lista_registrador.remove(registrador)


async def registrar_uso(uso: UsoModelo) -> None:
    """Entrega el uso a cada registrador. Un fallo al registrar nunca detiene al agente."""
    contexto = _contexto.get()
    for registrador in list(_lista_registrador):
        try:
            await registrador(uso, contexto)
        except Exception as exc:
            logger.warning("consumo_no_registrado", extra={
                "event": "consumo_no_registrado", "error": type(exc).__name__, "agente": uso.agente,
            })


def agregar_registrador_turno(registrador: RegistradorTurno) -> None:
    if registrador not in _lista_registrador_turno:
        _lista_registrador_turno.append(registrador)


def quitar_registrador_turno(registrador: RegistradorTurno) -> None:
    if registrador in _lista_registrador_turno:
        _lista_registrador_turno.remove(registrador)


async def registrar_turno(turno: TurnoAgente) -> None:
    """Entrega el resultado del turno de un agente (para la fiabilidad por agente). Nunca detiene el flujo."""
    contexto = _contexto.get()
    for registrador in list(_lista_registrador_turno):
        try:
            await registrador(turno, contexto)
        except Exception as exc:
            logger.warning("turno_no_registrado", extra={
                "event": "turno_no_registrado", "error": type(exc).__name__, "agente": turno.agente,
            })


def agregar_registrador_herramienta(registrador: RegistradorHerramienta) -> None:
    if registrador not in _lista_registrador_herramienta:
        _lista_registrador_herramienta.append(registrador)


def quitar_registrador_herramienta(registrador: RegistradorHerramienta) -> None:
    if registrador in _lista_registrador_herramienta:
        _lista_registrador_herramienta.remove(registrador)


async def registrar_herramienta(llamada: LlamadaHerramienta) -> None:
    """Entrega una consulta MCP (para la latencia por herramienta). Nunca detiene al agente."""
    contexto = _contexto.get()
    for registrador in list(_lista_registrador_herramienta):
        try:
            await registrador(llamada, contexto)
        except Exception as exc:
            logger.warning("herramienta_no_registrada", extra={
                "event": "herramienta_no_registrada", "error": type(exc).__name__, "agente": llamada.agente,
            })


def agregar_guardian(guardian: Guardian) -> None:
    if guardian not in _lista_guardian:
        _lista_guardian.append(guardian)


def quitar_guardian(guardian: Guardian) -> None:
    if guardian in _lista_guardian:
        _lista_guardian.remove(guardian)


async def verificar_presupuesto() -> None:
    """Antes de cada llamada al modelo: si la historia o el mes pasaron su tope, lanza PresupuestoAgotadoError.

    Si la revisión misma falla (por ejemplo, la base no responde), se registra y se deja pasar: el tope de
    OpenCode Go sigue protegiendo el gasto real.
    """
    contexto = _contexto.get()
    for guardian in list(_lista_guardian):
        try:
            await guardian(contexto)
        except PresupuestoAgotadoError:
            raise
        except Exception as exc:
            logger.warning("presupuesto_no_verificado", extra={
                "event": "presupuesto_no_verificado", "error": type(exc).__name__,
            })


# --- Lectura de la respuesta de OpenCode --------------------------------------------------------------
def _entero(valor: Any) -> int:
    if isinstance(valor, bool) or not isinstance(valor, (int, float)) or valor < 0:
        return 0
    return int(valor)


def _numero(valor: Any) -> float | None:
    if isinstance(valor, bool) or not isinstance(valor, (int, float)) or valor < 0:
        return None
    return float(valor)


def _precio_vigente(precio: Any) -> Mapping[str, Any] | None:
    """OpenCode anuncia el precio por millón de tokens, a veces como lista de tramos: se usa el primero."""
    if isinstance(precio, list):
        precio = next((tramo for tramo in precio if isinstance(tramo, Mapping)), None)
    return precio if isinstance(precio, Mapping) else None


def estimar_costo(tokens: Mapping[str, int], precio: Any) -> float | None:
    """Costo en USD con el precio del modelo (USD por millón de tokens). None si no hay precio."""
    vigente = _precio_vigente(precio)
    if vigente is None:
        return None
    cache = vigente.get("cache") if isinstance(vigente.get("cache"), Mapping) else {}
    tarifa = {
        "entrada": _numero(vigente.get("input")),
        "salida": _numero(vigente.get("output")),
        "cache_lectura": _numero(cache.get("read")),
        "cache_escritura": _numero(cache.get("write")),
    }
    if tarifa["entrada"] is None and tarifa["salida"] is None:
        return None
    # El razonamiento se cobra como salida.
    total = (
        tokens["entrada"] * (tarifa["entrada"] or 0)
        + (tokens["salida"] + tokens["razonamiento"]) * (tarifa["salida"] or 0)
        + tokens["cache_lectura"] * (tarifa["cache_lectura"] or 0)
        + tokens["cache_escritura"] * (tarifa["cache_escritura"] or 0)
    )
    return total / 1_000_000


def uso_desde_mensaje(record: Mapping[str, Any], *, precio: Any = None, agente: str | None = None) -> UsoModelo | None:
    """Arma el uso de un mensaje ``assistant`` terminado de OpenCode v2 (Session.Message.Assistant)."""
    mensaje_id = record.get("id")
    if not isinstance(mensaje_id, str) or not mensaje_id:
        return None
    datos_token = record.get("tokens") if isinstance(record.get("tokens"), Mapping) else {}
    cache = datos_token.get("cache") if isinstance(datos_token.get("cache"), Mapping) else {}
    tokens = {
        "entrada": _entero(datos_token.get("input")),
        "salida": _entero(datos_token.get("output")),
        "razonamiento": _entero(datos_token.get("reasoning")),
        "cache_lectura": _entero(cache.get("read")),
        "cache_escritura": _entero(cache.get("write")),
    }
    costo = _numero(record.get("cost"))
    if costo is not None and costo > 0:
        origen = ORIGEN_OPENCODE
    else:
        estimado = estimar_costo(tokens, precio)
        if estimado is not None:
            costo, origen = estimado, ORIGEN_ESTIMADO
        elif costo is not None:
            # OpenCode informó costo cero y el modelo no anuncia precio (por ejemplo, un modelo gratuito).
            origen = ORIGEN_OPENCODE
        else:
            costo, origen = 0.0, ORIGEN_SIN_PRECIO
    modelo = record.get("model") if isinstance(record.get("model"), Mapping) else {}
    tiempo = record.get("time") if isinstance(record.get("time"), Mapping) else {}
    creado, completado = tiempo.get("created"), tiempo.get("completed")
    duracion = (
        int(completado - creado)
        if isinstance(creado, (int, float)) and isinstance(completado, (int, float)) and completado >= creado
        else None
    )
    return UsoModelo(
        mensaje_id=mensaje_id[:80],
        agente=str(record.get("agent") or agente or "desconocido")[:40],
        proveedor=str(modelo.get("providerID") or "")[:60],
        modelo=str(modelo.get("id") or modelo.get("modelID") or "")[:160],
        tokens_entrada=tokens["entrada"],
        tokens_salida=tokens["salida"],
        tokens_razonamiento=tokens["razonamiento"],
        tokens_cache_lectura=tokens["cache_lectura"],
        tokens_cache_escritura=tokens["cache_escritura"],
        costo_usd=round(float(costo), 8),
        costo_origen=origen,
        duracion_ms=duracion,
        exitosa=not (record.get("finish") == "error" or record.get("error")),
    )


class AcumuladorConsumo:
    """Registrador en memoria: suma el consumo de un proceso corto (por ejemplo, el diagnóstico de pruebas)."""

    def __init__(self) -> None:
        self.lista_uso: list[UsoModelo] = []

    async def __call__(self, uso: UsoModelo, contexto: ContextoConsumo) -> None:
        if all(existente.mensaje_id != uso.mensaje_id for existente in self.lista_uso):
            self.lista_uso.append(uso)

    def resumen(self) -> dict[str, Any]:
        return resumir(self.lista_uso)


def resumir(lista_uso: list[UsoModelo]) -> dict[str, Any]:
    """Totales de una lista de usos: llamadas, tokens por tipo y costo."""
    return {
        "llamadas": len(lista_uso),
        "tokens_entrada": sum(uso.tokens_entrada for uso in lista_uso),
        "tokens_salida": sum(uso.tokens_salida for uso in lista_uso),
        "tokens_razonamiento": sum(uso.tokens_razonamiento for uso in lista_uso),
        "tokens_cache": sum(uso.tokens_cache_lectura + uso.tokens_cache_escritura for uso in lista_uso),
        "tokens_total": sum(uso.tokens_total for uso in lista_uso),
        "costo_usd": round(sum(uso.costo_usd for uso in lista_uso), 8),
    }
