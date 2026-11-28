import { expect, test } from './soporte/prueba.js';
import { USUARIO_ADMINISTRADOR, USUARIO_CONSULTA, ingresarComo } from './soporte/ambiente.js';

// Mantenimiento › Métricas › Consumo del modelo, con la API simulada (no gasta cuota del modelo).
const PANEL = {
  periodo: '30',
  lista_periodo: [{ codigo: '7', nombre: 'Últimos 7 días' }, { codigo: '30', nombre: 'Últimos 30 días' }, { codigo: 'todo', nombre: 'Todo' }],
  total: {
    llamadas: 14, tokens_entrada: 52000, tokens_salida: 9000, tokens_razonamiento: 3000, tokens_cache: 0, tokens_total: 64000,
    costo_usd: 0.0612, duracion_ms: 90000, fallidas: 0,
  },
  promedio_creacion: { flujos: 2, costo_usd: 0.0251, tokens_total: 26000, llamadas: 6 },
  promedio_cambio: { flujos: 1, costo_usd: 0.011, tokens_total: 12000, llamadas: 2 },
  por_agente: [
    { agente: 'redactor_revisor', nombre: 'Redactor-Revisor', llamadas: 4, tokens_total: 26000, costo_usd: 0.028 },
    { agente: 'analista', nombre: 'Agente Analista', llamadas: 6, tokens_total: 22000, costo_usd: 0.019 },
    { agente: 'asesor_tecnico', nombre: 'Asesor Técnico', llamadas: 2, tokens_total: 10000, costo_usd: 0.009 },
    { agente: 'gestor_cambios', nombre: 'Gestor de Cambios', llamadas: 2, tokens_total: 6000, costo_usd: 0.0052 },
  ],
  fiabilidad: [
    { agente: 'asesor_tecnico', nombre: 'Asesor Técnico', turnos: 3, fallidos: 1, con_reintento: 1, reintentos: 3, tasa_fallo: 33.3, duracion_promedio_ms: 80000, duracion_maxima_ms: 150000 },
    { agente: 'analista', nombre: 'Agente Analista', turnos: 6, fallidos: 0, con_reintento: 1, reintentos: 1, tasa_fallo: 0, duracion_promedio_ms: 42000, duracion_maxima_ms: 70000 },
  ],
  por_modelo: [{ proveedor: 'opencode', modelo: 'glm-5.3-flash', tokens_total: 64000, costo_usd: 0.0612, estimadas: 0, sin_precio: 0 }],
  por_dia: [
    { dia: '2030-01-01', costo_usd: 0.021, tokens_total: 20000 },
    { dia: '2030-01-02', costo_usd: 0.0402, tokens_total: 44000 },
  ],
  por_flujo: [
    { workflow_id: 'w2', historia_id: 'w1', titulo: 'Agregar el plazo de pago', modo: 'cambio', inicio: '2030-01-02T10:00:00Z',
      fin: '2030-01-02T10:03:00Z', agentes: 2, llamadas: 2, tokens_total: 12000, costo_usd: 0.011 },
    { workflow_id: 'w1', historia_id: 'w1', titulo: 'Consulta de saldos', modo: 'creacion', inicio: '2030-01-01T10:00:00Z',
      fin: '2030-01-01T10:06:00Z', agentes: 3, llamadas: 7, tokens_total: 30000, costo_usd: 0.029 },
  ],
  prueba: { ejecuciones: 0, llamadas: 0, tokens_total: 0, costo_usd: 0 },
  aviso_costo: null,
};

test.describe('Consumo del modelo', { tag: ['@mantenimiento', '@consumo'] }, () => {
  test('muestra cuánto cuesta cada historia y cada agente, y filtra por periodo', async ({ page }) => {
    const periodos = [];
    await ingresarComo(page, USUARIO_ADMINISTRADOR);
    await page.route('**/api/analista/metricas/consumo?**', (route) => {
      periodos.push(new URL(route.request().url()).searchParams.get('periodo'));
      return route.fulfill({ status: 200, json: { ...PANEL, periodo: periodos.at(-1) } });
    });

    await test.step('Abre la pantalla desde Mantenimiento › Métricas', async () => {
      await page.goto('/mantenimiento/consumo', { waitUntil: 'domcontentloaded' });
      await expect(page.getByRole('heading', { level: 1, name: 'Consumo del modelo' })).toBeVisible();
      await expect(page.getByRole('navigation', { name: 'Está en' })).toContainText('Métricas');
    });

    await test.step('Ve el costo total y el promedio por historia creada', async () => {
      const indicadores = page.getByLabel('Indicadores');
      await expect(indicadores).toContainText('US$0,061');
      await expect(indicadores).toContainText('Costo promedio por historia creada');
      await expect(indicadores).toContainText('US$0,025');
    });

    await test.step('Ve el costo por agente y por historia', async () => {
      const porAgente = page.getByRole('table', { name: 'Costo por agente' });
      await expect(porAgente.getByRole('rowheader')).toHaveText(['Redactor-Revisor', 'Agente Analista', 'Asesor Técnico', 'Gestor de Cambios']);
      const porHistoria = page.getByRole('table', { name: 'Consumo por historia' });
      await expect(porHistoria).toContainText('Consulta de saldos');
      await expect(porHistoria).toContainText('Cambio');
    });

    await test.step('Ve la fiabilidad de cada agente', async () => {
      const fiabilidad = page.getByRole('table', { name: 'Fiabilidad por agente' });
      await expect(fiabilidad.getByRole('row', { name: /Asesor Técnico/ })).toContainText('33,3 %');
    });

    await test.step('Cambia el periodo a los últimos 7 días', async () => {
      await page.getByRole('button', { name: 'Últimos 7 días' }).click();
      await expect(page.getByRole('button', { name: 'Últimos 7 días' })).toHaveAttribute('aria-pressed', 'true');
      await expect.poll(() => periodos.at(-1)).toBe('7');
    });
  });

  test('sin la acción de métricas no aparece en el menú', async ({ page }) => {
    await ingresarComo(page, USUARIO_CONSULTA);
    await expect(page.getByRole('link', { name: 'Consumo del modelo' })).toHaveCount(0);
  });
});
