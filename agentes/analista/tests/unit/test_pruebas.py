"""Pruebas automatizadas: pedirlas a GitHub Actions, seguirlas, traer el resumen y proteger las rutas."""
from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentes.analista.api.errors import install_error_handlers
from agentes.analista.api.routes import pruebas as rutas_pruebas
from agentes.analista.memory.repositorio import RepositorioHU
from agentes.pruebas.catalogo_pruebas import LISTA_ALCANCE
from agentes.pruebas.github_actions_service import ConfiguracionGitHub, GitHubActionsService
from agentes.pruebas.pruebas_service import PruebasService, filtro_casos, linea_de_tiempo
from agentes.pruebas.repositorio_pruebas import RepositorioPrueba
from agentes.seguridad.catalogo import ACCION
from agentes.seguridad.clave import FirmaSesion

RAIZ = Path(__file__).resolve().parents[4]
TOKEN = "token-github-sintetico"
RESUMEN = {
    "version": 1, "inicio": "2030-01-02T10:00:00Z", "duracion_ms": 272000, "navegador": "chromium",
    "total": 3, "aprobados": 2, "fallidos": 1, "inestables": 0, "omitidos": 0,
    "casos": [
        {"id": "c1", "titulo": "El PO aprueba (paso 5)", "modulo": "historias", "archivo": "historias.spec.js",
         "dispositivo": "movil", "estado": "fallido", "duracion_ms": 41000, "error": "No apareció «Historia aprobada».",
         "pasos": ["Ingresa", "Aprueba"], "contexto_pagina": "- button Aprobar", "registro": [{"tipo": "api", "estado": 403}],
         "diagnostico": {"estado": "listo", "que_fallo": "No se aprobó la historia.", "causa_probable": "La API respondió 403.",
                         "tipo": "error_aplicacion", "confianza": "media", "evidencia": ["POST /resume → 403"],
                         "sugerencia": "Revisar las acciones del rol.",
                         "exploracion": {"rondas": 2, "acciones": ["browser_navigate (ok)"], "limitaciones": []}}},
        {"id": "c2", "titulo": "Registra el requerimiento", "modulo": "historias", "dispositivo": "web",
         "estado": "aprobado", "duracion_ms": 12000, "diagnostico": {"estado": "otro"}},
        {"id": "c3", "titulo": "El analista no ve Aprobar", "modulo": "historias", "dispositivo": "web",
         "estado": "aprobado", "duracion_ms": 9000},
    ],
}


class GitHubFalso:
    """Responde como la API de GitHub Actions y guarda lo que se le pidió."""

    def __init__(self) -> None:
        self.lista_solicitud: list[httpx.Request] = []
        self.dispatch: list[dict] = []
        self.estado_run = "queued"
        self.conclusion = None
        self.resumen = RESUMEN
        self.cancelado = False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.lista_solicitud.append(request)
        ruta = request.url.path
        if ruta.endswith("/dispatches"):
            self.dispatch.append(json.loads(request.content))
            return httpx.Response(200, json={"workflow_run_id": 777, "html_url": "https://github.com/equipo/app/actions/runs/777"})
        if ruta.endswith("/actions/runs/777"):
            return httpx.Response(200, json={"id": 777, "status": self.estado_run, "conclusion": self.conclusion,
                                             "html_url": "https://github.com/equipo/app/actions/runs/777"})
        if ruta.endswith("/actions/runs/777/jobs"):
            terminado = self.estado_run == "completed"
            return httpx.Response(200, json={"jobs": [{"steps": [
                {"name": "Descargar el código", "status": "completed", "conclusion": "success"},
                {"name": "Preparar el navegador y la aplicación", "status": "completed" if terminado or self.estado_run == "in_progress" else "queued",
                 "conclusion": "success" if terminado or self.estado_run == "in_progress" else None},
                {"name": "Ejecutar las pruebas", "status": "completed" if terminado else "in_progress",
                 "conclusion": "failure" if terminado else None},
                {"name": "Diagnosticar los fallos con el Agente de Pruebas", "status": "completed" if terminado else "queued",
                 "conclusion": "success" if terminado else None},
                {"name": "Publicar los resultados para el tablero", "status": "completed" if terminado else "queued",
                 "conclusion": "success" if terminado else None},
            ]}]})
        if ruta.endswith("/actions/runs/777/artifacts"):
            nombre = request.url.params["name"]
            return httpx.Response(200, json={"artifacts": [{"id": 55, "name": nombre, "expired": False}]})
        if ruta.endswith("/actions/artifacts/55/zip"):
            contenido = io.BytesIO()
            with zipfile.ZipFile(contenido, "w") as comprimido:
                comprimido.writestr("resumen.json", json.dumps(self.resumen))
            return httpx.Response(200, content=contenido.getvalue())
        if ruta.endswith("/actions/runs/777/cancel"):
            self.cancelado = True
            return httpx.Response(202)
        return httpx.Response(404, json={"message": "Not Found"})


