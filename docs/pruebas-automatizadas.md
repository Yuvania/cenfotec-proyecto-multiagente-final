# Pruebas automatizadas (Playwright)

Pruebas de punta a punta que abren la aplicación en un navegador real y la recorren como una persona. Cada caso corre en tres tamaños: **web** (1366 px), **tablet** (820 px) y **móvil** (390 px).

Se pueden correr de tres formas, siempre con las mismas pruebas de `e2e/`:

| Dónde | Cómo | Para qué |
|---|---|---|
| Tablero de la aplicación | **Mantenimiento › Calidad › Pruebas automatizadas** → Ejecutar pruebas | El día a día: cualquiera con la acción «Ejecutar pruebas automatizadas» |
| Cualquier computadora con Docker | `docker compose --profile pruebas run --rm pruebas` | Probar antes de subir un cambio, sin instalar Node ni navegadores |
| Desarrollo con Vite | `npm run test:e2e` | Escribir pruebas nuevas |

## Cómo funciona el tablero

```
Tablero (Render) ──token──▶ GitHub Actions: pruebas-e2e.yml
      ▲                          │ 1. docker compose build (app + pruebas)
      │ avance y resumen         │ 2. levanta la aplicación (API simulada)
      └──────────────────────────┤ 3. Playwright: web, tablet y móvil
                                 └ 4. publica resumen.json y las evidencias
```

