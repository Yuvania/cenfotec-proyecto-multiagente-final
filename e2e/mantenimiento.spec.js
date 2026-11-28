import { expect, test } from './soporte/prueba.js';
import { USUARIO_ADMINISTRADOR, ingresarComo } from './soporte/ambiente.js';

const LISTA_ACCION = [
  { codigo: 'historia.ver', nombre: 'Acceder a Historias de usuario', modulo: 'Historias de usuario' },
  { codigo: 'historia.crear', nombre: 'Crear historia', modulo: 'Historias de usuario' },
  { codigo: 'historia.aprobar', nombre: 'Aprobar historia', modulo: 'Historias de usuario' },
  { codigo: 'prueba.ejecutar', nombre: 'Ejecutar pruebas automatizadas', modulo: 'Pruebas automatizadas' },
];
const LISTA_ROL = [
  { id: 'rol-po', nombre: 'Product Owner', descripcion: 'Aprueba historias.', acciones: ['historia.ver', 'historia.aprobar'], usuarios: 1 },
  { id: 'rol-analista', nombre: 'Analista de negocio', descripcion: 'Crea historias.', acciones: ['historia.ver', 'historia.crear'], usuarios: 1 },
];
const LISTA_USUARIO = [
  { id: 'u-po', usuario: 'po.prueba', nombre: 'Product Owner de prueba', activo: true, roles: [{ id: 'rol-po', nombre: 'Product Owner' }] },
  { id: 'u-an', usuario: 'analista.prueba', nombre: 'Analista de prueba', activo: false, roles: [{ id: 'rol-analista', nombre: 'Analista de negocio' }] },
];

// Mantenimiento › Seguridad: usuarios con sus roles y roles con sus acciones (con nombres legibles, nunca códigos).
test.describe('Mantenimiento › Seguridad', { tag: '@mantenimiento' }, () => {
  test.beforeEach(async ({ page }) => {
    await ingresarComo(page, USUARIO_ADMINISTRADOR);
    await page.route('**/api/analista/mantenimiento/acciones', (route) => route.fulfill({ status: 200, json: LISTA_ACCION }));
    await page.route('**/api/analista/mantenimiento/roles', (route) => route.fulfill({ status: 200, json: LISTA_ROL }));
    await page.route('**/api/analista/mantenimiento/usuarios**', (route) => route.fulfill({ status: 200, json: LISTA_USUARIO }));
  });

  test('lista los usuarios con sus roles', { tag: '@usuarios' }, async ({ page }) => {
    await page.goto('/mantenimiento/usuarios', { waitUntil: 'domcontentloaded' });
    await expect(page.getByRole('heading', { level: 1, name: 'Usuarios' })).toBeVisible();
    const tabla = page.getByRole('table');
    await expect(tabla.getByText('Product Owner de prueba')).toBeVisible();
    await expect(tabla.getByText('analista.prueba')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Nuevo usuario' })).toBeVisible();
  });

  test('las acciones de un rol se muestran por nombre y no por código', { tag: '@roles' }, async ({ page }) => {
    await page.goto('/mantenimiento/roles', { waitUntil: 'domcontentloaded' });
    await expect(page.getByRole('heading', { level: 1, name: 'Roles y acciones' })).toBeVisible();
    await page.getByRole('button', { name: /Product Owner/ }).click();
    const editor = page.getByRole('form', { name: 'Acciones de Product Owner' });
    await expect(editor.getByLabel('Aprobar historia')).toBeChecked();
    await expect(editor.getByLabel('Crear historia')).not.toBeChecked();
    await expect(editor.getByLabel('Ejecutar pruebas automatizadas')).toBeVisible();
    await expect(editor.getByText('historia.aprobar')).toHaveCount(0);
  });
});
