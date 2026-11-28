import { expect, test } from './soporte/prueba.js';
import { USUARIO_ADMINISTRADOR, ingresarComo } from './soporte/ambiente.js';

const FLUJO_ID = '11111111-1111-4111-8111-111111111111';
const AVISO_ID = '22222222-2222-4222-8222-222222222222';
const LEIDO_ID = '33333333-3333-4333-8333-333333333333';

// Notificaciones: una sola lista con la categoría de cada notificación y filtros arriba.
test.describe('Notificaciones', { tag: '@notificaciones' }, () => {
  let listaAviso;
  let marcado;

  test.beforeEach(async ({ page }) => {
    marcado = false;
    listaAviso = [
      { id: AVISO_ID, tipo: 'devuelta', titulo: 'Consulta de póliza ficticia', workflow_id: FLUJO_ID, leido: false,
        detalle: 'Falta el criterio de pólizas vencidas', autor: 'Product Owner de prueba', creado_en: '2030-01-02T10:00:00Z' },
      { id: LEIDO_ID, tipo: 'aprobada', titulo: 'Alta de beneficiario ficticio', leido: true, autor: 'Product Owner de prueba',
        creado_en: '2030-01-01T10:00:00Z' },
    ];
    const listaPorDecidir = [{
      tipo: 'por_aprobar', workflow_id: FLUJO_ID, titulo: 'Vigencia de póliza ficticia', modo: 'pre_grooming',
      creado_por: 'Analista de prueba', actualizado_en: '2030-01-02T09:00:00Z',
    }];
    await ingresarComo(page, USUARIO_ADMINISTRADOR);
    await page.route('**/api/analista/pendientes', (route) => route.fulfill({ status: 200, json: {
      por_decidir: listaPorDecidir, avisos: listaAviso,
      total: listaPorDecidir.length + listaAviso.filter((aviso) => !aviso.leido).length,
    } }));
    await page.route(`**/api/analista/pendientes/avisos/${AVISO_ID}/leido`, (route) => {
      marcado = true;
      listaAviso = listaAviso.map((aviso) => ({ ...aviso, leido: true }));
      return route.fulfill({ status: 204, body: '' });
    });
    await page.route('**/api/workflows/**', (route) => route.fulfill({ status: 404, json: { error: { code: 'WORKFLOW_NOT_FOUND' } } }));
    await page.goto('/notificaciones', { waitUntil: 'domcontentloaded' });
    await expect(page.getByRole('heading', { level: 1, name: 'Notificaciones' })).toBeVisible();
  });

  test('una sola lista con la categoría de cada notificación; se filtra por categoría', async ({ page }) => {
    const lista = page.getByRole('region', { name: 'Lista de notificaciones' });
    await test.step('Ve primero lo que requiere acción y después los avisos', async () => {
      await expect(lista.getByRole('listitem')).toHaveCount(3);
      await expect(lista.getByRole('listitem').first()).toContainText('Por aprobar');
      await expect(lista.getByRole('listitem').first()).toContainText('Vigencia de póliza ficticia');
      await expect(lista.getByText('Motivo: Falta el criterio de pólizas vencidas')).toBeVisible();
      await expect(page.getByRole('tab')).toHaveCount(0);
    });
    await test.step('Filtra «Requieren acción» y después «Devuelta»', async () => {
      await page.getByRole('button', { name: /Requieren acción/ }).click();
      await expect(lista.getByRole('listitem')).toHaveCount(1);
      await page.getByRole('button', { name: /^Devuelta/ }).click();
      await expect(lista.getByRole('listitem')).toHaveCount(1);
      await expect(lista.getByText('Consulta de póliza ficticia')).toBeVisible();
    });
  });

  test('marca un aviso como leído y sigue en la lista', async ({ page }) => {
    await page.getByRole('button', { name: 'Marcar como leído' }).click();
    await expect.poll(() => marcado).toBe(true);
    await expect(page.getByRole('button', { name: 'Marcar como leído' })).toHaveCount(0);
    await expect(page.getByText('Consulta de póliza ficticia')).toBeVisible();
  });

  test('«Revisar y decidir» abre la historia en el asistente', async ({ page }) => {
    await page.getByRole('button', { name: 'Revisar y decidir' }).click();
    await expect(page).toHaveURL(new RegExp(`/historias/nueva\\?flujo=${FLUJO_ID}$`));
  });
});
