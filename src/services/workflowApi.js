import { avisarSesionVencida, encabezadoSesion } from '../utils/sesion.js';
import { quotaRecoveryWorkflowMessage } from '../utils/quotaRecovery.js';
const API_BASE = '/api/workflows';

const STATUS_MESSAGES = Object.freeze({
  400: 'La respuesta no coincide con la intervención humana pendiente. Revise los datos y vuelva a intentarlo.',
  404: 'No se encontró el flujo. Puede que se haya descartado; revise la lista de HU en proceso o inicie uno nuevo.',
  409: 'El flujo está ocupado o ya no espera esta decisión. Actualice su estado antes de volver a enviar.',
  422: 'La respuesta no cumple el contrato del flujo. Revise los campos e inténtelo de nuevo.',
  503: 'Un servicio necesario no está disponible. El flujo no avanzó; puede reintentar cuando el servicio vuelva.',
  500: 'Ocurrió un error inesperado. El avance anterior quedó guardado: consulte el estado del flujo.',
  504: 'El flujo tardó demasiado y su resultado está incompleto. Consulte su estado antes de repetir la decisión.',
});

export class WorkflowApiError extends Error {
  constructor(status, payload = {}, { path = '', method = 'GET' } = {}) {
    const detail = payload?.error ?? {};
    const cuotaAgotada = detail.code === 'OPENCODE_RATE_LIMITED';
    const safeMessage = status === 404 && method === 'POST' && path === ''
      ? 'El endpoint de workflows no está disponible en este backend. Puede continuar con el flujo manual.'
      : (cuotaAgotada ? quotaRecoveryWorkflowMessage(detail.retry_at) : STATUS_MESSAGES[status]);
    super(safeMessage ?? (typeof detail.message === 'string'
      ? detail.message
      : 'No fue posible completar la solicitud del flujo.'));
    this.name = 'WorkflowApiError';
    this.status = status;
    this.code = typeof detail.code === 'string' ? detail.code : 'NETWORK_ERROR';
    this.retryable = Boolean(detail.retryable);
    this.requestId = typeof detail.request_id === 'string' ? detail.request_id : undefined;
    this.retryAt = typeof detail.retry_at === 'string' ? detail.retry_at : undefined;
  }
}

async function request(path, { method = 'GET', body, signal, headers = {} } = {}) {
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method,
      headers: body === undefined ? { Accept: 'application/json', ...encabezadoSesion(), ...headers } : {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        ...encabezadoSesion(),
        ...headers,
      },
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: 'same-origin',
      cache: 'no-store',
      signal,
    });
  } catch (cause) {
    if (cause?.name === 'AbortError') throw cause;
    const error = new WorkflowApiError(0);
    error.cause = cause;
    error.code = 'NETWORK_ERROR';
    error.retryable = true;
    throw error;
  }

  let payload;
  try {
    payload = response.status === 204 ? null : await response.json();
  } catch {
    payload = {};
  }
  avisarSesionVencida(response.status);
  if (!response.ok) throw new WorkflowApiError(response.status, payload, { path, method });
  return payload;
}

// --- Agentes en segundo plano -----------------------------------------------------------------------------
// Con «Prefer: respond-async» el backend responde 202 al instante y los agentes trabajan aparte. Aquí se sigue el
// avance en vivo (SSE por fetch, para poder enviar la sesión) y, si la conexión se corta, se consulta cada pocos
// segundos. Para quien llama no cambia nada: recibe el resultado final como antes; el avance llega por «alAvance».
// Un backend que no conoce el modo responde como siempre (201/200 con el resultado) y también funciona.
const ASINCRONO = Object.freeze({ Prefer: 'respond-async' });
export const CONSULTA_AVANCE_MS = 2000;

const esperar = (ms, signal) => new Promise((resolve, reject) => {
  const temporizador = setTimeout(resolve, ms);
  signal?.addEventListener('abort', () => {
    clearTimeout(temporizador);
    reject(new DOMException('Cancelado', 'AbortError'));
  }, { once: true });
});

