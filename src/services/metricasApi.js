import { request } from './analystApi.js';

// Métricas: consumo de tokens y costo del modelo por historia, por agente y por día; y observabilidad
// (latencia por paso, alertas y estado de cada traza).
export const metricasApi = Object.freeze({
  leerObservabilidad: (periodo, { signal } = {}) => request(`/metricas/observabilidad?periodo=${encodeURIComponent(periodo)}`, { signal }),
  leerConsumo: (periodo, { signal } = {}) => request(`/metricas/consumo?periodo=${encodeURIComponent(periodo)}`, { signal }),
  leerConsumoHistoria: (historiaId, { signal } = {}) => request(
    `/metricas/consumo/historias/${encodeURIComponent(historiaId)}`, { signal },
  ),
});
