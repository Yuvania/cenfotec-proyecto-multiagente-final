"""Kill-switch financiero, observabilidad (latencia, alertas y trazas), model router y sesión de Langfuse."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from agentes.analista.api.errors import install_error_handlers
from agentes.analista.api.routes import metricas as rutas_metricas
from agentes.analista.core.agent_registry import AgentId
from agentes.analista.core.aviso_fallo import detalle_fallo
from agentes.analista.core.opencode_client import NIVEL_LIVIANO, OpenCodeClient, OpenCodeClientError, OpenCodeSettings
from agentes.analista.memory.repositorio import RepositorioHU
from agentes.equipo import obtener_definicion
from agentes.equipo.agente_opencode_service import AgenteOpenCodeService, SalidaAgenteInvalidaError
from agentes.metricas.metricas_service import MetricasService
from agentes.metricas.observabilidad_service import ObservabilidadService, percentil
from agentes.metricas.presupuesto_service import PresupuestoService, inicio_mes
from agentes.metricas.registro_consumo import (
    ALCANCE_HISTORIA, ALCANCE_MES, ORIGEN_OPENCODE, ORIGEN_SIN_PRECIO, ContextoConsumo, LlamadaHerramienta,
    PresupuestoAgotadoError, TurnoAgente, UsoModelo, agregar_guardian, contexto_consumo, quitar_guardian,
)
from agentes.metricas.repositorio_consumo import RepositorioConsumo
from agentes.seguridad.catalogo import ACCION, CODIGO_ACCION
from agentes.seguridad.clave import FirmaSesion


def _hace(**delta) -> str:
    return (datetime.now(UTC) - timedelta(**delta)).isoformat(timespec="milliseconds")


def _uso(mensaje_id: str, costo: float, *, origen: str = ORIGEN_OPENCODE, creado_en: str | None = None) -> UsoModelo:
    datos = {"creado_en": creado_en} if creado_en else {}
    return UsoModelo(mensaje_id=mensaje_id, agente="analista", proveedor="opencode-go", modelo="glm-5.3-flash",
                     tokens_entrada=100, tokens_salida=50, costo_usd=costo, costo_origen=origen, **datos)


def _turno(agente: str, *, exitoso: bool = True, duracion_ms: int = 1000, intentos: int = 1,
           codigo_error: str | None = None, creado_en: str | None = None) -> TurnoAgente:
    datos = {"creado_en": creado_en} if creado_en else {}
    return TurnoAgente(agente=agente, exitoso=exitoso, intentos=intentos, duracion_ms=duracion_ms,
                       codigo_error=codigo_error, **datos)


def _flujo(nombre: str) -> ContextoConsumo:
    return ContextoConsumo(workflow_id=nombre, historia_id=nombre, titulo=f"Historia {nombre}", modo="creacion")


@pytest.fixture()
def repositorio(tmp_path):
    return RepositorioConsumo(RepositorioHU(tmp_path / "o.db").motor)


# --- Kill-switch financiero ---------------------------------------------------------------------------
def test_el_tope_por_historia_congela_solo_esa_historia(repositorio, monkeypatch):
    monkeypatch.setenv("PRESUPUESTO_HISTORIA_USD", "0.10")
    monkeypatch.setenv("PRESUPUESTO_MENSUAL_USD", "60")
    presupuesto = PresupuestoService(repositorio)
    repositorio.guardar(_uso("a1", 0.06), _flujo("A"))
    presupuesto.verificar(_flujo("A"))  # 0,06 < 0,10: sigue
    repositorio.guardar(_uso("a2", 0.05), _flujo("A"))
    with pytest.raises(PresupuestoAgotadoError) as error:
        presupuesto.verificar(_flujo("A"))
    assert error.value.alcance == ALCANCE_HISTORIA
    assert "modo manual" not in str(error.value) and "termínela a mano" in str(error.value)
    presupuesto.verificar(_flujo("B"))  # otra historia no se detiene


def test_el_tope_mensual_detiene_todo_y_cero_lo_desactiva(repositorio, monkeypatch):
    monkeypatch.setenv("PRESUPUESTO_HISTORIA_USD", "0")
    monkeypatch.setenv("PRESUPUESTO_MENSUAL_USD", "1")
    presupuesto = PresupuestoService(repositorio)
    repositorio.guardar(_uso("viejo", 5.0, creado_en="2000-01-01T00:00:00.000+00:00"), _flujo("X"))
    repositorio.guardar(_uso("m1", 0.6), _flujo("A"))
    presupuesto.verificar(_flujo("B"))  # el gasto de otro mes no cuenta
    repositorio.guardar(_uso("m2", 0.5), _flujo("A"))
    with pytest.raises(PresupuestoAgotadoError) as error:
        presupuesto.verificar(_flujo("B"))
    assert error.value.alcance == ALCANCE_MES
    assert presupuesto.estado()["porcentaje_mes"] == pytest.approx(110.0)
    monkeypatch.setenv("PRESUPUESTO_MENSUAL_USD", "0")
    presupuesto.verificar(_flujo("B"))
    assert presupuesto.estado()["mensual_usd"] is None


def test_el_mes_empieza_a_medianoche_hora_de_costa_rica(monkeypatch):
    monkeypatch.setenv("ZONA_HORARIA", "America/Costa_Rica")
    assert inicio_mes(datetime(2026, 11, 28, 15, tzinfo=UTC)) == "2026-11-01T06:00:00.000+00:00"
    # El 1.º a las 3 a. m. UTC todavía es octubre en Costa Rica.
    assert inicio_mes(datetime(2026, 11, 1, 3, tzinfo=UTC)) == "2026-10-01T06:00:00.000+00:00"


@pytest.mark.asyncio
async def test_opencode_no_llama_al_modelo_si_se_paso_el_tope(repositorio, monkeypatch):
    monkeypatch.setenv("PRESUPUESTO_HISTORIA_USD", "0.01")
    repositorio.guardar(_uso("a1", 0.02), _flujo("A"))
    presupuesto = PresupuestoService(repositorio)
    llamada: list[str] = []

    def responder(request: httpx.Request) -> httpx.Response:
        llamada.append(request.url.path)
        return httpx.Response(200, json={"data": {"id": "m"}})

    agregar_guardian(presupuesto)
    try:
        async with httpx.AsyncClient(base_url="http://opencode.test", transport=httpx.MockTransport(responder)) as http:
            cliente = OpenCodeClient(OpenCodeSettings(_env_file=None, server_password=SecretStr("test-only")), client=http)
            with contexto_consumo(workflow_id="A", historia_id="A", modo="creacion"):
                with pytest.raises(OpenCodeClientError) as error:
                    await cliente.submit_prompt("s1", "hola")
            with contexto_consumo(workflow_id="B", historia_id="B", modo="creacion"):
                await cliente.submit_prompt("s1", "hola")
    finally:
        quitar_guardian(presupuesto)
    assert error.value.code == "PRESUPUESTO_AGOTADO"
    assert error.value.retryable is False
    assert llamada == ["/api/session/s1/prompt"]  # solo la historia B llegó al modelo


@pytest.mark.asyncio
async def test_si_el_guardian_falla_se_deja_pasar(monkeypatch):
    async def roto(_contexto):
        raise ConnectionError("la base no responde")

    from agentes.metricas.registro_consumo import verificar_presupuesto

    agregar_guardian(roto)
    try:
        await verificar_presupuesto()
    finally:
        quitar_guardian(roto)


def test_el_aviso_del_tope_ofrece_el_modo_manual():
    texto = detalle_fallo(OpenCodeClientError("PRESUPUESTO_AGOTADO", "tope"), agente="redactor_revisor")
    assert texto.startswith("Redactor-Revisor no pudo terminar: se alcanzó el tope de gasto")
    assert "modo manual" in texto and "Retomar" not in texto


# --- Observabilidad ------------------------------------------------------------------------------------
def test_percentil_por_rango_mas_cercano():
    assert percentil([], 95) == 0
    assert percentil([5, 1, 3], 50) == 3
    assert percentil(list(range(1, 101)), 95) == 95


def test_latencia_por_agente_y_por_herramienta(repositorio, monkeypatch):
    monkeypatch.setenv("PRESUPUESTO_MENSUAL_USD", "60")
    for duracion in (1000, 2000, 3000, 200_000):
        repositorio.guardar_turno(_turno("asesor_tecnico", duracion_ms=duracion), _flujo("A"))
    repositorio.guardar_herramienta(LlamadaHerramienta("analista", "consultar_glosario", "ok", 120), _flujo("A"))
    repositorio.guardar_herramienta(LlamadaHerramienta("analista", "consultar_glosario", "timeout", 8000), _flujo("A"))
    panel = ObservabilidadService(repositorio, PresupuestoService(repositorio)).panel("7")
    [asesor] = panel["latencia_agente"]
    assert (asesor["nombre"], asesor["cantidad"], asesor["p50_ms"], asesor["maxima_ms"], asesor["lentos"]) == (
        "Asesor Técnico", 4, 2000, 200_000, 1)
    [glosario] = panel["latencia_herramienta"]
    assert (glosario["nombre"], glosario["p95_ms"], glosario["fallidas"]) == ("Glosario", 8000, 1)


def test_alertas_con_los_umbrales_aprobados(repositorio, monkeypatch):
    monkeypatch.setenv("PRESUPUESTO_MENSUAL_USD", "0.6")
    # Tres historias baratas y una que cuesta más del doble del promedio.
    for nombre, costo in (("A", 0.01), ("B", 0.01), ("C", 0.01), ("D", 0.5)):
        repositorio.guardar(_uso(f"m-{nombre}", costo), _flujo(nombre))
    repositorio.guardar(_uso("sin-precio", 0.0, origen=ORIGEN_SIN_PRECIO), _flujo("A"))
    # Redactor: 1 de 5 turnos falla (20 %); Analista: 1 de 4 (no llega al mínimo de 5).
    for indice in range(5):
        repositorio.guardar_turno(_turno("redactor_revisor", exitoso=indice != 0, codigo_error=None if indice else "TURN_TIMEOUT"), _flujo("B"))
    for indice in range(4):
        repositorio.guardar_turno(_turno("analista", exitoso=indice != 0), _flujo("C"))
    repositorio.guardar_turno(_turno("asesor_tecnico", duracion_ms=181_000), _flujo("C"))
    repositorio.guardar_turno(_turno("asesor_tecnico", exitoso=False, codigo_error="OPENCODE_RATE_LIMITED"), _flujo("A"))
    repositorio.guardar_turno(_turno("gestor_cambios", exitoso=False, codigo_error="OPENCODE_RATE_LIMITED",
                                     creado_en=_hace(hours=2)), _flujo("A"))
    repositorio.guardar_turno(_turno("redactor_revisor", exitoso=False, codigo_error="PRESUPUESTO_AGOTADO"), _flujo("D"))

    alerta = {item["id"]: item for item in ObservabilidadService(repositorio, PresupuestoService(repositorio)).panel("7")["alerta"]}
    assert alerta["costo_alto"]["lista"] == [{"workflow_id": "D", "titulo": "Historia D"}]
    assert alerta["paso_lento"]["detalle"] == "Agentes: Asesor Técnico."
    assert "fallo_redactor_revisor" in alerta and "fallo_analista" not in alerta
    assert "1 paso(s)" in alerta["cuota"]["detalle"]  # el de hace 2 horas no cuenta
    assert alerta["costo_inexacto"]["titulo"].startswith("1 llamada")
    assert alerta["presupuesto_historia"]["lista"] == [{"workflow_id": "D", "titulo": "Historia D"}]
    assert alerta["presupuesto_mes"]["nivel"] == "advertencia"  # 0,53 de 0,60: más del 80 %
    niveles = [item["nivel"] for item in alerta.values()]
    assert niveles == sorted(niveles, key=lambda nivel: nivel != "critica")


def test_sin_datos_no_hay_alertas(repositorio):
    panel = ObservabilidadService(repositorio, PresupuestoService(repositorio)).panel("todo")
    assert (panel["alerta"], panel["traza"], panel["latencia_agente"]) == ([], [], [])


def test_estado_de_cada_traza(repositorio):
    repositorio.guardar(_uso("a", 0.02), _flujo("A"))
    repositorio.guardar_turno(_turno("analista", creado_en=_hace(minutes=3)), _flujo("A"))
    repositorio.guardar_turno(_turno("redactor_revisor", intentos=2, creado_en=_hace(minutes=2)), _flujo("A"))
    repositorio.guardar_turno(_turno("analista", exitoso=False, codigo_error="TURN_TIMEOUT"), _flujo("B"))
    repositorio.guardar_turno(_turno("analista", exitoso=False, codigo_error="PRESUPUESTO_AGOTADO"), _flujo("C"))
    repositorio.guardar_turno(_turno("analista"), _flujo("E"))
    repositorio.guardar_herramienta(LlamadaHerramienta("analista", "consultar_glosario", "ok", 50), _flujo("A"))
    traza = {item["workflow_id"]: item for item in ObservabilidadService(repositorio, PresupuestoService(repositorio)).panel("7")["traza"]}
    assert {flujo: item["estado"] for flujo, item in traza.items()} == {
        "A": "con_reintento", "B": "fallo", "C": "detenida", "E": "ok"}
    assert [paso["nombre"] for paso in traza["A"]["paso"]] == ["Agente Analista", "Redactor-Revisor"]
    assert (traza["A"]["titulo"], traza["A"]["costo_usd"], traza["A"]["consultas_mcp"]) == ("Historia A", 0.02, 1)


def test_la_api_de_observabilidad_exige_su_accion(repositorio):
    assert ACCION.OBSERVABILIDAD_VER in CODIGO_ACCION
    usuario = {"id": "u", "nombre": "Ana", "usuario": "ana", "activo": True, "roles": [], "acciones": [ACCION.METRICA_VER]}
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(rutas_metricas.router, prefix="/api/analista")
    app.state.observabilidad = ObservabilidadService(repositorio, PresupuestoService(repositorio))
    app.state.seguridad = SimpleNamespace(obtener_usuario=lambda _id: usuario)
    app.state.firma_sesion = FirmaSesion("prueba")
    cliente = TestClient(app)
    cliente.headers["Authorization"] = f"Bearer {app.state.firma_sesion.emitir('u')}"
    assert cliente.get("/api/analista/metricas/observabilidad").status_code == 403
    usuario["acciones"] = [ACCION.OBSERVABILIDAD_VER]
    respuesta = cliente.get("/api/analista/metricas/observabilidad?periodo=30")
    assert respuesta.status_code == 200
    assert respuesta.json()["umbral"]["paso_ms"] == 180_000
    assert cliente.get("/api/analista/metricas/observabilidad?periodo=x").status_code == 400


# --- Langfuse: cada historia es una sesión ------------------------------------------------------------------
def test_langfuse_agrupa_por_historia(tmp_path):
    observado: list[dict] = []

    class _Generacion:
        def end(self):
            observado[-1]["terminada"] = True

    class _Cliente:
        @staticmethod
        def create_trace_id(*, seed):
            return f"traza-{seed}"

        @staticmethod
        def start_observation(**datos):
            observado.append(datos)
            return _Generacion()

    servicio = MetricasService(RepositorioConsumo(RepositorioHU(tmp_path / "l.db").motor),
                               observability=SimpleNamespace(client=_Cliente()))
    servicio._enviar_a_langfuse(_uso("m", 0.01), ContextoConsumo(workflow_id="F1", historia_id="HU-7", modo="cambio"))
    [datos] = observado
    assert datos["trace_context"] == {"trace_id": "traza-F1"}
    assert datos["cost_details"] == {"total": 0.01}
    assert datos["metadata"]["historia_id"] == "HU-7"
    assert datos["terminada"] is True


# --- Model router ----------------------------------------------------------------------------------------
def test_cada_agente_declara_su_nivel_de_modelo():
    assert obtener_definicion("analista").nivel_modelo == "principal"
    assert obtener_definicion("redactor_revisor").nivel_modelo == "principal"
    assert obtener_definicion("gestor_cambios").nivel_modelo == "liviano"


@pytest.mark.asyncio
async def test_select_model_usa_el_liviano_solo_si_esta_configurado():
    modelos = {"data": [
        {"providerID": "opencode-go", "modelID": "glm-5.3-flash", "enabled": True, "cost": [{"input": 1, "output": 2}]},
        {"providerID": "opencode-go", "modelID": "deepseek-v4-flash", "enabled": True, "cost": [{"input": 0.1, "output": 0.2}]},
    ]}
    transporte = httpx.MockTransport(lambda _request: httpx.Response(200, json=modelos))
    async with httpx.AsyncClient(base_url="http://opencode.test", transport=transporte) as http:
        base = {"_env_file": None, "server_password": SecretStr("x"), "opencode_provider_id": "opencode-go",
                "opencode_model_id": "glm-5.3-flash"}
        sin_router = OpenCodeClient(OpenCodeSettings(**base), client=http)
        assert sin_router.hay_modelo_liviano is False
        assert (await sin_router.select_model(nivel=NIVEL_LIVIANO))["id"] == "glm-5.3-flash"
        con_router = OpenCodeClient(OpenCodeSettings(**base, opencode_modelo_liviano_id="deepseek-v4-flash"), client=http)
        assert con_router.hay_modelo_liviano is True
        assert (await con_router.select_model(nivel=NIVEL_LIVIANO))["id"] == "deepseek-v4-flash"
        assert (await con_router.select_model())["id"] == "glm-5.3-flash"


class _ClienteRouter:
    """Doble de OpenCode: anota con qué modelo corrió cada turno y falla con el liviano si se le pide."""

    def __init__(self, registro: list[str], *, falla_liviano: Exception | None, hay_liviano: bool = True) -> None:
        self.registro = registro
        self.falla_liviano = falla_liviano
        self.hay_modelo_liviano = hay_liviano
        self.settings = SimpleNamespace(turn_timeout_seconds=30)
        self.modelo = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    def set_deadline(self, _deadline):
        return None

    async def server_info(self):
        return {"version": "2.1.2"}

    async def verify_agent(self, _agente):
        return {}

    async def select_model(self, _agent=None, *, nivel="principal"):
        self.modelo = nivel
        return {"providerID": "opencode-go", "id": nivel}

    @asynccontextmanager
    async def session(self, **_):
        yield {"id": "s"}

    async def submit_prompt(self, _session_id, _texto):
        self.registro.append(self.modelo)
        if self.modelo == NIVEL_LIVIANO and self.falla_liviano is not None:
            raise self.falla_liviano
        return {"time": {"created": 1}}

    async def wait_for_assistant(self, *_args, **_kwargs):
        return {"text": "{}"}


class _GestorDoble(AgenteOpenCodeService[str]):
    agente = AgentId.CHANGE_MANAGER
    titulo_sesion = "prueba"
    corregir_salida = False

    def __init__(self, cliente_factory):
        super().__init__(cliente_factory)

    @property
    def prompt(self):
        return None

    async def correr(self):
        async def consulta_propia(_turno):
            return None

        return await self._ejecutar_turno(
            tarea="t", contexto="c", consulta_base="q", armar_mensaje=lambda _turno: "m",
            interpretar=lambda generado, _turno: generado["text"], consulta_propia=consulta_propia,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(("falla", "esperado"), [
    (None, ["liviano"]),
    (OpenCodeClientError("MODEL_UNAVAILABLE", "x"), ["liviano", "principal"]),
    (SalidaAgenteInvalidaError("formato"), ["liviano", "principal"]),
])
async def test_el_router_escala_al_principal_si_el_liviano_falla(falla, esperado):
    registro: list[str] = []
    servicio = _GestorDoble(lambda **_: _ClienteRouter(registro, falla_liviano=falla))
    assert await servicio.correr() == "{}"
    assert registro == esperado


@pytest.mark.asyncio
async def test_el_tope_de_gasto_no_se_escala_y_sin_liviano_no_se_repite():
    registro: list[str] = []
    servicio = _GestorDoble(lambda **_: _ClienteRouter(registro, falla_liviano=OpenCodeClientError("PRESUPUESTO_AGOTADO", "tope")))
    with pytest.raises(OpenCodeClientError):
        await servicio.correr()
    assert registro == ["liviano"]

    registro.clear()

    class _SinLiviano(_ClienteRouter):
        async def submit_prompt(self, _session_id, _texto):
            self.registro.append(self.modelo)
            raise OpenCodeClientError("OPENCODE_UNAVAILABLE", "caído", retryable=True)

    servicio = _GestorDoble(lambda **_: _SinLiviano(registro, falla_liviano=None, hay_liviano=False))
    with pytest.raises(OpenCodeClientError):
        await servicio.correr()
    assert registro == ["principal"]  # sin modelo liviano configurado, un solo intento (los reintentos son aparte)


@pytest.mark.asyncio
async def test_cada_consulta_mcp_queda_registrada(monkeypatch):
    from agentes.analista.core import ejecutor_mcp
    from agentes.metricas.registro_consumo import agregar_registrador_herramienta, quitar_registrador_herramienta

    recibido: list[tuple[LlamadaHerramienta, ContextoConsumo]] = []

    async def guardar(llamada, contexto):
        recibido.append((llamada, contexto))

    sesion = object.__new__(ejecutor_mcp.SesionMCP)
    sesion.agent_id = AgentId.ANALYST

    async def invocar_falso(nombre, consulta, *, limite):
        await asyncio.sleep(0)
        return ejecutor_mcp.ResultadoHerramienta(nombre, consulta, "ok", duracion_ms=42)

    monkeypatch.setattr(sesion, "_invocar", invocar_falso, raising=False)
    agregar_registrador_herramienta(guardar)
    try:
        with contexto_consumo(workflow_id="F", historia_id="F", modo="creacion"):
            await ejecutor_mcp.SesionMCP.invocar(sesion, "consultar_glosario", "saldo")
    finally:
        quitar_registrador_herramienta(guardar)
    [(llamada, contexto)] = recibido
    assert (llamada.agente, llamada.herramienta, llamada.estado, llamada.duracion_ms) == ("analista", "consultar_glosario", "ok", 42)
    assert contexto.workflow_id == "F"


def test_la_api_explica_el_tope_y_no_ofrece_reintentar():
    from agentes.analista.api.routes.workflows import _translate_runtime_error

    error = _translate_runtime_error(OpenCodeClientError("PRESUPUESTO_AGOTADO", "Esta historia alcanzó su tope de gasto."))
    assert (error.status_code, error.retryable, error.message) == (429, False, "Esta historia alcanzó su tope de gasto.")
