"""Métricas del consumo del modelo: lectura de OpenCode, contexto por historia, tabla, panel y API."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from agentes.analista.api.errors import install_error_handlers
from agentes.analista.api.routes import metricas as rutas_metricas
from agentes.analista.core.models import AgentTurnResponse, Analysis
from agentes.analista.core.opencode_client import OpenCodeClient, OpenCodeSettings
from agentes.analista.core.workflow_graph import WorkflowRuntime
from agentes.analista.core.workflow_models import FlowMode, WorkflowCreateRequest
from agentes.analista.memory.repositorio import RepositorioHU
from agentes.metricas.metricas_service import MetricasService
from agentes.metricas.registro_consumo import (
    MODO_CAMBIO, MODO_CREACION, ORIGEN_ESTIMADO, ORIGEN_OPENCODE, ORIGEN_SIN_PRECIO, AcumuladorConsumo,
    ContextoConsumo, UsoModelo, agregar_registrador, contexto_consumo, quitar_registrador, registrar_uso,
    uso_desde_mensaje,
)
from agentes.metricas.repositorio_consumo import RepositorioConsumo
from agentes.pruebas.pruebas_service import PruebasService, ResumenEjecucion
from agentes.pruebas.repositorio_pruebas import RepositorioPrueba
from agentes.seguridad.clave import FirmaSesion
from agentes.seguridad.catalogo import ACCION, CODIGO_ACCION

PRECIO = [{"input": 0.5, "output": 2.0, "cache": {"read": 0.05, "write": 0.0}}]


def _mensaje(**cambios):
    base = {
        "id": "msg_1", "type": "assistant", "agent": "analista",
        "model": {"providerID": "opencode", "id": "glm-5.3-flash"},
        "time": {"created": 1_000, "completed": 3_500},
        "tokens": {"input": 1200, "output": 300, "reasoning": 100, "cache": {"read": 400, "write": 0}},
        "cost": 0.0021, "finish": "stop", "content": [{"type": "text", "text": "{}"}],
    }
    return base | cambios


def _uso(mensaje_id: str, agente: str = "analista", costo: float = 0.01, entrada: int = 100, salida: int = 50) -> UsoModelo:
    return UsoModelo(mensaje_id=mensaje_id, agente=agente, proveedor="opencode", modelo="glm-5.3-flash",
                     tokens_entrada=entrada, tokens_salida=salida, costo_usd=costo, costo_origen=ORIGEN_OPENCODE)


# --- Lectura de la respuesta de OpenCode ------------------------------------------------------------
def test_lee_tokens_costo_y_duracion_de_opencode():
    uso = uso_desde_mensaje(_mensaje())
    assert (uso.agente, uso.proveedor, uso.modelo) == ("analista", "opencode", "glm-5.3-flash")
    assert (uso.tokens_entrada, uso.tokens_salida, uso.tokens_razonamiento, uso.tokens_cache_lectura) == (1200, 300, 100, 400)
    assert uso.tokens_total == 2000
    assert uso.costo_usd == pytest.approx(0.0021)
    assert uso.costo_origen == ORIGEN_OPENCODE
    assert uso.duracion_ms == 2500
    assert uso.exitosa is True


def test_sin_costo_de_opencode_lo_estima_con_el_precio_del_modelo():
    uso = uso_desde_mensaje(_mensaje(cost=None), precio=PRECIO)
    # (1200 × 0,5 + (300 + 100) × 2 + 400 × 0,05) / 1 000 000
    assert uso.costo_usd == pytest.approx((1200 * 0.5 + 400 * 2.0 + 400 * 0.05) / 1_000_000)
    assert uso.costo_origen == ORIGEN_ESTIMADO


def test_sin_costo_ni_precio_queda_marcado_y_conserva_los_tokens():
    uso = uso_desde_mensaje(_mensaje(cost=None))
    assert (uso.costo_usd, uso.costo_origen, uso.tokens_total) == (0.0, ORIGEN_SIN_PRECIO, 2000)


def test_la_respuesta_fallida_tambien_cuenta_y_valores_raros_no_rompen():
    uso = uso_desde_mensaje(_mensaje(finish="error", error={"type": "x"}, tokens={"input": -3, "output": "mucho"}))
    assert uso.exitosa is False
    assert uso.tokens_total == 0
    assert uso_desde_mensaje({"type": "assistant"}) is None


# --- Contexto y registradores -------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_registrar_uso_entrega_el_contexto_y_un_registrador_que_falla_no_detiene_al_agente():
    recibido = []

    async def guardar(uso, contexto):
        recibido.append((uso.mensaje_id, contexto))

    async def fallar(_uso, _contexto):
        raise RuntimeError("base caída")

    agregar_registrador(fallar)
    agregar_registrador(guardar)
    try:
        with contexto_consumo(workflow_id="w1", historia_id="h1", modo=MODO_CAMBIO, titulo="Cambio"):
            await registrar_uso(_uso("m1"))
        await registrar_uso(_uso("m2"))
    finally:
        quitar_registrador(fallar)
        quitar_registrador(guardar)
    assert recibido[0] == ("m1", ContextoConsumo(workflow_id="w1", historia_id="h1", titulo="Cambio", modo=MODO_CAMBIO))
    assert recibido[1][1] == ContextoConsumo()


@pytest.mark.asyncio
async def test_el_acumulador_suma_sin_repetir_mensajes():
    acumulador = AcumuladorConsumo()
    for uso in (_uso("a", costo=0.01), _uso("a", costo=0.01), _uso("b", costo=0.02, entrada=10, salida=5)):
        await acumulador(uso, ContextoConsumo())
    resumen = acumulador.resumen()
    assert (resumen["llamadas"], resumen["tokens_total"]) == (2, 165)
    assert resumen["costo_usd"] == pytest.approx(0.03)


@pytest.mark.asyncio
async def test_el_cliente_de_opencode_registra_cada_respuesta_con_el_precio_del_modelo():
    respuestas = {
        "/api/model": {"data": [{"providerID": "opencode", "modelID": "glm-5.3-flash", "enabled": True, "cost": PRECIO}]},
        "/api/session/s1/message": {"data": [_mensaje(cost=None)]},
    }
    transporte = httpx.MockTransport(lambda request: httpx.Response(200, json=respuestas[request.url.path]))
    acumulador = AcumuladorConsumo()
    agregar_registrador(acumulador)
    try:
        async with httpx.AsyncClient(base_url="http://opencode.test", transport=transporte) as http:
            cliente = OpenCodeClient(OpenCodeSettings(
                _env_file=None, server_password=SecretStr("test-only"),
                opencode_provider_id="opencode", opencode_model_id="glm-5.3-flash",
            ), client=http)
            await cliente.select_model()
            generado = await cliente.wait_for_assistant("s1", deadline=asyncio.get_running_loop().time() + 5)
    finally:
        quitar_registrador(acumulador)
    assert generado["tokens"]["input"] == 1200
    [uso] = acumulador.lista_uso
    assert uso.costo_origen == ORIGEN_ESTIMADO
    assert uso.costo_usd > 0


# --- El flujo asocia el consumo a su historia -------------------------------------------------------
@pytest.mark.asyncio
async def test_cada_agente_del_flujo_hereda_el_flujo_y_la_historia():
    recibido: list[ContextoConsumo] = []

    async def guardar(_uso, contexto):
        recibido.append(contexto)

    async def analista(_state):
        await registrar_uso(_uso("analista-1"))
        return AgentTurnResponse(
            conversation_id=uuid4(), request_id=uuid4(), turn_id=uuid4(), estado="completado",
            respuesta_markdown="Análisis.", analisis=Analysis(conocida=[], faltante=["Plazo"], supuesta=[], ambigua=[]),
            preguntas=[], fuentes_consultadas=[], listo_para_redactor=False, limitaciones=[], duracion_ms=1,
            prompt_version="1.0.0",
        )

    async def asesor(_state):
        return {"affected_modules": [], "dependencies": [], "risks": [], "critical_processes": [],
                "consulted_sources": [], "uncertainties": []}

    agregar_registrador(guardar)
    try:
        runtime = WorkflowRuntime(analyst=analista, advisor=asesor)
        resultado = await runtime.execute(WorkflowCreateRequest(
            mode=FlowMode.PRE_GROOMING, requirement="Consultar saldos", titulo="Consulta de saldos",
        ))
    finally:
        quitar_registrador(guardar)
    flujo = str(resultado.workflow_id)
    assert recibido == [ContextoConsumo(workflow_id=flujo, historia_id=flujo, titulo="Consulta de saldos", modo=MODO_CREACION)]


# --- Tabla y panel --------------------------------------------------------------------------------------
@pytest.fixture()
def metricas(tmp_path):
    motor = RepositorioHU(tmp_path / "m.db").motor
    pruebas = PruebasService(RepositorioPrueba(motor))
    return MetricasService(RepositorioConsumo(motor), consumo_prueba=pruebas.consumo_desde), pruebas


@pytest.mark.asyncio
async def test_panel_por_agente_por_flujo_y_promedio_por_historia(metricas):
    servicio, _ = metricas
    creacion_a = ContextoConsumo(workflow_id="wa", historia_id="wa", titulo="HU A", modo=MODO_CREACION)
    creacion_b = ContextoConsumo(workflow_id="wb", historia_id="wb", titulo="HU B", modo=MODO_CREACION)
    cambio_a = ContextoConsumo(workflow_id="wc", historia_id="wa", titulo="Cambio A", modo=MODO_CAMBIO)
    await servicio.registrar(_uso("1", "analista", 0.01), creacion_a)
    await servicio.registrar(_uso("2", "redactor_revisor", 0.03), creacion_a)
    await servicio.registrar(_uso("2", "redactor_revisor", 0.03), creacion_a)  # repetida: cuenta una vez
    await servicio.registrar(_uso("3", "analista", 0.02), creacion_b)
    await servicio.registrar(_uso("4", "gestor_cambios", 0.05), cambio_a)

    panel = servicio.panel("todo")
    assert panel["total"]["llamadas"] == 4
    assert panel["total"]["costo_usd"] == pytest.approx(0.11)
    assert panel["total"]["tokens_total"] == 600
    assert [(a["agente"], a["nombre"]) for a in panel["por_agente"]][0] == ("gestor_cambios", "Gestor de Cambios")
    assert panel["promedio_creacion"] == {"flujos": 2, "costo_usd": pytest.approx(0.03), "tokens_total": 225, "llamadas": 1.5}
    assert panel["promedio_cambio"]["flujos"] == 1
    assert {f["workflow_id"]: f["costo_usd"] for f in panel["por_flujo"]} == pytest.approx({"wa": 0.04, "wb": 0.02, "wc": 0.05})
    assert panel["aviso_costo"] is None

    historia = servicio.historia("wa")
    assert historia["total"]["costo_usd"] == pytest.approx(0.09)  # creación + cambio
    assert len(historia["por_flujo"]) == 2


def test_periodo_invalido(metricas):
    servicio, _ = metricas
    with pytest.raises(ValueError):
        servicio.panel("90")


@pytest.mark.asyncio
async def test_avisa_cuando_el_costo_es_estimado(metricas):
    servicio, _ = metricas
    estimado = UsoModelo(mensaje_id="e", agente="analista", proveedor="opencode", modelo="m", tokens_entrada=10,
                         costo_usd=0.001, costo_origen=ORIGEN_ESTIMADO)
    await servicio.registrar(estimado, ContextoConsumo())
    assert "estimado" in servicio.panel("7")["aviso_costo"]


def test_el_panel_suma_el_consumo_del_agente_de_pruebas(metricas):
    servicio, pruebas = metricas
    ejecucion = pruebas.repositorio.crear(alcance="regresion", navegador="chromium", ambiente="pruebas", casos=None,
                                          repositorio="equipo/app", iniciada_por="Ana", iniciada_por_usuario="a")
    resumen = ResumenEjecucion.model_validate({"total": 1, "fallidos": 1, "consumo": {
        "llamadas": 6, "tokens_total": 9000, "costo_usd": 0.012}})
    pruebas.repositorio.actualizar(ejecucion["id"], estado="con_fallos", resumen=resumen.model_dump(),
                                   finalizado_en="2999-01-01T00:00:00.000+00:00")
    assert servicio.panel("todo")["prueba"] == {
        "ejecuciones": 1, "llamadas": 6, "tokens_entrada": 0, "tokens_salida": 0, "tokens_razonamiento": 0,
        "tokens_cache": 0, "tokens_total": 9000, "costo_usd": 0.012,
    }
    assert ResumenEjecucion.model_validate({"consumo": {"llamadas": -1}}).consumo is None


# --- API y permiso ---------------------------------------------------------------------------------------
def _cliente(servicio, acciones):
    usuario = {"id": "u", "nombre": "Ana", "usuario": "ana", "activo": True, "roles": [], "acciones": acciones}
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(rutas_metricas.router, prefix="/api/analista")
    app.state.metricas = servicio
    app.state.seguridad = SimpleNamespace(obtener_usuario=lambda _id: usuario)
    app.state.firma_sesion = FirmaSesion("prueba")
    cliente = TestClient(app)
    cliente.headers["Authorization"] = f"Bearer {app.state.firma_sesion.emitir(usuario['id'])}"
    return cliente


def test_la_api_exige_la_accion_de_metricas(metricas):
    servicio, _ = metricas
    assert ACCION.METRICA_VER in CODIGO_ACCION
    sin_permiso = _cliente(servicio, [ACCION.HISTORIA_VER])
    assert sin_permiso.get("/api/analista/metricas/consumo").status_code == 403
    con_permiso = _cliente(servicio, [ACCION.METRICA_VER])
    respuesta = con_permiso.get("/api/analista/metricas/consumo?periodo=7")
    assert respuesta.status_code == 200
    assert respuesta.json()["lista_periodo"][0]["codigo"] == "7"
    assert con_permiso.get("/api/analista/metricas/consumo?periodo=x").status_code == 400
    assert con_permiso.get("/api/analista/metricas/consumo/historias/abc-123").json()["total"]["llamadas"] == 0
