# Métricas: consumo de tokens y costo del modelo

Responde a una pregunta concreta: **¿cuánto cuesta crear (o cambiar) una historia de usuario?** Y, por partes,
cuánto gasta cada agente, cada día y el Agente de Pruebas cuando diagnostica un fallo.

Pantalla: **Mantenimiento › Consumo del modelo** (`/mantenimiento/consumo`). En el detalle de cada
HU, la pestaña **Consumo del modelo** muestra lo de esa historia. Las dos piden la acción
`metrica.ver` («Ver el consumo del modelo (tokens y costo)»); el Administrador la tiene, y se le puede dar a
otro rol en Mantenimiento › Roles y acciones.

## De dónde sale cada número

OpenCode devuelve, en cada respuesta del modelo (`Session.Message.Assistant` de la API v2), los **tokens**
(entrada, salida, razonamiento y caché de lectura y escritura) y el **costo en dólares**. El proyecto los toma
de ahí; no los calcula ni los adivina.

```
Aplicación ─► API ─► WorkflowRuntime abre el contexto (flujo, HU, título, creación o cambio)
                         │
                         ▼
               LangGraph ─► agente ─► OpenCodeClient.wait_for_assistant
                                            │  lee tokens y costo de la respuesta
                                            ▼
                                     registrar_uso ─► MetricasService ─► tabla consumo_modelo
                                                                     └─► Langfuse (generación con tokens y costo)
```

1. `WorkflowRuntime._ejecutar` abre `contexto_consumo(...)` antes de ejecutar el grafo. Los nodos de LangGraph
   corren en tareas que heredan ese contexto: cada agente queda asociado al flujo **sin tocar su código**.
2. `OpenCodeClient.wait_for_assistant` registra **toda** respuesta terminada, también las que fallaron (el
   proveedor igual las cobra), antes de revisarla.
3. `MetricasService.registrar` guarda una fila en `consumo_modelo` y, si Langfuse está configurado, envía una
   generación con `usage_details` y `cost_details` (sin contenido), para ver lo mismo en los tableros de Langfuse.

La HU se identifica así: al **crearla**, por el id del flujo, que al aprobarse pasa a ser el id de la HU; en un
**cambio**, por la HU aprobada. Por eso el costo de una HU suma su creación y todos sus cambios.

### Cuando OpenCode no informa el costo

| `costo_origen` | Qué significa |
|---|---|
| `opencode` | El costo lo calculó OpenCode (lo normal). |
| `estimado` | OpenCode no lo informó; se estimó con el precio que anuncia el modelo (USD por millón de tokens). |
| `sin_precio` | Ni costo ni precio: la fila queda en US$0, pero los tokens son exactos. |

La pantalla avisa si hay llamadas estimadas o sin precio.

### Agente de Pruebas

Corre dentro de GitHub Actions, donde la base de datos no se conserva. `agentes/pruebas/diagnosticar.py` suma
su consumo en memoria (`AcumuladorConsumo`) y lo entrega en `diagnostico.json`; el workflow lo agrega al
`resumen.json` y la aplicación lo guarda con la ejecución. La pantalla de métricas lo suma aparte.

## Qué muestra la pantalla

- **Indicadores:** costo total, tokens (entrada y salida), costo promedio por historia creada, costo promedio por
  cambio y llamadas al modelo (con las que tuvieron error).
- **Costo por agente** y **costo por día**, con el valor de cada barra al pasar el cursor y una tabla para
  lectores de pantalla.
- **Por historia:** cada creación o cambio, con sus agentes, llamadas, tokens y costo (los 50 más recientes).
- **Agente de Pruebas** y **modelo** usado.
- Periodo: últimos 7 días, últimos 30 o todo.

## Fiabilidad por agente

Además del consumo, cada **turno** de un agente en el flujo se guarda en la tabla `turno_agente`: si terminó,
cuántos intentos usó (1 = sin reintentos) y cuánto tardó. La pantalla muestra, por agente, los turnos, los que
necesitaron reintentos, los fallidos, la tasa de fallo y la duración promedio y máxima. Los reintentos
automáticos están en `agentes/analista/core/reintento.py` (ver `docs/arquitectura.md`, «Resiliencia»).

## Observabilidad (pantalla aparte)

**Mantenimiento › Observabilidad** (`/mantenimiento/observabilidad`, acción `observabilidad.ver`) responde otra
pregunta: **¿está funcionando bien ahora?** Muestra:

- **Alertas**, con los umbrales aprobados (`UMBRAL` en `observabilidad_service.py`):

  | Alerta | Umbral | Nivel |
  |---|---|---|
  | Historia cara | Costo mayor a 2 veces el promedio de los últimos 30 días (con al menos 3 historias) | Advertencia |
  | Paso lento | Un turno de agente de más de 3 minutos | Advertencia |
  | Agente que falla | Más de 10 % de turnos fallidos en 24 horas, con al menos 5 turnos | Crítica |
  | Cuota | Un error de cuota del modelo en la última hora | Crítica |
  | Costo no exacto | Llamadas con costo estimado o sin precio | Advertencia |
  | Tope de gasto | El mes pasó el 80 % (advertencia) o el 100 % (crítica); una historia detenida por su tope | Según el caso |

- **Tope de gasto:** lo gastado en el mes contra `PRESUPUESTO_MENSUAL_USD`, y el tope por historia.
- **Latencia por paso:** mediana, 95 % y máxima del turno de cada agente y de cada fuente de conocimiento (MCP).
  Cada consulta MCP se guarda en `llamada_herramienta` (agente, herramienta, estado y duración).
- **Trazas:** cada creación o cambio, con su estado (terminó, con reintentos, falló o detenida por el tope), su
  duración, su costo, sus consultas y sus pasos.

## Tope de gasto (kill-switch financiero)

Antes de cada llamada al modelo, `OpenCodeClient.submit_prompt` llama a `verificar_presupuesto`, y
`PresupuestoService` revisa:

- lo gastado por el flujo (la creación o el cambio de una HU) contra `PRESUPUESTO_HISTORIA_USD` (0,50 por defecto);
- lo gastado en el mes calendario, en hora local, contra `PRESUPUESTO_MENSUAL_USD` (60 por defecto: el uso mensual
  de OpenCode Go).

Si se pasó, la llamada no se hace. El error `PRESUPUESTO_AGOTADO` no se reintenta: el avance queda guardado, a quien
creó la historia le llega «Falló un agente» con el motivo y puede terminarla en modo manual. `0` desactiva un tope.
Si la revisión falla (la base no responde), se registra y se deja pasar: el límite del plan Go sigue protegiendo.

La barrera que garantiza no pagar más que la suscripción está en la consola de OpenCode: «Use balance» apagado y
sin créditos en Zen (ver `DESPLIEGUE.md`).

## Langfuse

Cada respuesta del modelo se envía como una generación con sus tokens y su costo. Todas las de un flujo van a la
misma traza (el id sale del id del flujo) y todas las de una HU (su creación y sus cambios) a la misma **sesión**.
En Langfuse: **Dashboards** trae los tableros de costo y latencia; **Sessions** muestra el costo de cada historia.
La latencia por paso se ve en la pantalla de Observabilidad.

## Model router

Cada agente declara `nivel_modelo` en su `definicion.py`: `liviano` (Asesor Técnico, Gestor de Cambios, Agente de
Pruebas) o `principal` (Analista, Redactor-Revisor). Con `OPENCODE_MODELO_LIVIANO_ID` configurado, los livianos usan
ese modelo; si falla (salida inválida, modelo no disponible o cuota de ese modelo), el turno se repite una vez con
`OPENCODE_MODEL_ID`. El modelo de cada llamada queda en `consumo_modelo`, así que en Consumo del modelo se ve cuánto
se gasta con cada uno.

## Privacidad

Solo se guardan cantidades: tokens, costo, duración, agente, modelo y a qué flujo o HU pertenecen. Nunca lo que
se le pidió al modelo ni lo que respondió. A Langfuse se envía lo mismo.

## Archivos

| Pieza | Archivo |
|---|---|
| Contexto, lectura de OpenCode y registradores | `agentes/metricas/registro_consumo.py` |
| Tabla `consumo_modelo` y consultas | `agentes/metricas/repositorio_consumo.py` |
| Servicio (registro, Langfuse, panel e historia) | `agentes/metricas/metricas_service.py` |
| Tope de gasto | `agentes/metricas/presupuesto_service.py` |
| Observabilidad (alertas, latencia, trazas) | `agentes/metricas/observabilidad_service.py` |
| API | `agentes/analista/api/routes/metricas.py` (`GET /api/analista/metricas/consumo?periodo=7\|30\|todo`, `GET …/metricas/consumo/historias/{id}` y `GET …/metricas/observabilidad?periodo=…`) |
| Pantallas | `src/components/Metricas/ConsumoModeloComponent.jsx` y `ObservabilidadComponent.jsx` |
| Pestaña del detalle | `src/components/Metricas/ConsumoHistoriaComponent.jsx` |
| Pruebas | `agentes/analista/tests/unit/test_metricas.py`, `test_observabilidad.py`, `src/components/Metricas/__tests__/`, `e2e/metricas.spec.js` (`@consumo`, `@observabilidad`) |

El consumo se registra desde que se instaló esta medición: las historias anteriores no tienen datos.
