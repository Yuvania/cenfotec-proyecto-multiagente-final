import { request } from './analystApi.js';

// Métricas: consumo de tokens y costo del modelo por historia, por agente y por día.
export const metricasApi = Object.freeze({
  leerConsumo: (periodo, { signal } = {}) => request(`/metricas/consumo?periodo=${encodeURIComponent(periodo)}`, { signal }),
  leerConsumoHistoria: (historiaId, { signal } = {}) => request(
    `/metricas/consumo/historias/${encodeURIComponent(historiaId)}`, { signal },
  ),
});
