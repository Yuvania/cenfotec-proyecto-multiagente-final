import { expect, test } from './soporte/prueba.js';
import { MODO_REAL, ingresarComo } from './soporte/ambiente.js';

// Básicas (smoke): se ingresa y cada pantalla principal abre. Solo leen, así que también corren contra la
// aplicación publicada con el usuario de QA (ambiente «Producción»). El usuario de QA solo necesita el rol
// «Consulta».
const LISTA_PANTALLA = [
  { ruta: '/', titulo: 'Panel de Historias de Usuario' },
  { ruta: '/historias', titulo: 'Historias de Usuario' },
  { ruta: '/notificaciones', titulo: 'Notificaciones' },
  { ruta: '/ayuda', titulo: 'Centro de Ayuda y Documentación' },
];

test.describe('Básicas', { tag: '@basicas' }, () => {
  test('ingresa y abre las pantallas principales', async ({ page }) => {
    await test.step('Ingresa con su usuario', () => ingresarComo(page));

    for (const pantalla of LISTA_PANTALLA) {
      await test.step(`Abre ${pantalla.titulo}`, async () => {
        await page.goto(pantalla.ruta, { waitUntil: 'domcontentloaded' });
        await expect(page.getByRole('heading', { level: 1, name: pantalla.titulo, exact: true })).toBeVisible();
      });
    }
  });

  test('cerrar sesión pide confirmación y vuelve al ingreso', async ({ page }) => {
    await test.step('Ingresa con su usuario', () => ingresarComo(page));
    await test.step('Toca su nombre para salir', async () => {
      await page.getByRole('button', { name: /Cerrar sesión/ }).click();
      await page.getByRole('alertdialog').getByRole('button', { name: 'Cerrar sesión', exact: true }).click();
    });
    await test.step('Vuelve a pedir el ingreso', async () => {
      await expect(page.getByRole('form', { name: 'Iniciar sesión' })).toBeVisible();
    });
  });

  test('la aplicación responde su chequeo de salud', async ({ request }) => {
    test.skip(!MODO_REAL && !process.env.BASE_URL, 'Con Vite no hay backend: solo aplica contra un contenedor o producción.');
    const respuesta = await request.get('/healthz');
    expect(respuesta.ok()).toBeTruthy();
  });
});
