// Avance de los agentes en segundo plano, en palabras de la persona usuaria.
export const NOMBRE_AGENTE = Object.freeze({
  analista: 'Agente Analista',
  asesor_tecnico: 'Asesor Técnico',
  redactor_revisor: 'Redactor-Revisor',
  gestor_cambios: 'Gestor de Cambios',
  probador: 'Agente de Pruebas',
});

export const NOMBRE_HERRAMIENTA = Object.freeze({
  consultar_glosario: 'el glosario',
  buscar_hu_similares: 'HU similares',
  consultar_estandares: 'los estándares',
  aplicar_checklist_vacios: 'el checklist de vacíos',
  consultar_lecciones: 'las lecciones aprendidas',
  consultar_codigo_demo: 'el código',
  buscar_referencias_codigo: 'el código',
  leer_archivo_codigo: 'el código',
  consultar_asesor_tecnico: 'el criterio del Asesor Técnico',
});

const MOTIVO_REINTENTO = Object.freeze({
  TURN_TIMEOUT: 'El agente tardó más de lo permitido.',
  WORKFLOW_TIMEOUT: 'El agente tardó más de lo permitido.',
  OPENCODE_UNAVAILABLE: 'El proveedor del modelo no respondió.',
  OPENCODE_RATE_LIMITED: 'Se agotó la cuota del modelo; vuelve en menos de un minuto.',
});

// «el glosario, HU similares y los estándares».
export const listarFuentes = (herramientas = []) => {
  const nombres = [...new Set(herramientas.map((nombre) => NOMBRE_HERRAMIENTA[nombre] ?? nombre))];
  if (nombres.length <= 1) return nombres.join('');
  return `${nombres.slice(0, -1).join(', ')} y ${nombres.at(-1)}`;
};

const segundos = (ms) => Math.max(1, Math.round((ms ?? 0) / 1000));

/** Resume los eventos en: cola, una fila por agente (en el orden en que empezaron) y si terminó.
 * Los tiempos se miden con el reloj del servidor: «recibido» (cuándo llegó al navegador) corrige la diferencia. */
export const resumirAvance = (eventos = [], ahoraNavegador = Date.now()) => {
  const conHora = [...eventos].reverse().find((evento) => evento.recibido && Date.parse(evento.momento));
  const ahora = conHora ? ahoraNavegador - (conHora.recibido - Date.parse(conHora.momento)) : ahoraNavegador;
  const porAgente = new Map();
  let enCola = null;
  let fin = null;
  let iniciado = false;
  eventos.forEach((evento) => {
    if (evento.tipo === 'en_cola') enCola = evento.puesto ?? 1;
    if (evento.tipo === 'inicio') { enCola = null; iniciado = true; }
    if (evento.tipo === 'fin') fin = evento;
    if (!evento.agente) return;
    // Un agente puede volver a trabajar en el mismo flujo (por ejemplo, el Analista después de las respuestas).
    if (evento.tipo === 'agente_inicio' || !porAgente.has(evento.agente)) {
      porAgente.set(evento.agente, {
        agente: evento.agente, nombre: NOMBRE_AGENTE[evento.agente] ?? evento.agente, estado: 'trabajando',
        desde: Date.parse(evento.momento) || ahora, fuentes: '', reintento: null, duracionMs: null,
      });
    }
    const fila = porAgente.get(evento.agente);
    if (evento.tipo === 'agente_consulta') {
      fila.fuentes = listarFuentes(evento.herramientas);
      fila.reintento = null;
    } else if (evento.tipo === 'agente_reintento') {
      fila.reintento = {
        texto: MOTIVO_REINTENTO[evento.codigo] ?? 'Falló algo pasajero.',
        espera: segundos(evento.espera_ms), intento: evento.intento, de: evento.de ?? 3,
      };
    } else if (evento.tipo === 'agente_fin') {
      fila.estado = evento.exitoso ? 'listo' : 'fallo';
      fila.duracionMs = evento.duracion_ms;
      fila.reintento = null;
    }
  });
  const filas = [...porAgente.values()].map((fila) => ({
    ...fila, duracionMs: fila.duracionMs ?? Math.max(0, ahora - fila.desde),
  }));
  return { enCola, iniciado, fin, filas };
};

// 72000 → «1 min 12 s»; 8000 → «8 s».
export const duracionCorta = (ms) => {
  const total = Math.max(0, Math.round((ms ?? 0) / 1000));
  const minutos = Math.floor(total / 60);
  return minutos ? `${minutos} min ${total % 60} s` : `${total} s`;
};
