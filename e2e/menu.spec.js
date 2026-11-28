import { expect, test } from './soporte/prueba.js';
import { USUARIO_ADMINISTRADOR, ingresarComo } from './soporte/ambiente.js';

// Menú de 2 niveles como máximo: Mantenimiento › Pruebas automatizadas. Dentro del grupo, las secciones
// (Seguridad, Calidad, Métricas) son solo títulos que ordenan el panel; no son un nivel.
// En web se despliega en la barra lateral, en tablet abre un panel y en móvil va dentro de «Más».
test.describe('Menú principal', { tag: '@inicio-sesion' }, () => {
  test('llega a Pruebas automatizadas por Mantenimiento', async ({ page }, testInfo) => {
    await ingresarComo(page, USUARIO_ADMINISTRADOR);
    await page.route('**/api/analista/pruebas/**', (route) => route.fulfill({ status: 200, json: {
      configurado: false, faltante: ['GITHUB_PRUEBAS_TOKEN'], lista_menu: [], lista_alcance: [], lista_ambiente: [], lista_navegador: [],
      indicador: { ultima: null, tasa_exito: null }, activa: null, lista_ejecucion: [],
    } }));
    const movil = testInfo.project.name === 'movil';

    await test.step(movil ? 'Abre «Más»' : 'Abre Mantenimiento', async () => {
      if (movil) {
        await page.getByRole('button', { name: 'Más opciones' }).click();
      } else {
        const grupo = page.getByRole('button', { name: 'Mantenimiento' });
        await grupo.click();
        await expect(grupo).toHaveAttribute('aria-expanded', 'true');
      }
    });

    await test.step('Ve Seguridad y Calidad con sus opciones', async () => {
      const contenedor = movil ? page.getByRole('dialog', { name: 'Más opciones' }) : page.getByRole('navigation', { name: 'Menú principal' });
      await expect(contenedor.getByRole('group', { name: 'Seguridad' })).toBeVisible();
      await expect(contenedor.getByRole('link', { name: 'Usuarios' })).toBeVisible();
      await expect(contenedor.getByRole('link', { name: 'Roles y acciones' })).toBeVisible();
      await contenedor.getByRole('group', { name: 'Calidad' }).getByRole('link', { name: 'Pruebas automatizadas' }).click();
    });

    await test.step('Abre la pantalla y la ruta dice dónde está', async () => {
      await expect(page).toHaveURL(/\/mantenimiento\/pruebas$/);
      await expect(page.getByRole('heading', { level: 1, name: 'Pruebas automatizadas' })).toBeVisible();
      await expect(page.getByRole('navigation', { name: 'Está en' })).toHaveText(/^\s*Mantenimiento\s*›\s*Pruebas automatizadas\s*$/);
    });
  });

  test('las direcciones viejas llevan a las nuevas', async ({ page }) => {
    await ingresarComo(page, USUARIO_ADMINISTRADOR);
    await page.goto('/pendientes', { waitUntil: 'domcontentloaded' });
    await expect(page).toHaveURL(/\/notificaciones$/);
    await page.goto('/mantenimiento', { waitUntil: 'domcontentloaded' });
    await expect(page).toHaveURL(/\/mantenimiento\/usuarios$/);
  });
});