@pytest.fixture()
def github():
    return GitHubFalso()


@pytest.fixture()
def servicio(tmp_path, github):
    repositorio = RepositorioPrueba(RepositorioHU(tmp_path / "repo.db").motor)
    cliente_github = GitHubActionsService(ConfiguracionGitHub(TOKEN, "equipo/app", "main"),
                                          transport=httpx.MockTransport(github))
    return PruebasService(repositorio, cliente_github)


ADMIN = {"id": "admin", "nombre": "Ana", "usuario": "ana", "activo": True, "roles": [],
         "acciones": [ACCION.PRUEBA_VER, ACCION.PRUEBA_EJECUTAR]}
SOLO_VER = {"id": "lectora", "nombre": "Luis", "usuario": "luis", "activo": True, "roles": [], "acciones": [ACCION.PRUEBA_VER]}


def _cliente(servicio, usuario):
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(rutas_pruebas.router, prefix="/api/analista")
    app.state.pruebas = servicio
    app.state.seguridad = SimpleNamespace(obtener_usuario=lambda _id: usuario)
    app.state.firma_sesion = FirmaSesion("prueba")
    cliente = TestClient(app)
    cliente.headers["Authorization"] = f"Bearer {app.state.firma_sesion.emitir(usuario['id'])}"
    return cliente


def _forzar_sincronizacion(servicio, ejecucion_id):
    servicio.repositorio.actualizar(ejecucion_id, sincronizado_en=None)


def test_sin_token_avisa_que_falta_configurar(tmp_path, monkeypatch):
    for nombre in ("GITHUB_PRUEBAS_TOKEN", "GITHUB_PRUEBAS_REPOSITORIO", "RENDER_GIT_REPO_SLUG"):
        monkeypatch.delenv(nombre, raising=False)
    servicio = PruebasService(RepositorioPrueba(RepositorioHU(tmp_path / "r.db").motor))
    respuesta = _cliente(servicio, ADMIN).get("/api/analista/pruebas/configuracion").json()
    assert respuesta["configurado"] is False
    assert "GITHUB_PRUEBAS_TOKEN" in respuesta["faltante"]
    creada = _cliente(servicio, ADMIN).post("/api/analista/pruebas/ejecuciones", json={"alcance": "regresion"})
    assert creada.status_code == 503


def test_el_repositorio_y_la_rama_salen_de_render(monkeypatch):
    monkeypatch.delenv("GITHUB_PRUEBAS_REPOSITORIO", raising=False)
    monkeypatch.delenv("GITHUB_PRUEBAS_RAMA", raising=False)
    monkeypatch.setenv("GITHUB_PRUEBAS_TOKEN", TOKEN)
    monkeypatch.setenv("RENDER_GIT_REPO_SLUG", "companero/app")
    monkeypatch.setenv("RENDER_GIT_BRANCH", "main")
    configuracion = ConfiguracionGitHub.from_environment()
    assert (configuracion.repositorio, configuracion.rama, configuracion.configurado) == ("companero/app", "main", True)
    monkeypatch.setenv("RENDER_GIT_REPO_SLUG", "no es un repositorio")
    assert ConfiguracionGitHub.from_environment().repositorio == ""


def test_ejecutar_arranca_el_workflow_y_solo_permite_una_a_la_vez(servicio, github):
    cliente = _cliente(servicio, ADMIN)
    respuesta = cliente.post("/api/analista/pruebas/ejecuciones",
                             json={"alcance": "historias", "navegador": "firefox", "ambiente": "pruebas"})
    assert respuesta.status_code == 201
    ejecucion = respuesta.json()
    assert ejecucion["numero"] == 1 and ejecucion["estado"] == "en_cola" and ejecucion["iniciada_por"] == "Ana"
    assert github.dispatch == [{"ref": "main", "return_run_details": True, "inputs": {
        "ejecucion": ejecucion["id"], "numero": "#001", "alcance": "historias", "navegador": "firefox",
        "ambiente": "pruebas", "url": "", "casos": ""}}]
    # El token viaja solo en el encabezado hacia GitHub; nunca en la respuesta.
    assert github.lista_solicitud[0].headers["Authorization"] == f"Bearer {TOKEN}"
    assert TOKEN not in respuesta.text and TOKEN not in cliente.get("/api/analista/pruebas/configuracion").text

    otra = cliente.post("/api/analista/pruebas/ejecuciones", json={"alcance": "regresion"})
    assert otra.status_code == 409
    assert "#001" in otra.json()["error"]["message"]


