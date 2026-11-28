import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach, vi } from 'vitest';

// Las pruebas corren sin seguridad (como el desarrollo local): la sesión responde que no está activa.
// Una prueba de seguridad puede reemplazar estas funciones con vi.mocked(sesionApi.leer).mockResolvedValue(...).
vi.mock('../services/seguridadApi.js', () => ({
  sesionApi: {
    leer: vi.fn(async () => ({ seguridad: false, usuario: null })),
    iniciar: vi.fn(),
    listarAprobador: vi.fn(async () => []),
  },
  mantenimientoApi: {
    listarAccion: vi.fn(async () => []),
    listarUsuario: vi.fn(async () => []),
    crearUsuario: vi.fn(),
    actualizarUsuario: vi.fn(),
    listarRol: vi.fn(async () => []),
    crearRol: vi.fn(),
    actualizarRol: vi.fn(),
    eliminarRol: vi.fn(),
  },
}));

// Notificaciones: sin nada por decidir, salvo que una prueba diga otra cosa.
vi.mock('../services/pendientesApi.js', () => ({
  pendientesApi: {
    listar: vi.fn(async () => ({ por_decidir: [], avisos: [], total: 0 })),
    marcarLeido: vi.fn(async () => null),
    marcarTodoLeido: vi.fn(async () => null),
  },
}));

// Métricas: sin consumo registrado, salvo que una prueba diga otra cosa.
const TOTAL_VACIO = {
  llamadas: 0, tokens_entrada: 0, tokens_salida: 0, tokens_razonamiento: 0, tokens_cache: 0, tokens_total: 0,
  costo_usd: 0, duracion_ms: 0, fallidas: 0,
};
vi.mock('../services/metricasApi.js', () => ({
  metricasApi: {
    leerConsumo: vi.fn(async (periodo) => ({
      periodo, lista_periodo: [{ codigo: '7', nombre: 'Últimos 7 días' }, { codigo: '30', nombre: 'Últimos 30 días' }, { codigo: 'todo', nombre: 'Todo' }],
      total: TOTAL_VACIO, promedio_creacion: null, promedio_cambio: null, por_agente: [], por_modelo: [], por_dia: [],
      por_flujo: [], prueba: null, aviso_costo: null,
    })),
    leerConsumoHistoria: vi.fn(async (historiaId) => ({ historia_id: historiaId, total: TOTAL_VACIO, por_agente: [], por_flujo: [] })),
  },
}));

afterEach(() => {
  cleanup();
});
