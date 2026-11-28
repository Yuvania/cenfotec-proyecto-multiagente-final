"""Qué se puede probar, en qué ambiente y con qué navegador. Es el único registro de las suites.

Las suites se ordenan como el menú de la aplicación: primero se elige la opción del menú (Mantenimiento) y
después lo que hay dentro (Usuarios, Roles y acciones, Pruebas automatizadas) o «Todo Mantenimiento».

Cada alcance corresponde a una etiqueta de Playwright que llevan las pruebas de ``e2e/``. Una prueba lleva la
etiqueta de su opción del menú y la de su pantalla: ``{ tag: ['@mantenimiento', '@roles'] }``. Así
«Todo Mantenimiento» corre ``@mantenimiento`` y «Roles y acciones» solo ``@roles``.
El workflow ``.github/workflows/pruebas-e2e.yml`` ofrece las mismas opciones; una prueba de estructura revisa
que las tres listas (este catálogo, las etiquetas de ``e2e/`` y el workflow) coincidan.

Para agregar una suite:
1. Se agrega una línea en ``LISTA_ALCANCE`` con su opción del menú y su etiqueta.
2. Las pruebas nuevas en ``e2e/`` llevan esa etiqueta y la de su opción del menú.
3. La opción se agrega en ``inputs.alcance.options`` del workflow.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Alcance:
    codigo: str
    nombre: str
    descripcion: str
    etiqueta: str | None  # None: todas las pruebas (regresión)
    menu: str  # opción del menú a la que pertenece (LISTA_MENU)
    permite_produccion: bool = False


@dataclass(frozen=True)
class Opcion:
    codigo: str
    nombre: str
    descripcion: str = ""


# Opciones del menú que tienen pruebas, en el orden del menú de la aplicación.
LISTA_MENU: tuple[Opcion, ...] = (
    Opcion("aplicacion", "Toda la aplicación"),
    Opcion("notificaciones", "Notificaciones"),
    Opcion("historias", "Historias de usuario"),
    Opcion("mantenimiento", "Mantenimiento"),
)

LISTA_ALCANCE: tuple[Alcance, ...] = (
    Alcance("regresion", "Todo (regresión)", "Todas las pruebas de la aplicación.", None, "aplicacion"),
    Alcance("basicas", "Solo las básicas (smoke)", "Inicio de sesión y que cada pantalla principal abra.",
            "@basicas", "aplicacion", permite_produccion=True),
    Alcance("inicio-sesion", "Inicio de sesión y menú", "Entrar, clave incorrecta y menú según el rol.",
            "@inicio-sesion", "aplicacion"),
    Alcance("notificaciones", "Todo Notificaciones", "Lo que espera decisión, avisos, categorías y filtros.",
            "@notificaciones", "notificaciones"),
    Alcance("historias", "Todo Historias de usuario", "Crear, cambiar y exportar historias.", "@historias", "historias"),
    Alcance("crear-historia", "Crear historia (asistente)", "Requerimiento, preguntas a Negocio, historia y aprobación.",
            "@crear-historia", "historias"),
    Alcance("cambios", "Cambios a historias aprobadas", "Gestor de Cambios y registro manual.", "@cambios", "historias"),
    Alcance("exportar", "Exportar Word y PDF", "Descarga de la historia aprobada.", "@exportar", "historias"),
    Alcance("mantenimiento", "Todo Mantenimiento", "Usuarios, roles y acciones, pruebas, consumo del modelo y observabilidad.",
            "@mantenimiento", "mantenimiento"),
    Alcance("usuarios", "Usuarios", "Usuarios y sus roles.", "@usuarios", "mantenimiento"),
    Alcance("roles", "Roles y acciones", "Roles y las acciones que permiten, con nombres legibles.", "@roles", "mantenimiento"),
    Alcance("pruebas", "Pruebas automatizadas", "El propio tablero de ejecuciones.", "@pruebas", "mantenimiento"),
    Alcance("consumo", "Consumo del modelo", "Tokens y costo por historia, por agente y por día; permiso de métricas.",
            "@consumo", "mantenimiento"),
    Alcance("observabilidad", "Observabilidad", "Alertas, tope de gasto, latencia por paso y estado de cada traza; su permiso.",
            "@observabilidad", "mantenimiento"),
)

AMBIENTE_PRUEBAS = "pruebas"
AMBIENTE_PRODUCCION = "produccion"
LISTA_AMBIENTE: tuple[Opcion, ...] = (
    Opcion(AMBIENTE_PRUEBAS, "Pruebas",
           "Levanta la aplicación en un contenedor de GitHub con la API simulada: no gasta cuota del modelo ni crea datos."),
    Opcion(AMBIENTE_PRODUCCION, "Producción (solo lectura)",
           "Revisa la aplicación publicada con el usuario de QA, sin crear ni cambiar datos. Solo las básicas."),
)

LISTA_NAVEGADOR: tuple[Opcion, ...] = (
    Opcion("chromium", "Chromium"),
    Opcion("firefox", "Firefox"),
    Opcion("webkit", "WebKit (Safari)"),
)

# Cada prueba corre en estos tres tamaños de pantalla (proyectos de playwright.config.js).
LISTA_DISPOSITIVO: tuple[Opcion, ...] = (Opcion("web", "Web"), Opcion("tablet", "Tablet"), Opcion("movil", "Móvil"))

_ALCANCE = {a.codigo: a for a in LISTA_ALCANCE}
CODIGO_AMBIENTE = frozenset(o.codigo for o in LISTA_AMBIENTE)
CODIGO_NAVEGADOR = frozenset(o.codigo for o in LISTA_NAVEGADOR)


def alcance_de(codigo: str) -> Alcance | None:
    return _ALCANCE.get(codigo)


def nombre_de_etiqueta(etiqueta: str) -> str:
    """«roles» → «Roles y acciones», para mostrar el módulo de cada caso."""
    alcance = next((a for a in LISTA_ALCANCE if a.etiqueta == f"@{etiqueta}"), None)
    return alcance.nombre.removeprefix("Todo ") if alcance else etiqueta


def nombre_de(lista: tuple[Opcion, ...], codigo: str) -> str:
    return next((o.nombre for o in lista if o.codigo == codigo), codigo)


def como_dict() -> dict[str, list[dict[str, object]]]:
    return {
        "lista_menu": [{"codigo": o.codigo, "nombre": o.nombre} for o in LISTA_MENU],
        "lista_alcance": [
            {"codigo": a.codigo, "nombre": a.nombre, "descripcion": a.descripcion, "etiqueta": a.etiqueta,
             "menu": a.menu, "permite_produccion": a.permite_produccion}
            for a in LISTA_ALCANCE
        ],
        "lista_ambiente": [{"codigo": o.codigo, "nombre": o.nombre, "descripcion": o.descripcion} for o in LISTA_AMBIENTE],
        "lista_navegador": [{"codigo": o.codigo, "nombre": o.nombre} for o in LISTA_NAVEGADOR],
        "lista_dispositivo": [{"codigo": o.codigo, "nombre": o.nombre} for o in LISTA_DISPOSITIVO],
    }
