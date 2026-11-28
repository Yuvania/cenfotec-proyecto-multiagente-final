"""Agentes en segundo plano: 202 al instante, avance (JSON y SSE), cola, avisos y errores ya traducidos."""
from __future__ import annotations

import asyncio
import json
import threading
import time
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentes.analista.api.errors import install_error_handlers
from agentes.analista.api.routes import workflows
from agentes.analista.core.avance import emitir
from agentes.analista.core.models import AgentTurnResponse, Analysis, Question, QuestionCategory, QuestionState
from agentes.analista.core.opencode_client import OpenCodeClientError
from agentes.analista.core.segundo_plano import SegundoPlanoService
from agentes.analista.core.workflow_graph import WorkflowRuntime
from agentes.analista.memory.repositorio import RepositorioHU

ASINCRONO = {"Prefer": "respond-async"}


def _respuesta_con_pregunta() -> AgentTurnResponse:
    return AgentTurnResponse(
        conversation_id=uuid4(), request_id=uuid4(), turn_id=uuid4(), estado="completado", respuesta_markdown="Listo.",
        analisis=Analysis(conocida=["Consulta de saldos"], faltante=["Plazo"], supuesta=[], ambigua=[]),
        preguntas=[Question(question_id="q-plazo", categoria=QuestionCategory.REQUIRED_DATA,
                            pregunta="¿Cuál es el plazo?", estado=QuestionState.PENDING)],
        fuentes_consultadas=[], listo_para_redactor=False, limitaciones=[], duracion_ms=1, prompt_version="1.0.0",
    )


class Control:
    """Permite frenar al Analista hasta que la prueba lo suelte (la app corre en otro hilo)."""

    def __init__(self, *, error: Exception | None = None) -> None:
        self.soltar = threading.Event()
        self.empezo = threading.Event()
        self.error = error

    async def analista(self, _state):
        self.empezo.set()
        emitir("agente_consulta", agente="analista", herramientas=["consultar_glosario", "buscar_hu_similares"])
        while not self.soltar.is_set():
            await asyncio.sleep(0.01)
        if self.error is not None:
            raise self.error
        return _respuesta_con_pregunta()


async def _asesor(_state):
    return {"affected_modules": [], "dependencies": [], "risks": [], "critical_processes": [],
            "consulted_sources": [], "uncertainties": ["Integración aislada del Asesor Técnico."]}


@pytest.fixture()
def armar(tmp_path):
    def _armar(control: Control, **opciones) -> tuple[TestClient, RepositorioHU]:
        repositorio = RepositorioHU(tmp_path / "fondo.db")
        app = FastAPI()
        install_error_handlers(app)
        app.include_router(workflows.router, prefix="/api/workflows")
        app.state.workflow_runtime = WorkflowRuntime(analyst=control.analista, advisor=_asesor, persistencia=repositorio)
        app.state.workflow_operation_guard = asyncio.Lock()
        app.state.workflow_active_operations = set()
        app.state.segundo_plano = SegundoPlanoService(**opciones)
        return TestClient(app), repositorio
    return _armar


def _iniciar(cliente: TestClient, usuario: str = "u-ana"):
    return cliente.post("/api/workflows", headers=ASINCRONO, json={
        "mode": "pre_grooming", "requirement": "Consultar saldos", "titulo": "Consulta de saldos",
        "creado_por": "Ana", "creado_por_usuario": usuario,
    })


def _esperar_fin(cliente: TestClient, workflow_id: str, segundos: float = 10) -> dict:
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        avance = cliente.get(f"/api/workflows/{workflow_id}/avance").json()
        if not avance["en_curso"]:
            return avance
        time.sleep(0.02)
    raise AssertionError("El flujo no terminó a tiempo.")


def test_responde_202_al_instante_y_el_avance_termina_con_lo_que_espera(armar):
    control = Control()
    cliente, repositorio = armar(control)
    with cliente:
        respuesta = _iniciar(cliente)
        assert respuesta.status_code == 202
        workflow_id = respuesta.json()["workflow_id"]
        assert control.empezo.wait(5)

        # Mientras trabaja: la consulta pide seguir el avance y la lista lo muestra «en ejecución».
        assert cliente.get(f"/api/workflows/{workflow_id}", headers=ASINCRONO).status_code == 202
        [en_lista] = [item for item in cliente.get("/api/workflows").json() if item["workflow_id"] == workflow_id]
        assert (en_lista["estado"], en_lista["titulo"]) == ("trabajando", "Consulta de saldos")
        assert _iniciar(cliente).status_code == 202  # otro flujo distinto sí puede empezar

        control.soltar.set()
        avance = _esperar_fin(cliente, workflow_id)
        tipos = [evento["tipo"] for evento in avance["eventos"]]
        assert tipos[0] == "inicio" and tipos[-1] == "fin"
        assert {"agente_inicio", "agente_consulta", "agente_fin"} <= set(tipos)
        assert avance["resultado"] == {"estado": "listo", "espera": "business_answers", "etapa": "espera_negocio"}
        consulta = next(e for e in avance["eventos"] if e["tipo"] == "agente_consulta")
        assert consulta["herramientas"] == ["consultar_glosario", "buscar_hu_similares"]

        # Terminó y nadie miraba en vivo: a quien la creó le llega «lista para continuar».
        lista = [a for a in repositorio.listar_aviso("u-ana") if a["tipo"] == "lista"]
        assert lista and lista[0]["detalle"] == "Las preguntas para Negocio están listas para responder."

        resultado = cliente.get(f"/api/workflows/{workflow_id}", headers=ASINCRONO)
        assert resultado.status_code == 200
        assert resultado.json()["interrupt"]["kind"] == "business_answers"


