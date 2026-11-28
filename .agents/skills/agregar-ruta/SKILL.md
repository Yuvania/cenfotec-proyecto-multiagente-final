---
name: agregar-ruta
description: Úsala cuando haya que agregar una pantalla, una ruta o una opción de menú al frontend React de este repositorio de historias de usuario.
---

# Agregar una pantalla o una opción de menú

Las rutas y el menú salen de un solo registro: `src/config/rutas.jsx`. No agregues `<Route>` en `App.jsx` ni enlaces en `EnvolturaPaginaComponent.jsx`.

## Regla que no se negocia: el menú tiene como máximo 2 niveles
Grupo › opción, por ejemplo «Mantenimiento › Observabilidad». **Nunca un tercer nivel**: no crees grupos dentro de grupos, submenús, opciones que abran otro menú ni migas de tres partes. Las secciones de un grupo (*Seguridad*, *Calidad*, *Métricas*) son solo títulos que ordenan su panel: no son un nivel, no se abren y no aparecen en las migas. Si una pantalla nueva no cabe, va suelta (nivel 1) o dentro de un grupo existente (nivel 2). La prueba «el menú no pasa de 2 niveles» de `src/config/__tests__/rutas.test.jsx` lo comprueba: no la relajes ni la borres. Ver `docs/arquitectura.md`.

## Pasos
1. Crea el componente en `src/components/<Funcionalidad>/<Nombre>Component.jsx`.
   - Lógica sin React en `src/utils/` (con pruebas), llamadas al backend en `src/services/`, estado reutilizable en `src/hooks/`.
   - Componentes comunes (botones, alertas, tarjetas, áreas de texto) en `src/components/Comun/`: reutilízalos.
2. Agrega una entrada en `listaRuta` de `src/config/rutas.jsx`:
   ```js
   { ruta: 'reportes', componente: ReporteComponent,
     menu: { etiqueta: 'Reportes', titulo: 'Ver reportes', icono: BarChart3, orden: 40 } },
   ```
   - Sin `menu` la pantalla existe pero no aparece en el menú (por ejemplo, un detalle `historias/:id`).
   - **Grupos:** lo que es de administrar no va suelto en el menú. Va en un grupo de `listaGrupoMenu` (hoy, Mantenimiento, con los títulos de sección *Seguridad*, *Calidad* y *Métricas*): la entrada lleva `menu.grupo` y `menu.seccion` (el título bajo el que aparece), su ruta empieza por la del grupo (`mantenimiento/...`) y no lleva ícono. Las migas «Mantenimiento › Opción» se arman solas, con dos partes.
   - **Móvil:** solo las opciones con `barraMovil: true` van en la barra inferior (hoy Inicio, Notificaciones e Historias); las demás y los grupos van en «Más». No agregues más de cuatro a la barra.
   - **Direcciones viejas:** si cambias una ruta, deja la vieja con `redirigir('/nueva')` para no romper enlaces guardados.
   - Las acciones de una pantalla (por ejemplo, «Nueva historia») van como botón en la pantalla, no como opción del menú.
   - `orden` en decenas y único; `exacta: true` si la ruta no debe marcarse activa en sus subrutas.
   - Íconos de `lucide-react`.
   - Si solo deben verla algunos roles, agrega `accion: ACCION.X` (de `src/config/acciones.js`). Si la acción no existe, agrégala en `agentes/seguridad/catalogo.py` (con su nombre legible) y en `src/config/acciones.js`; las rutas de la API que use la pantalla declaran `requiere_accion(ACCION.X)`. No hace falta tocar Mantenimiento.
3. Si la pantalla es nueva para la persona usuaria, descríbela en la Ayuda (`src/data/ayudaDocumentacion.js`).
4. Prueba con Testing Library (mira `src/components/EnvolturaPagina/__tests__/`) y ejecuta `npx vitest run` y `npx vite build`.

## Pasos del asistente para crear una historia
El asistente está en `src/components/HistoriaUsuario/crear/` y separa controlador y vistas:
- La lógica (estado, efectos, llamadas al flujo) va en `useCrearHistoria.js`; lo que una vista necesite se agrega al objeto que devuelve.
- Cada paso es una vista `Paso<Nombre>Component.jsx` que lee el controlador con `useAsistenteHistoria()` y no guarda estado del flujo.
- Para agregar un paso: su valor en `PASO` (`constantesAsistente.js`), su vista y su entrada en `LISTA_PASO` (`pasosAsistente.js`). El indicador de pasos sale de ese registro.
- `CrearHistoriaUsuarioComponent.jsx` solo arma la página (avisos, indicador y paso activo): no agregues lógica ahí.

## Convenciones
- Componentes terminan en `Component`; servicios en `Service`.
- Nombres en español y en singular para variables (`listaHistoria`).
- Sin `catch` vacío: al menos `console.warn` con el motivo.
- Textos para la persona usuaria en lenguaje de negocio, sin detalle técnico.
