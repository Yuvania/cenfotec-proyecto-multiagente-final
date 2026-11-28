import React from 'react';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { AvanceAgentesComponent } from '../AvanceAgentesComponent';
import { listarFuentes, resumirAvance } from '../../../../utils/formatoAvance';

const T0 = Date.parse('2030-01-01T10:00:00Z');
const en = (segundos) => new Date(T0 + segundos * 1000).toISOString();

const EVENTOS = [
  { tipo: 'inicio', momento: en(0) },
  { tipo: 'agente_inicio', agente: 'analista', momento: en(1) },
  { tipo: 'agente_consulta', agente: 'analista', herramientas: ['consultar_glosario', 'buscar_hu_similares', 'consultar_estandares'], momento: en(2) },
  { tipo: 'agente_fin', agente: 'analista', exitoso: true, intentos: 1, duracion_ms: 72000, momento: en(73) },
  { tipo: 'agente_inicio', agente: 'asesor_tecnico', momento: en(74) },
  { tipo: 'agente_reintento', agente: 'asesor_tecnico', intento: 1, de: 3, espera_ms: 4000, codigo: 'OPENCODE_UNAVAILABLE', momento: en(80) },
];

describe('avance de los agentes', () => {
  it('resume por agente: terminado, trabajando, qué consulta y el reintento', () => {
    const { filas, iniciado, enCola } = resumirAvance(EVENTOS, T0 + 90_000);
    expect(iniciado).toBe(true);
    expect(enCola).toBeNull();
    expect(filas.map((f) => [f.nombre, f.estado])).toEqual([['Agente Analista', 'listo'], ['Asesor Técnico', 'trabajando']]);
    expect(filas[0].duracionMs).toBe(72000);
    expect(filas[1].reintento).toMatchObject({ texto: 'El proveedor del modelo no respondió.', espera: 4, intento: 1 });
    // Reloj del navegador 2 minutos adelantado: se corrige con la hora en que llegó el último evento.
    const conRecibido = EVENTOS.map((e, i) => (i === EVENTOS.length - 1 ? { ...e, recibido: T0 + 80_000 + 120_000 } : e));
    expect(resumirAvance(conRecibido, T0 + 90_000 + 120_000).filas[1].duracionMs).toBe(16_000);
    expect(listarFuentes(['consultar_glosario', 'buscar_hu_similares', 'leer_archivo_codigo', 'buscar_referencias_codigo']))
      .toBe('el glosario, HU similares y el código');
  });

  it('muestra la cola, los agentes con su estado y deja salir de la pantalla', async () => {
    const usuario = userEvent.setup();
    const onSalir = vi.fn();
    const { rerender } = render(<AvanceAgentesComponent eventos={[{ tipo: 'en_cola', puesto: 2, momento: en(0) }]} onSalir={onSalir} />);
    expect(screen.getByText(/En cola: hay 2 historias antes que esta/)).toBeInTheDocument();

    rerender(<AvanceAgentesComponent eventos={EVENTOS} onSalir={onSalir} />);
    const avance = screen.getByRole('region', { name: 'Avance de los agentes' });
    const asesor = within(avance).getByText('Asesor Técnico').closest('li');
    expect(asesor).toHaveTextContent('trabajando');
    expect(within(asesor).getByRole('status')).toHaveTextContent('Reintento en 4 s (intento 2 de 4)');
    expect(within(avance).getByText('Agente Analista').closest('li')).toHaveTextContent('1 min 12 s');
    await usuario.click(screen.getByRole('button', { name: 'Ir a mis historias' }));
    expect(onSalir).toHaveBeenCalledTimes(1);
  });
});
