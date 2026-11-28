"""Agente de Pruebas: explica por qué falló una prueba de punta a punta, no solo que falló."""
from agentes.equipo.contrato import DefinicionAgente, PropiedadAgente

DEFINICION = DefinicionAgente(
    id="probador",
    constante="TESTER",
    nombre="Agente de Pruebas",
    orden=50,
    descripcion="Diagnostica las pruebas de Playwright que fallan, con un navegador por Playwright MCP; no cambia nada.",
    modo_opencode="subagent",
    propiedad=PropiedadAgente(
        autonomia="Decide qué pantallas abrir y qué revisar (página, consola y llamadas a la API) para confirmar la causa.",
        razonamiento="Compara lo que la prueba esperaba con lo que ve en la aplicación y clasifica el fallo.",
        herramienta="Un navegador por Playwright MCP, limitado por el backend a la aplicación de prueba y a herramientas de lectura y navegación.",
        memoria="La evidencia del caso fallido: el error, los pasos, la página al fallar y la consola y la red registradas.",
    ),
    # No consulta la base de conocimiento: su servidor MCP propio queda sin herramientas. Sus herramientas son las
    # del navegador (Playwright MCP), con la lista permitida en agentes/pruebas/navegador_playwright_service.py.
    herramienta=set(),
    fuente={},
    maximo_ronda=4,
    nivel_modelo="liviano",
)
