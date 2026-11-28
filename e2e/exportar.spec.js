import { expect, test } from './soporte/prueba.js';
import { abrirSinSeguridad } from './soporte/ambiente.js';

const HISTORIA = {
  id: 'HU-E2E-001', number: 'HU-E2E-001', code: 'TEST-001', title: 'Consulta de póliza ficticia', status: 'aprobada',
  createdAt: '2030-01-01', createdBy: 'Analista de prueba', infoType: 'Minuta', description: 'Consultar una póliza ficticia.',
  userStory: { asA: 'persona usuaria ficticia', iWant: 'consultar una póliza ficticia', soThat: 'conocer su vigencia' },
  acceptanceCriteria: [{ id: 'c1', given: 'una póliza ficticia', when: 'consulto el detalle', then: 'veo su vigencia' }],
  questions: [{ id: 'q1', category: 'Datos requeridos', question: '¿Qué fecha se muestra?', answer: 'La de vigencia', status: 'respondida' }],
  bitacora: [],
};

// Exportar una historia aprobada a Word y a PDF desde el ícono de descarga del listado.
test.describe('Exportar Word y PDF', { tag: ['@historias', '@exportar'] }, () => {
  for (const formato of [{ nombre: 'Word', extension: '.docx' }, { nombre: 'PDF', extension: '.pdf' }]) {
    test(`descarga la historia aprobada en ${formato.nombre}`, async ({ page }) => {
      await abrirSinSeguridad(page, '/', { listaHistoria: [HISTORIA] });
      await page.evaluate((historia) => localStorage.setItem('historias_usuario_prototipo', JSON.stringify([historia])), HISTORIA);

      await test.step('Abre el listado de historias', async () => {
        await page.goto('/historias', { waitUntil: 'domcontentloaded' });
        await expect(page.getByText(HISTORIA.title).first()).toBeVisible();
      });
      await test.step(`Elige Descargar → ${formato.nombre}`, async () => {
        await page.getByRole('button', { name: 'Descargar' }).first().click();
        const descarga = page.waitForEvent('download');
        await page.getByRole('menuitem', { name: formato.nombre }).click();
        const archivo = await descarga;
        expect(archivo.suggestedFilename()).toMatch(new RegExp(`\\${formato.extension}$`));
        expect(await archivo.failure()).toBeNull();
      });
    });
  }
});