// Lee «data: {...}» de un stream SSE y entrega cada evento. Devuelve el evento «fin» o null si se cortó antes.
async function leerSse(respuesta, alEvento) {
  const lector = respuesta.body.getReader();
  const decodificador = new TextDecoder();
  let pendiente = '';
  for (;;) {
    const { value, done } = await lector.read();
    if (done) return null;
    pendiente += decodificador.decode(value, { stream: true });
    const bloques = pendiente.split('\n\n');
    pendiente = bloques.pop();
    for (const bloque of bloques) {
      const datos = bloque.split('\n').filter((linea) => linea.startsWith('data: ')).map((linea) => linea.slice(6)).join('\n');
      if (!datos) continue;
      let evento;
      try {
        evento = JSON.parse(datos);
      } catch (fallo) {
        console.warn('Evento de avance ilegible:', fallo?.message ?? fallo);
        continue;
      }
      alEvento(evento);
      if (evento.tipo === 'fin') {
        lector.cancel().catch((motivo) => console.warn('No se cerró el avance:', motivo?.message ?? motivo));
        return evento;
      }
    }
  }
}

/** Sigue a los agentes hasta que terminan y devuelve el resultado del flujo (o lanza el error ya traducido). */
export async function esperarFlujo(workflowId, { signal, alAvance } = {}) {
  const ruta = `/${encodeURIComponent(workflowId)}`;
  let recibidos = 0;
  const entregar = (evento) => {
    recibidos += 1;
    alAvance?.(evento);
  };
  let fin = null;
  // 1) En vivo. El backend repite lo que ya pasó, así que se cuenta lo entregado para no duplicarlo después.
  try {
    const respuesta = await fetch(`${API_BASE}${ruta}/avance`, {
      headers: { Accept: 'text/event-stream', ...encabezadoSesion() }, credentials: 'same-origin', cache: 'no-store', signal,
    });
    avisarSesionVencida(respuesta.status);
    if (respuesta.ok && respuesta.body) fin = await leerSse(respuesta, entregar);
  } catch (fallo) {
    if (fallo?.name === 'AbortError') throw fallo;
    console.warn('Se perdió el avance en vivo; se consulta cada pocos segundos:', fallo?.message ?? fallo);
  }
  // 2) Respaldo: consultar el avance hasta que termine.
  while (!fin) {
    const estado = await request(`${ruta}/avance`, { signal });
    (estado?.eventos ?? []).slice(recibidos).forEach(entregar);
    if (estado && !estado.en_curso) {
      fin = estado.resultado ?? { estado: 'desconocido' };
      break;
    }
    await esperar(CONSULTA_AVANCE_MS, signal);
  }
  if (fin.estado === 'error') {
    const error = fin.error ?? {};
    throw new WorkflowApiError(error.status || 500, { error });
  }
  // 3) Listo: el resultado completo, como lo devolvía la solicitud que esperaba.
  for (;;) {
    const resultado = await request(ruta, { signal, headers: ASINCRONO });
    if (!resultado?.en_curso) return resultado;
    await esperar(CONSULTA_AVANCE_MS, signal);
  }
}

const conAvance = async (respuesta, opciones) => {
  if (!respuesta?.en_curso) return respuesta;
  opciones.alAvance?.({ tipo: 'aceptado', workflow_id: respuesta.workflow_id });
  return esperarFlujo(respuesta.workflow_id, opciones);
};

export const startWorkflow = async (body, opciones = {}) => conAvance(
  await request('', { method: 'POST', body, signal: opciones.signal, headers: ASINCRONO }), opciones,
);
export const getWorkflow = async (workflowId, opciones = {}) => conAvance(
  await request(`/${encodeURIComponent(workflowId)}`, { signal: opciones.signal, headers: ASINCRONO }), opciones,
);
export const resumeWorkflow = async (workflowId, body, opciones = {}) => conAvance(
  await request(`/${encodeURIComponent(workflowId)}/resume`, { method: 'POST', body, signal: opciones.signal, headers: ASINCRONO }),
  opciones,
);

export const listWorkflows = ({ signal } = {}) => request('', { signal });
export const deleteWorkflow = (workflowId, { signal } = {}) => request(
  `/${encodeURIComponent(workflowId)}`, { method: 'DELETE', signal },
);
export const saveWorkflowDraft = (workflowId, respuestas, { signal } = {}) => request(
  `/${encodeURIComponent(workflowId)}/borrador`, { method: 'PUT', body: { respuestas }, signal },
);
export const retryWorkflow = async (workflowId, opciones = {}) => conAvance(
  await request(`/${encodeURIComponent(workflowId)}/reintentar`, { method: 'POST', signal: opciones.signal, headers: ASINCRONO }),
  opciones,
);

export const workflowApi = Object.freeze({
  startWorkflow, getWorkflow, resumeWorkflow, listWorkflows, deleteWorkflow, saveWorkflowDraft, retryWorkflow,
});
