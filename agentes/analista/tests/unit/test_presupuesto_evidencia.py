"""Presupuesto de tokens de evidencia por agente: repetidos, recorte parejo, textos enormes y marca."""
from __future__ import annotations

import pytest

from agentes.analista.core.ciclo_agente import ResultadoCiclo
from agentes.analista.core.ejecutor_mcp import ResultadoHerramienta
from agentes.analista.core.presupuesto_evidencia import (
    MARCA_RECORTE, PRESUPUESTO_PREDETERMINADO, ajustar_fuente, ajustar_observacion, estimar_token,
    presupuesto_configurado,
)


def _historia(i: int, largo: int = 400) -> dict:
    return {"id": f"HU-{i:03d}", "titulo": f"Historia {i}", "resumen": "x" * largo}


def _observacion(nombre: str, consulta: str, lista: list[dict], clave: str = "historias") -> dict:
    return {"nombre": nombre, "consulta": consulta, "datos": {clave: lista, "sources": [{"source_id": "s"}]}, "resultados": len(lista)}


def test_dentro_del_presupuesto_no_cambia_nada():
    lista = [_observacion("buscar_hu_similares", "saldos", [_historia(1), _historia(2)])]
    ajustada, ajuste = ajustar_observacion(lista, 12_000)
    assert ajustada == lista
    assert not ajuste.recortado and ajuste.limitacion() is None


def test_quita_consultas_y_elementos_repetidos():
    lista = [
        _observacion("buscar_hu_similares", "saldos", [_historia(1), _historia(2)]),
        _observacion("buscar_hu_similares", "saldos", [_historia(1)]),  # la misma consulta otra vez
        _observacion("buscar_hu_similares", "cuentas", [_historia(2), _historia(3)]),  # HU-002 ya vista
    ]
    ajustada, ajuste = ajustar_observacion(lista, 12_000)
    assert len(ajustada) == 2
    assert [h["id"] for h in ajustada[1]["datos"]["historias"]] == ["HU-003"]
    assert ajuste.repetidos == 2
    assert lista[2]["datos"]["historias"][0]["id"] == "HU-002"  # la original no se toca


def test_recorta_parejo_quitando_lo_menos_relevante_de_la_lista_mas_larga():
    grande = [_historia(i, 2000) for i in range(1, 6)]
    chica = [{"id": f"E-{i}", "regla": "y" * 2000} for i in range(1, 3)]
    lista = [_observacion("buscar_hu_similares", "a", grande), _observacion("consultar_estandares", "b", chica, "estandares")]
    ajustada, ajuste = ajustar_observacion(lista, 2_000)
    assert estimar_token(ajustada) <= 2_000
    historias = ajustada[0]["datos"]["historias"]
    assert [h["id"] for h in historias] == [f"HU-{i:03d}" for i in range(1, len(historias) + 1)]  # quedan las primeras
    assert ajustada[0]["recortado"] is True and ajustada[0]["omitidos"] >= 1
    assert ajustada[1]["datos"]["estandares"]  # ninguna herramienta queda vacía
    assert "presupuesto de 2.000 tokens" in ajuste.limitacion()


def test_un_texto_enorme_se_recorta_con_marca():
    lista = [{"nombre": "leer_archivo_codigo", "consulta": "polizas.py", "datos": {"archivo": {"contenido": "z" * 60_000}}}]
    ajustada, ajuste = ajustar_observacion(lista, 3_000)
    contenido = ajustada[0]["datos"]["archivo"]["contenido"]
    assert contenido.endswith(MARCA_RECORTE)
    assert estimar_token(ajustada) <= 3_000
    assert ajuste.textos_recortados == 1


def test_fuentes_del_asesor_recorta_textos_y_luego_quita_las_ultimas():
    fuentes = [{"source_id": f"f{i}", "source_ref": f"src/m{i}.py", "contenido": "c" * 12_000} for i in range(10)]
    fuentes.append(dict(fuentes[0]))  # repetida
    ajustada, ajuste = ajustar_fuente(fuentes, 6_000, reservado=500)
    assert estimar_token(ajustada) <= 5_500
    assert ajuste.repetidos == 1
    assert ajustada[0]["source_id"] == "f0"  # conserva el orden: lo que el agente leyó primero
    assert any(f["contenido"].endswith(MARCA_RECORTE) for f in ajustada)


def test_el_ciclo_aplica_el_presupuesto_y_deja_la_limitacion():
    ciclo = ResultadoCiclo(agente="analista", resultado=[
        ResultadoHerramienta("buscar_hu_similares", f"consulta {i}", "ok", datos={"historias": [_historia(i * 10 + j, 3000) for j in range(5)]}, cantidad=5)
        for i in range(4)
    ])
    ciclo.asesor = {"pregunta": "¿Afecta cargas?", "evaluacion": {"impacto": ["carga masiva"]}}
    evidencia = ciclo.observacion(presupuesto=4_000)
    assert estimar_token(evidencia) <= 4_000
    assert evidencia[-1]["nombre"] == "consultar_asesor_tecnico"  # el criterio del Asesor no se recorta
    assert ciclo.ajuste.omitidos > 0
    assert any("presupuesto" in nota for nota in ciclo.limitacion)


@pytest.mark.parametrize(("valor", "esperado"), [("", PRESUPUESTO_PREDETERMINADO), ("20000", 20_000), ("50", 1_000), ("mucho", PRESUPUESTO_PREDETERMINADO)])
def test_presupuesto_configurable(monkeypatch, valor, esperado):
    monkeypatch.setenv("PRESUPUESTO_EVIDENCIA_TOKENS", valor)
    assert presupuesto_configurado() == esperado