def test_sigue_el_avance_y_al_terminar_guarda_el_resumen(servicio, github):
    cliente = _cliente(servicio, ADMIN)
    ejecucion_id = cliente.post("/api/analista/pruebas/ejecuciones", json={"alcance": "historias"}).json()["id"]

    github.estado_run = "in_progress"
    _forzar_sincronizacion(servicio, ejecucion_id)
    panel = cliente.get("/api/analista/pruebas/ejecuciones").json()
    assert panel["activa"]["estado"] == "en_ejecucion"
    assert [p["estado"] for p in panel["activa"]["pasos"]] == ["completa", "completa", "en_curso", "pendiente", "pendiente"]

    github.estado_run, github.conclusion = "completed", "failure"
    _forzar_sincronizacion(servicio, ejecucion_id)
    detalle = cliente.get(f"/api/analista/pruebas/ejecuciones/{ejecucion_id}").json()
    assert detalle["estado"] == "con_fallos"
    assert detalle["resumen"] == {k: v for k, v in RESUMEN.items() if k not in ("casos", "version")}
    assert [c["estado"] for c in detalle["casos"]] == ["fallido", "aprobado", "aprobado"]
    # El diagnóstico del Agente de Pruebas se guarda; uno mal formado se descarta sin perder el caso.
    assert detalle["casos"][0]["diagnostico"]["tipo"] == "error_aplicacion"
    assert detalle["casos"][1]["diagnostico"] is None
    # La evidencia cruda para el agente (página y registro) no se guarda en la base.
    assert "contexto_pagina" not in detalle["casos"][0] and "registro" not in detalle["casos"][0]
    assert [p["estado"] for p in detalle["pasos"]] == ["completa", "completa", "fallida", "completa", "completa"]
    assert detalle["run_url"].endswith("/runs/777")

    panel = cliente.get("/api/analista/pruebas/ejecuciones").json()
    assert panel["activa"] is None
    assert panel["indicador"]["ultima"] == {"id": ejecucion_id, "numero": 1, "total": 3, "aprobados": 2, "fallidos": 1,
                                            "duracion_ms": 272000}
    assert "casos" not in panel["lista_ejecucion"][0]


def test_repetir_los_fallidos_filtra_exactamente_esos_casos(servicio, github):
    cliente = _cliente(servicio, ADMIN)
    ejecucion_id = cliente.post("/api/analista/pruebas/ejecuciones", json={"alcance": "historias"}).json()["id"]
    github.estado_run, github.conclusion = "completed", "failure"
    _forzar_sincronizacion(servicio, ejecucion_id)
    cliente.get(f"/api/analista/pruebas/ejecuciones/{ejecucion_id}")

    nueva = cliente.post(f"/api/analista/pruebas/ejecuciones/{ejecucion_id}/repetir-fallidos")
    assert nueva.status_code == 201 and nueva.json()["solo_fallidos"] is True
    filtro = github.dispatch[-1]["inputs"]["casos"]
    assert re.search(filtro, "historias.spec.js > El PO aprueba (paso 5) @historias")
    assert not re.search(filtro, "Registra el requerimiento")


def test_produccion_solo_admite_las_basicas_con_url_https(servicio, monkeypatch):
    cliente = _cliente(servicio, ADMIN)
    monkeypatch.setenv("APP_URL", "https://historias.example.com")
    rechazada = cliente.post("/api/analista/pruebas/ejecuciones", json={"alcance": "historias", "ambiente": "produccion"})
    assert rechazada.status_code == 400
    monkeypatch.setenv("APP_URL", "http://historias.example.com")
    assert cliente.post("/api/analista/pruebas/ejecuciones",
                        json={"alcance": "basicas", "ambiente": "produccion"}).status_code == 503