1. La persona elige **qué probar**, el **ambiente** y el **navegador**. Solo hay una ejecución a la vez.
2. El backend (`agentes/pruebas/`) registra la ejecución (#013) y arranca el workflow con un token de GitHub.
3. Mientras el tablero está abierto, el backend consulta a GitHub cada pocos segundos: el estado y los pasos («Preparar…», «Ejecutar…», «Publicar…») forman la línea de tiempo.
4. Al terminar descarga el artefacto `resumen-<id>` (el `resumen.json` que escribe `e2e/soporte/reportero-resumen.js`), lo valida y lo guarda en la tabla `prueba_ejecucion`.
5. Las evidencias completas quedan en GitHub, en el artefacto `evidencias-<id>`: reporte HTML, JUnit, JSON y, de cada fallo, captura, video y traza (se abre en [trace.playwright.dev](https://trace.playwright.dev)). Se conservan 30 días.

6. **Si hay fallos**, el **Agente de Pruebas** explica por qué (ver la sección siguiente) y su diagnóstico aparece en cada caso del tablero.

**¿Por qué en GitHub y no en Render?** Chromium le quitaría memoria a la aplicación en vivo (el plan tiene 2 GB) y las evidencias se borrarían con cada despliegue. En repositorios públicos los minutos de Actions no tienen costo.

## Agente de Pruebas: por qué falló, no solo que falló

Playwright dice *que* algo falló («esperaba ver "Historia aprobada" y no apareció»). El Agente de Pruebas investiga *por qué*.

1. **Percibe** la evidencia del caso fallido, que deja el reportero en `resumen.json`: el error, los pasos que alcanzó (`test.step`), la página al fallar (árbol de accesibilidad) y los errores de consola y de la API que registró la prueba (`e2e/soporte/prueba.js`).
2. **Piensa** qué necesita confirmar y **actúa** con un navegador real por **Playwright MCP** (el servidor oficial de Microsoft, servicio `navegador` de `docker-compose.yml`): abre pantallas, lee la página, revisa la consola y las llamadas a la API. Hasta 4 rondas.
3. **Diagnostica**: qué falló, la causa probable, la evidencia, una sugerencia y la clasificación — **error de la aplicación**, **prueba desactualizada** (la aplicación cambió a propósito y la prueba quedó vieja) o **problema del ambiente** — con su nivel de confianza.

Reglas:

- **Solo diagnostica.** No cambia código, datos ni usuarios; decide una persona.
- **Mínimo privilegio.** Playwright MCP trae más de 20 herramientas; el backend (`agentes/pruebas/navegador_playwright_service.py`) solo permite 10 (navegar, leer la página, clic, escribir, elegir, tecla, esperar, consola y red) y rechaza las demás (por ejemplo, ejecutar JavaScript o subir archivos). Solo abre la aplicación de prueba (`http://aplicacion:10000`); cualquier otra dirección se rechaza, y el navegador además tiene `--allowed-origins`.
- **Cuida la cuota:** el mismo caso en web, tablet y móvil se diagnostica una vez, y como máximo 3 casos por ejecución (variable `PROBADOR_MAXIMO_CASO` del repositorio).
- Usa el modelo con OpenCode, como los demás agentes (`agentes/equipo/probador/`). Sus instrucciones están en `prompt.md`.
- La aplicación que abre no tiene la API simulada de la prueba: la usa para confirmar lo que depende de la interfaz (textos, botones, permisos, errores de JavaScript, llamadas que fallan).

Si el repositorio no tiene `OPENCODE_API_KEY`, las pruebas corren igual y los casos quedan sin diagnóstico.

### Ambientes

- **Pruebas** (predeterminado): GitHub levanta la aplicación en Docker y las pruebas simulan la API con `page.route`. No gastan cuota del modelo, no crean datos y dan el mismo resultado siempre.
- **Producción (solo lectura)**: solo las **básicas**, contra la aplicación publicada (`APP_URL` o `RENDER_EXTERNAL_URL`), ingresando con el usuario de QA. Solo leen: ingresar, abrir cada pantalla principal y salir.

### Suites, por opción del menú

En «Nueva ejecución» primero se elige la **opción del menú** y después aparecen solo las pruebas de lo que hay dentro de ella. Cada prueba lleva la etiqueta de su opción del menú y la de su pantalla (`{ tag: ['@mantenimiento', '@roles'] }`): «Todo Mantenimiento» corre `@mantenimiento` y «Roles y acciones», solo `@roles`.

| Opción del menú | Qué probar | Etiqueta | Qué cubre |
|---|---|---|---|
| Toda la aplicación | Todo (regresión) | — | Todas las pruebas |
| | Solo las básicas (smoke) | `@basicas` | Ingreso, pantallas principales y salida (también en producción) |
| | Inicio de sesión y menú | `@inicio-sesion` | Clave incorrecta, ingreso, menú según el rol, grupos y «Más» en móvil |
| Notificaciones | Todo Notificaciones | `@notificaciones` | Lista única, categorías, filtros y avisos leídos |
| Historias de usuario | Todo Historias de usuario | `@historias` | Todo lo de abajo |
| | Crear historia (asistente) | `@crear-historia` | Requerimiento, preguntas a Negocio, historia y aprobación del PO |
| | Cambios a historias aprobadas | `@cambios` | Gestor de Cambios y registro manual |
| | Exportar Word y PDF | `@exportar` | Descarga de la historia aprobada |
| Mantenimiento | Todo Mantenimiento | `@mantenimiento` | Todo lo de abajo |
| | Usuarios | `@usuarios` | Usuarios y sus roles |
| | Roles y acciones | `@roles` | Acciones con nombres legibles, nunca códigos |
| | Pruebas automatizadas | `@pruebas` | El propio tablero |

El registro único es `agentes/pruebas/catalogo_pruebas.py` (cada suite dice a qué opción del menú pertenece). Una prueba de estructura (`test_pruebas.py`) revisa que coincida con las opciones del workflow y con las etiquetas de `e2e/`.

## Configuración (una sola vez)

La hace quien administra el repositorio desde el que Render despliega. **Para pasar de un repositorio a otro (por ejemplo, del de un compañero al propio) solo se cambia el token**: Render le dice a la aplicación de qué repositorio y rama salió (`RENDER_GIT_REPO_SLUG` y `RENDER_GIT_BRANCH`).

1. **Token en GitHub** (lo crea el dueño del repositorio): GitHub → *Settings* → *Developer settings* → *Personal access tokens* → *Fine-grained tokens* → *Generate new token*.
   - *Repository access*: **Only select repositories** → el repositorio de la aplicación.
   - *Permissions* → *Repository permissions* → **Actions: Read and write**. Nada más.
   - Elija una fecha de vencimiento y guárdelo: GitHub lo muestra una sola vez.
2. **Render** → el servicio → *Environment* → agregue `GITHUB_PRUEBAS_TOKEN` con el token → *Save and deploy*.
3. **Para el ambiente Producción** (opcional):
   - En la aplicación, Mantenimiento → *Nuevo usuario* de QA con el rol **Consulta**.
   - En GitHub → *Settings* → *Secrets and variables* → *Actions* → *New repository secret*: `QA_USUARIO` y `QA_CLAVE`.
4. **Para el Agente de Pruebas** (recomendado): en GitHub → *Settings* → *Secrets and variables* → *Actions* → *New repository secret*: `OPENCODE_API_KEY`. Use una clave **nueva** solo para esto, que se pueda revocar sin afectar la aplicación. Opcional, en *Variables*: `OPENCODE_MODEL_ID`, `OPENCODE_PROVIDER_ID` y `PROBADOR_MAXIMO_CASO`.
5. **Permiso en la aplicación**: el Administrador tiene las acciones nuevas «Acceder a Pruebas automatizadas» y «Ejecutar pruebas automatizadas». Asígnelas en Mantenimiento a los roles que deban verlas o ejecutarlas.

El token nunca se envía al navegador ni se escribe en los registros. Las claves de QA y del modelo solo viven en los Secrets de GitHub.

Fuera de Render (por ejemplo, con Docker en una computadora), además del token se indican `GITHUB_PRUEBAS_REPOSITORIO` (`dueño/repositorio`) y `GITHUB_PRUEBAS_RAMA`.

## En cualquier computadora con Docker

Requisito: Docker Desktop (Windows o Mac) o Docker Engine con Compose (Linux).

```powershell
Copy-Item .env.docker.example .env.docker      # opcional: claves del modelo, base de datos, etc.
docker compose up --build                       # la aplicación en http://localhost:10000
docker compose --profile pruebas run --rm pruebas                  # todas las pruebas
docker compose --profile pruebas run --rm pruebas --grep @basicas  # una suite
docker compose --profile pruebas run --rm -e NAVEGADOR=firefox pruebas
docker compose down                             # detener (los datos quedan en el volumen «datos»)
```

Las evidencias quedan en `reportes-pruebas/` (abra `reportes-pruebas/html/index.html`).

Para que el Agente de Pruebas diagnostique los fallos en su computadora (necesita `OPENCODE_API_KEY` en `.env.docker`):

```powershell
docker compose --profile diagnostico up --detach --wait navegador
Get-Content reportes-pruebas\resumen.json | docker compose exec -T aplicacion python -m agentes.pruebas.diagnosticar > reportes-pruebas\diagnostico.json
``` Las imágenes son las mismas que usa GitHub Actions: lo que pasa en su computadora pasa en GitHub.

## Escribir una prueba

- Un archivo `e2e/<modulo>.spec.js`. Cada `test` o `test.describe` de primer nivel lleva la etiqueta de su opción del menú y la de su pantalla: `test.describe('Usuarios', { tag: ['@mantenimiento', '@usuarios'] }, () => { ... })`. Importe `test` y `expect` de `./soporte/prueba.js` (registra consola y API para el Agente de Pruebas).
- Use `e2e/soporte/ambiente.js`: `ingresarComo(page, usuario)`, `simularSesion`, `simularApiVacia` y `abrirSinSeguridad`. Simule la API con `page.route`; nunca dependa de datos del ambiente.
- Busque los elementos como lo haría una persona: `getByRole`, `getByLabel`, `getByText`. Nada de clases CSS.
- Use `test.step('Abre Notificaciones', ...)`: los pasos aparecen en el tablero cuando un caso falla.
- Solo datos sintéticos: nada real del negocio ni datos personales.
- Una prueba `@basicas` debe funcionar también en producción: solo lee y no asume datos.

## Archivos

| Archivo | Qué es |
|---|---|
| `e2e/*.spec.js` | Las pruebas, por módulo |
| `e2e/soporte/` | Ayudas comunes y el reportero que escribe `resumen.json` |
| `e2e/Dockerfile` | Imagen de las pruebas (Playwright con Chromium, Firefox y WebKit) |
| `playwright.config.js` | Proyectos web, tablet y móvil; `BASE_URL`, `NAVEGADOR` y `REPORTE_DIR` |
| `docker-compose.yml` | Servicios `aplicacion` y `pruebas` |
| `.github/workflows/pruebas-e2e.yml` | El workflow que arranca el tablero |
| `agentes/pruebas/` | Catálogo de suites, registro de ejecuciones, cliente de GitHub Actions, navegador (Playwright MCP) y `diagnosticar.py` |
| `agentes/equipo/probador/` | El Agente de Pruebas: definición, instrucciones y su servicio |
| `e2e/soporte/prueba.js` | `test` con el registro automático de consola y API (evidencia para el agente) |
| `src/components/Pruebas/` | El tablero y los resultados |

## Problemas frecuentes

- **«Las pruebas todavía no están conectadas con GitHub»**: falta `GITHUB_PRUEBAS_TOKEN` en Render (o, fuera de Render, `GITHUB_PRUEBAS_REPOSITORIO`).
- **«GitHub rechazó el token»**: venció o no tiene *Actions: Read and write* sobre ese repositorio.
- **«GitHub no encontró pruebas-e2e.yml»**: el workflow no está en la rama que despliega Render, o el token es de otro repositorio.
- **«GitHub no inició la ejecución»**: revise que Actions esté habilitado en el repositorio (*Settings* → *Actions*).
- **Los casos fallidos no tienen diagnóstico**: falta el secret `OPENCODE_API_KEY`, o el modelo no respondió a tiempo (el caso dice el motivo). El paso «Diagnosticar los fallos» en GitHub muestra el detalle.
- **La ejecución terminó sin resultados**: abra «Ver en GitHub» y revise el paso «Ejecutar las pruebas» (por ejemplo, la aplicación no levantó).