def test_en_vivo_por_sse_y_quien_mira_no_recibe_el_aviso(armar):
    control = Control()
    cliente, repositorio = armar(control)
    with cliente:
        workflow_id = _iniciar(cliente, usuario="u-luis").json()["workflow_id"]
        assert control.empezo.wait(5)
        eventos = []
        with cliente.stream("GET", f"/api/workflows/{workflow_id}/avance", headers={"Accept": "text/event-stream"}) as flujo:
            assert flujo.headers["content-type"].startswith("text/event-stream")
            control.soltar.set()
            for linea in flujo.iter_lines():
                if linea.startswith("data: "):
                    eventos.append(json.loads(linea[6:]))
                    if eventos[-1]["tipo"] == "fin":
                        break
        assert eventos[0]["tipo"] == "inicio"  # repite lo que pasó antes de conectarse
        assert eventos[-1]["estado"] == "listo"
        assert not [a for a in repositorio.listar_aviso("u-luis") if a["tipo"] == "lista"]


def test_el_error_llega_traducido_y_se_avisa_el_fallo(armar):
    control = Control(error=OpenCodeClientError("OPENCODE_AUTH_FAILED", "detalle privado"))
    cliente, repositorio = armar(control)
    with cliente:
        workflow_id = _iniciar(cliente).json()["workflow_id"]
        control.soltar.set()
        avance = _esperar_fin(cliente, workflow_id)
        error = avance["resultado"]["error"]
        assert avance["resultado"]["estado"] == "error"
        assert (error["code"], error["status"]) == ("DEPENDENCY_UNAVAILABLE", 503)
        assert "privado" not in json.dumps(avance)
        assert [a["tipo"] for a in repositorio.listar_aviso("u-ana")] == ["fallo"]


def test_no_se_responde_dos_veces_el_mismo_flujo_mientras_trabaja(armar):
    control = Control()
    cliente, _repositorio = armar(control)
    with cliente:
        workflow_id = _iniciar(cliente).json()["workflow_id"]
        assert control.empezo.wait(5)
        repetido = cliente.post(f"/api/workflows/{workflow_id}/reintentar", headers=ASINCRONO)
        assert repetido.status_code == 409
        control.soltar.set()
        _esperar_fin(cliente, workflow_id)


def test_sin_el_encabezado_responde_como_siempre(armar):
    control = Control()
    control.soltar.set()
    cliente, _repositorio = armar(control)
    with cliente:
        respuesta = cliente.post("/api/workflows", json={"mode": "pre_grooming", "requirement": "Consultar saldos"})
        assert respuesta.status_code == 201
        assert respuesta.json()["interrupt"]["kind"] == "business_answers"


@pytest.mark.asyncio
async def test_la_cola_deja_trabajar_a_uno_por_vez_y_avisa_el_puesto():
    servicio = SegundoPlanoService(maximo_simultaneo=1)
    soltar = asyncio.Event()

    async def lento():
        await soltar.wait()
        return "uno"

    async def rapido():
        return "dos"

    primero, segundo = uuid4(), uuid4()
    servicio.lanzar(primero, lento, traducir_error=lambda exc: {"code": "X"})
    await asyncio.sleep(0)
    servicio.lanzar(segundo, rapido, traducir_error=lambda exc: {"code": "X"})
    await asyncio.sleep(0.05)
    assert [e["tipo"] for e in servicio.estado(segundo)["eventos"]] == ["en_cola"]
    assert servicio.estado(segundo)["eventos"][0]["puesto"] == 1
    soltar.set()
    eventos = [e async for e in servicio.seguir(segundo)]
    assert [e["tipo"] for e in eventos] == ["en_cola", "inicio", "fin"]
    assert servicio.lista_en_curso() == set()
