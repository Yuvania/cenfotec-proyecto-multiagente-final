// Reportero propio: escribe resumen.json, lo que lee el tablero «Pruebas automatizadas».
// Los demás reportes (HTML, JUnit, JSON completo, capturas y trazas) los genera Playwright y quedan como
// evidencias en GitHub. El backend valida este archivo (agentes/pruebas/pruebas_service.py, ResumenEjecucion).
import fs from 'node:fs';
import path from 'node:path';

const ANSI = /\u001b\[[0-9;]*m/g;
const ESTADO = Object.freeze({ expected: 'aprobado', unexpected: 'fallido', flaky: 'inestable', skipped: 'omitido' });

const limpiar = (texto, maximo) => (texto ? String(texto).replace(ANSI, '').trim().slice(0, maximo) : null);

// Evidencia de un caso fallido para el Agente de Pruebas: la página al fallar y la consola y la API.
const leerAdjunto = (adjunto) => {
  try {
    if (adjunto?.body) return adjunto.body.toString('utf8');
    if (adjunto?.path) return fs.readFileSync(adjunto.path, 'utf8');
  } catch (error) {
    console.warn(`No se pudo leer el adjunto ${adjunto?.name}: ${error.message}`);
  }
  return null;
};

const evidencia = (result) => {
  const adjunto = (nombre) => (result.attachments ?? []).find((item) => item.name === nombre);
  let registro = [];
  try {
    registro = JSON.parse(leerAdjunto(adjunto('consola-y-red')) ?? '[]');
  } catch (error) {
    console.warn(`Registro de consola y red no válido: ${error.message}`);
  }
  // Playwright encabeza el archivo con instrucciones para una IA: se quitan, el agente tiene las suyas.
  const contexto = (leerAdjunto(adjunto('error-context')) ?? '').replace(/^# Instructions[\s\S]*?(?=^# )/m, '');
  return { contexto_pagina: limpiar(contexto, 12000), registro: registro.slice(-50) };
};

export default class ReporteroResumen {
  constructor({ archivo = 'reportes/resumen.json' } = {}) {
    this.archivo = archivo;
    this.porCaso = new Map();
    this.inicio = new Date();
  }

  onBegin(config) {
    this.navegador = config.projects[0]?.use?.browserName ?? 'chromium';
  }

  onTestEnd(test, result) {
    // Con reintentos se llama una vez por intento: queda el último.
    const lista = test.titlePath().filter(Boolean);
    const estado = ESTADO[test.outcome()] ?? 'fallido';
    // El módulo es la etiqueta más específica: la de la pantalla (@roles), no la de su opción del menú.
    const listaEtiqueta = (test.tags ?? []).filter((tag) => tag !== '@basicas');
    const etiqueta = listaEtiqueta[listaEtiqueta.length - 1] ?? (test.tags ?? [])[0] ?? '';
    this.porCaso.set(test.id, {
      id: test.id,
      titulo: test.title,
      modulo: etiqueta.replace(/^@/, ''),
      archivo: path.basename(test.location.file),
      dispositivo: lista[0] ?? '',
      estado,
      duracion_ms: Math.max(0, Math.round(result.duration)),
      error: limpiar(result.error?.message, 1500),
      pasos: (result.steps ?? []).filter((paso) => paso.category === 'test.step').map((paso) => limpiar(paso.title, 200)),
      ...(estado === 'fallido' ? evidencia(result) : {}),
    });
  }

  onEnd(result) {
    const listaCaso = [...this.porCaso.values()];
    const cuenta = (estado) => listaCaso.filter((caso) => caso.estado === estado).length;
    const resumen = {
      version: 1,
      inicio: this.inicio.toISOString(),
      duracion_ms: Math.max(0, Math.round(result.duration)),
      navegador: this.navegador,
      total: listaCaso.length,
      aprobados: cuenta('aprobado'),
      fallidos: cuenta('fallido'),
      inestables: cuenta('inestable'),
      omitidos: cuenta('omitido'),
      // Primero los fallidos: es lo que la persona quiere ver.
      casos: listaCaso.sort((a, b) => Number(b.estado === 'fallido') - Number(a.estado === 'fallido')),
    };
    fs.mkdirSync(path.dirname(this.archivo), { recursive: true });
    fs.writeFileSync(this.archivo, JSON.stringify(resumen, null, 2));
  }

  printsToStdio() {
    return false;
  }
}