def test_cancelar_pide_a_github_que_detenga_la_ejecucion(servicio, github):
    cliente = _cliente(servicio, ADMIN)
    ejecucion_id = cliente.post("/api/analista/pruebas/ejecuciones", json={"alcance": "regresion"}).json()["id"]
    assert cliente.post(f"/api/analista/pruebas/ejecuciones/{ejecucion_id}/cancelar").status_code == 200
    assert github.cancelado is True
    github.estado_run, github.conclusion = "completed", "cancelled"
    _forzar_sincronizacion(servicio, ejecucion_id)
    assert cliente.get(f"/api/analista/pruebas/ejecuciones/{ejecucion_id}").json()["estado"] == "cancelada"


def test_ver_y_ejecutar_son_acciones_separadas(servicio):
    cliente = _cliente(servicio, SOLO_VER)
    assert cliente.get("/api/analista/pruebas/ejecuciones").status_code == 200
    assert cliente.post("/api/analista/pruebas/ejecuciones", json={"alcance": "regresion"}).status_code == 403


def test_un_resumen_invalido_no_se_guarda(servicio, github):
    cliente = _cliente(servicio, ADMIN)
    ejecucion_id = cliente.post("/api/analista/pruebas/ejecuciones", json={"alcance": "regresion"}).json()["id"]
    github.resumen = {"total": -1, "casos": "no es una lista"}
    github.estado_run, github.conclusion = "completed", "success"
    _forzar_sincronizacion(servicio, ejecucion_id)
    detalle = cliente.get(f"/api/analista/pruebas/ejecuciones/{ejecucion_id}").json()
    assert detalle["estado"] == "error" and detalle["casos"] == []


def test_filtro_y_linea_de_tiempo():
    assert filtro_casos(["a.b", "a.b", "c (d)"]) == r"a\.b|c\ \(d\)"
    cancelada = linea_de_tiempo([], "cancelada")
    assert [e["estado"] for e in cancelada] == ["completa", "cancelada", "cancelada", "cancelada", "cancelada"]


# --- Las tres listas de suites coinciden: catálogo, workflow y etiquetas de e2e/ ------------------------
def _opciones_workflow(entrada: str) -> list[str]:
    texto = (RAIZ / ".github/workflows/pruebas-e2e.yml").read_text(encoding="utf-8")
    bloque = re.search(rf"\n      {entrada}:\n(.*?)(?=\n      [a-z]+:\n|\npermissions:)", texto, re.S).group(1)
    return re.findall(r"^          - ([a-z-]+)$", bloque, re.M)


def test_el_workflow_ofrece_las_mismas_suites_del_catalogo():
    assert _opciones_workflow("alcance") == [a.codigo for a in LISTA_ALCANCE]


def test_cada_suite_tiene_pruebas_y_cada_prueba_tiene_suite():
    texto = "\n".join(p.read_text(encoding="utf-8") for p in (RAIZ / "e2e").glob("*.spec.js"))
    # Una etiqueta sola (tag: '@roles') o varias (tag: ['@mantenimiento', '@roles']).
    usadas = {etiqueta for grupo in re.findall(r"tag: (\[[^\]]*\]|'[^']*')", texto) for etiqueta in re.findall(r"@[a-z-]+", grupo)}
    catalogo = {a.etiqueta for a in LISTA_ALCANCE if a.etiqueta}
    assert usadas == catalogo
    # Ninguna prueba queda fuera de una suite: cada test o describe de primer nivel lleva su etiqueta.
    sin_etiqueta = re.findall(r"^(?:test|test\.describe)\('[^']+', async", texto, re.M)
    assert sin_etiqueta == []


def test_la_imagen_de_pruebas_usa_la_version_de_playwright_del_proyecto():
    bloqueo = json.loads((RAIZ / "package-lock.json").read_text(encoding="utf-8"))
    version = bloqueo["packages"]["node_modules/@playwright/test"]["version"]
    dockerfile = (RAIZ / "e2e/Dockerfile").read_text(encoding="utf-8")
    assert f"mcr.microsoft.com/playwright:v{version}-" in dockerfile
    assert f"@playwright/test@{version}" in dockerfile


def test_los_pasos_del_workflow_alimentan_la_linea_de_tiempo():
    from agentes.pruebas.pruebas_service import LISTA_ETAPA
    texto = (RAIZ / ".github/workflows/pruebas-e2e.yml").read_text(encoding="utf-8")
    lista_nombre = re.findall(r"^      - name: (.+)$", texto, re.M)
    for _, _, prefijo in LISTA_ETAPA:
        if prefijo:
            assert any(nombre.startswith(prefijo) for nombre in lista_nombre), prefijo
