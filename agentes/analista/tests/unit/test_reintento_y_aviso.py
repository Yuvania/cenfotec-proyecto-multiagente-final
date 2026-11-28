"""Reintentos automáticos, aviso de fallo a quien creó la historia y fiabilidad por agente."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from agentes.analista.api.routes.workflows import _translate_runtime_error
from agentes.analista.core import reintento
from agentes.analista.core.aviso_fallo import detalle_fallo, es_fallo_de_agente
from agentes.analista.core.models import AgentTurnResponse, Analysis, ErrorCode
from agentes.analista.core.opencode_client import OpenCodeClientError
from agentes.analista.core.workflow_graph import WorkflowRuntime
from agentes.analista.core.workflow_models import FlowMode, WorkflowCreateRequest
from agentes.analista.memory.repositorio import RepositorioHU
from agentes.metricas.metricas_service import MetricasService
from agentes.metricas.registro_consumo import (
    ContextoConsumo, TurnoAgente, agregar_registrador_turno, quitar_registrador_turno,
)
from agentes.metricas.repositorio_consumo import RepositorioConsumo


def _caido() -> OpenCodeClientError:
    return OpenCodeClientError("OPENCODE_UNAVAILABLE", "detalle privado", retryable=True)


@pytest.fixture()
def esperas(monkeypatch):
    lista: list[float] = []

    async def anotar(segundos):
        lista.append(segundos)

    monkeypatch.setattr(reintento, "_dormir", anotar)
    monkeypatch.setattr(reintento, "_azar", lambda a, _b: a)  # sin azar: esperas exactas
    return lista


@pytest.fixture()
def turnos():
    lista: list[tuple[TurnoAgente, ContextoConsumo]] = []

    async def anotar(turno, contexto):
        lista.append((turno, contexto))

    agregar_registrador_turno(anotar)
    yield lista
    quitar_registrador_turno(anotar)


# --- Reintentos ----------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_un_fallo_pasajero_se_reintenta_con_espera_creciente(esperas, turnos):
    intentos = []

    async def agente():
        intentos.append(1)
        if len(intentos) < 3:
            raise _caido()
        return "listo"

    assert await reintento.con_reintento("analista", agente) == "listo"
    assert esperas == [2.0, 4.0]
    assert [(t.agente, t.exitoso, t.intentos) for t, _ in turnos] == [("analista", True, 3)]


@pytest.mark.asyncio
async def test_se_rinde_tras_tres_reintentos_y_deja_marcado_el_agente(esperas, turnos):
    async def agente():
        raise _caido()

    with pytest.raises(OpenCodeClientError) as error:
        await reintento.con_reintento("asesor_tecnico", agente)
    assert esperas == [2.0, 4.0, 8.0]
    assert (error.value.agente_fallido, error.value.intentos_agente) == ("asesor_tecnico", 4)
    turno = turnos[0][0]
    assert (turno.exitoso, turno.intentos, turno.codigo_error) == (False, 4, "OPENCODE_UNAVAILABLE")


@pytest.mark.asyncio
@pytest.mark.parametrize("codigo", ["OPENCODE_AUTH_FAILED", "MODEL_UNAVAILABLE", "AGENT_OUTPUT_INVALID"])
async def test_lo_que_no_se_arregla_solo_no_se_reintenta(esperas, codigo):
    llamadas = []

    async def agente():
        llamadas.append(1)
        raise OpenCodeClientError(codigo, "x", retryable=True)

    with pytest.raises(OpenCodeClientError):
        await reintento.con_reintento("analista", agente)
    assert llamadas == [1] and esperas == []


def test_cuota_solo_se_espera_si_vuelve_en_un_minuto_o_menos(monkeypatch):
    monkeypatch.setattr(reintento, "_azar", lambda a, _b: a)
    ahora = datetime(2030, 1, 1, 12, 0, tzinfo=UTC)
    pronto = OpenCodeClientError("OPENCODE_RATE_LIMITED", "x", retryable=True, retry_at=ahora + timedelta(seconds=40))
    tarde = OpenCodeClientError("OPENCODE_RATE_LIMITED", "x", retryable=True, retry_at=ahora + timedelta(minutes=25))
    decision = reintento.decidir(pronto, 0, ahora=ahora)
    assert decision.reintentar and decision.espera == pytest.approx(41.0)
    assert reintento.decidir(tarde, 0, ahora=ahora).reintentar is False


@pytest.mark.asyncio
async def test_no_empieza_un_reintento_que_pasa_el_tiempo_maximo(esperas, monkeypatch):
    reloj = iter([0.0, 300.0, 300.0, 300.0])
    monkeypatch.setattr(reintento, "_reloj", lambda: next(reloj))
    monkeypatch.setenv("REINTENTO_TIEMPO_MAXIMO_SEGUNDOS", "240")

    async def agente():
        raise _caido()

    with pytest.raises(OpenCodeClientError):
        await reintento.con_reintento("analista", agente)
    assert esperas == []


def test_la_api_devuelve_cuando_vuelve_la_cuota():
    vuelve = datetime(2030, 1, 1, 12, 25, tzinfo=UTC)
    error = _translate_runtime_error(OpenCodeClientError("OPENCODE_RATE_LIMITED", "privado", retryable=True, retry_at=vuelve))
    assert (error.code, error.status_code, error.retry_at) == (ErrorCode.OPENCODE_RATE_LIMITED, 503, vuelve)
    assert "privado" not in error.message


# --- Aviso de fallo ------------------------------------------------------------------------------------------
def test_el_aviso_dice_que_agente_fallo_por_que_y_cuando_vuelve_la_cuota(monkeypatch):
    monkeypatch.setenv("ZONA_HORARIA", "America/Costa_Rica")
    error = _caido()
    error.intentos_agente = 4
    texto = detalle_fallo(error, agente="asesor_tecnico")
    assert texto.startswith("Asesor Técnico no pudo terminar: el proveedor del modelo no respondió.")
    assert "Se intentó 4 veces de forma automática." in texto and "Retomar" in texto
    assert "privado" not in texto

    ahora = datetime(2030, 1, 1, 21, 0, tzinfo=UTC)
    cuota = OpenCodeClientError("OPENCODE_RATE_LIMITED", "x", retry_at=ahora + timedelta(minutes=40))
    assert "La cuota vuelve a las 3:40 p. m." in detalle_fallo(cuota, agente="analista", ahora=ahora)
    assert "Avise a quien administra" in detalle_fallo(OpenCodeClientError("OPENCODE_AUTH_FAILED", "x"), agente="analista")


def test_una_respuesta_equivocada_de_la_persona_no_es_un_fallo_del_agente():
    assert es_fallo_de_agente(_caido())
    assert not es_fallo_de_agente(ValueError("La respuesta no coincide con la interrupción pendiente."))


def _respuesta_analista() -> AgentTurnResponse:
    return AgentTurnResponse(
        conversation_id=uuid4(), request_id=uuid4(), turn_id=uuid4(), estado="completado", respuesta_markdown="Listo.",
        analisis=Analysis(conocida=[], faltante=["Plazo"], supuesta=[], ambigua=[]), preguntas=[],
        fuentes_consultadas=[], listo_para_redactor=False, limitaciones=[], duracion_ms=1, prompt_version="1.0.0",
    )


@pytest.mark.asyncio
async def test_el_creador_recibe_un_solo_aviso_y_se_cierra_cuando_el_flujo_vuelve_a_andar(tmp_path, turnos):
    repositorio = RepositorioHU(tmp_path / "flujo.db")
    estado = {"caido": True}

    async def analista(_state):
        if estado["caido"]:
            raise _caido()
        return _respuesta_analista()

    async def asesor(_state):
        return {"affected_modules": [], "dependencies": [], "risks": [], "critical_processes": [],
                "consulted_sources": [], "uncertainties": []}

    runtime = WorkflowRuntime(analyst=analista, advisor=asesor, persistencia=repositorio)
    pedido = WorkflowCreateRequest(mode=FlowMode.PRE_GROOMING, requirement="Consultar saldos", titulo="Consulta de saldos",
                                   creado_por="Ana", creado_por_usuario="u-ana")
    with pytest.raises(OpenCodeClientError):
        await runtime.execute(pedido)
    [aviso] = repositorio.listar_aviso("u-ana")
    assert (aviso["tipo"], aviso["titulo"], aviso["leido"]) == ("fallo", "Consulta de saldos", False)
    assert aviso["detalle"].startswith("Agente Analista no pudo terminar")
    flujo = aviso["workflow_id"]

    with pytest.raises(OpenCodeClientError):
        await runtime.reintentar(flujo)
    assert len(repositorio.listar_aviso("u-ana")) == 1  # no se repite mientras no lo lea

    estado["caido"] = False
    await runtime.reintentar(flujo)
    assert repositorio.listar_aviso("u-ana")[0]["leido"] is True  # se cerró solo
    assert [t.exitoso for t, _ in turnos][-1] is True


# --- Fiabilidad por agente ------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fiabilidad_por_agente_en_el_panel(tmp_path):
    servicio = MetricasService(RepositorioConsumo(RepositorioHU(tmp_path / "m.db").motor))
    contexto = ContextoConsumo(workflow_id="w1", historia_id="w1", modo="creacion")
    for turno in (
        TurnoAgente("analista", True, 1, 30_000), TurnoAgente("analista", True, 2, 50_000),
        TurnoAgente("analista", False, 4, 120_000, "OPENCODE_UNAVAILABLE"), TurnoAgente("redactor_revisor", True, 1, 20_000),
    ):
        await servicio.registrar_turno(turno, contexto)
    fiabilidad = {item["agente"]: item for item in servicio.panel("todo")["fiabilidad"]}
    analista = fiabilidad["analista"]
    assert (analista["turnos"], analista["fallidos"], analista["con_reintento"], analista["reintentos"]) == (3, 1, 2, 4)
    assert analista["tasa_fallo"] == pytest.approx(33.3)
    assert (analista["duracion_promedio_ms"], analista["duracion_maxima_ms"]) == (66_667, 120_000)
    assert analista["nombre"] == "Agente Analista"
    assert fiabilidad["redactor_revisor"]["tasa_fallo"] == 0.0
