# Métricas: consumo de tokens y costo del modelo

Responde a una pregunta concreta: **¿cuánto cuesta crear (o cambiar) una historia de usuario?** Y, por partes,
cuánto gasta cada agente, cada día y el Agente de Pruebas cuando diagnostica un fallo.

Pantalla: **Mantenimiento › Métricas › Consumo del modelo** (`/mantenimiento/consumo`). En el detalle de cada
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

## Privacidad

Solo se guardan cantidades: tokens, costo, duración, agente, modelo y a qué flujo o HU pertenecen. Nunca lo que
se le pidió al modelo ni lo que respondió. A Langfuse se envía lo mismo.

## Archivos

| Pieza | Archivo |
|---|---|
| Contexto, lectura de OpenCode y registradores | `agentes/metricas/registro_consumo.py` |
| Tabla `consumo_modelo` y consultas | `agentes/metricas/repositorio_consumo.py` |
| Servicio (registro, Langfuse, panel e historia) | `agentes/metricas/metricas_service.py` |
| API | `agentes/analista/api/routes/metricas.py` (`GET /api/analista/metricas/consumo?periodo=7\|30\|todo` y `GET …/metricas/consumo/historias/{id}`) |
| Pantalla | `src/components/Metricas/ConsumoModeloComponent.jsx` |
| Pestaña del detalle | `src/components/Metricas/ConsumoHistoriaComponent.jsx` |
| Pruebas | `agentes/analista/tests/unit/test_metricas.py`, `src/components/Metricas/__tests__/`, `e2e/metricas.spec.js` (`@consumo`) |

El consumo se registra desde que se instaló esta medición: las historias anteriores no tienen datos.
