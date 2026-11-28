import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { metricasApi } from '../../../services/metricasApi';
import { ConsumoModeloComponent } from '../ConsumoModeloComponent';
import { ConsumoHistoriaComponent } from '../ConsumoHistoriaComponent';
import { construirSecciones } from '../../HistoriaUsuario/detalle/secciones';
import { formatoCosto, formatoToken, formatoTokenCorto } from '../../../utils/formatoMetricas';

const total = (cambio = {}) => ({
  llamadas: 12, tokens_entrada: 30000, tokens_salida: 8000, tokens_razonamiento: 2000, tokens_cache: 0,
  tokens_total: 40000, costo_usd: 0.0456, duracion_ms: 60000, fallidas: 1, ...cambio,
});

const PANEL = {
  periodo: '30',
  lista_periodo: [{ codigo: '7', nombre: 'Últimos 7 días' }, { codigo: '30', nombre: 'Últimos 30 días' }, { codigo: 'todo', nombre: 'Todo' }],
  total: total(),
  promedio_creacion: { flujos: 2, costo_usd: 0.0181, tokens_total: 16000, llamadas: 5 },
  promedio_cambio: null,
  por_agente: [
    { agente: 'redactor_revisor', nombre: 'Redactor-Revisor', llamadas: 4, tokens_total: 20000, costo_usd: 0.03 },
    { agente: 'analista', nombre: 'Agente Analista', llamadas: 8, tokens_total: 20000, costo_usd: 0.0156 },
  ],
  fiabilidad: [
    { agente: 'asesor_tecnico', nombre: 'Asesor Técnico', turnos: 4, fallidos: 1, con_reintento: 2, reintentos: 5, tasa_fallo: 25, duracion_promedio_ms: 95000, duracion_maxima_ms: 180000 },
    { agente: 'analista', nombre: 'Agente Analista', turnos: 6, fallidos: 0, con_reintento: 0, reintentos: 0, tasa_fallo: 0, duracion_promedio_ms: 40000, duracion_maxima_ms: 61000 },
  ],
  por_modelo: [{ proveedor: 'opencode', modelo: 'glm-5.3-flash', tokens_total: 40000, costo_usd: 0.0456, estimadas: 0, sin_precio: 0 }],
  por_dia: [{ dia: '2026-11-27', costo_usd: 0.02, tokens_total: 18000 }, { dia: '2026-11-28', costo_usd: 0.0256, tokens_total: 22000 }],
  por_flujo: [{
    workflow_id: 'w1', historia_id: 'w1', titulo: 'Consulta de saldos', modo: 'creacion', inicio: '2026-11-28T10:00:00.000+00:00',
    fin: '2026-11-28T10:05:00.000+00:00', agentes: 3, llamadas: 6, tokens_total: 20000, costo_usd: 0.025,
  }],
  prueba: { ejecuciones: 1, llamadas: 5, tokens_total: 9000, costo_usd: 0.004 },
  aviso_costo: 'Algunas llamadas tienen el costo estimado.',
};

describe('Consumo del modelo', () => {
  it('muestra el costo total, el promedio por historia, por agente, por día, por historia y del Agente de Pruebas', async () => {
    vi.mocked(metricasApi.leerConsumo).mockResolvedValueOnce(PANEL);
    render(<MemoryRouter><ConsumoModeloComponent /></MemoryRouter>);

    const indicadores = await screen.findByLabelText('Indicadores');
    await waitFor(() => expect(indicadores).toHaveTextContent(formatoCosto(0.0456)));
    expect(indicadores).toHaveTextContent(formatoTokenCorto(40000));
    expect(within(indicadores).getByText('Costo promedio por historia creada').parentElement).toHaveTextContent(formatoCosto(0.0181));
    expect(indicadores).toHaveTextContent(`+ ${formatoCosto(0.004)} del Agente de Pruebas`);
    expect(indicadores).toHaveTextContent('1 con error (también se cobran)');
    expect(screen.getByText('Algunas llamadas tienen el costo estimado.')).toBeInTheDocument();

    const porAgente = screen.getByRole('table', { name: 'Costo por agente' });
    expect(within(porAgente).getAllByRole('rowheader').map((celda) => celda.textContent)).toEqual(['Redactor-Revisor', 'Agente Analista']);
    expect(screen.getByRole('table', { name: 'Consumo por historia' })).toHaveTextContent('Consulta de saldos');
    // Los miles usan espacio fino (es-CR): se compara sin espacios.
    const tokens = screen.getByRole('table', { name: 'Consumo por historia' }).querySelector('td[data-etiqueta="Tokens"]');
    expect(tokens.textContent.replace(/\s/g, '')).toBe(formatoToken(20000).replace(/\s/g, ''));
    expect(screen.getByText(/Diagnosticó fallos en 1 ejecución/)).toBeInTheDocument();
    const fiabilidad = screen.getByRole('table', { name: 'Fiabilidad por agente' });
    const asesor = within(fiabilidad).getByRole('rowheader', { name: 'Asesor Técnico' }).closest('tr');
    expect(asesor).toHaveTextContent('25 %');
    expect(asesor).toHaveTextContent('01:35');
    expect(asesor).toHaveTextContent('03:00');
    expect(screen.getByText('Costo por día', { selector: 'caption' })).toBeInTheDocument();
  });

  it('cambia de periodo con el filtro', async () => {
    const user = userEvent.setup();
    render(<MemoryRouter><ConsumoModeloComponent /></MemoryRouter>);
    const filtro = await screen.findByRole('button', { name: 'Últimos 7 días' });
    await user.click(filtro);
    await waitFor(() => expect(metricasApi.leerConsumo).toHaveBeenLastCalledWith('7', expect.anything()));
    expect(filtro).toHaveAttribute('aria-pressed', 'true');
    expect(await screen.findByText(/Todavía no hay consumo registrado en este periodo/)).toBeInTheDocument();
  });
});

describe('Consumo de una historia', () => {
  it('solo aparece para quien puede ver las métricas', () => {
    expect(construirSecciones({}).map((s) => s.id)).not.toContain('consumo');
    expect(construirSecciones({}, { puedeVerConsumo: true }).map((s) => s.id)).toContain('consumo');
  });

  it('muestra lo que costó la historia por agente y sus cambios', async () => {
    vi.mocked(metricasApi.leerConsumoHistoria).mockResolvedValueOnce({
      historia_id: 'h1', total: total({ costo_usd: 0.031, tokens_total: 25000, llamadas: 9 }),
      por_agente: PANEL.por_agente,
      por_flujo: [PANEL.por_flujo[0], { ...PANEL.por_flujo[0], workflow_id: 'w2', modo: 'cambio', titulo: 'Agregar plazo' }],
    });
    render(<MemoryRouter><ConsumoHistoriaComponent historiaId="h1" /></MemoryRouter>);
    expect(await screen.findByText(formatoCosto(0.031))).toBeInTheDocument();
    expect(screen.getByText(/25.000 tokens|25 000 tokens/)).toBeInTheDocument();
    expect(screen.getByRole('table', { name: 'Consumo de la historia por agente' })).toHaveTextContent('Redactor-Revisor');
    expect(screen.getByRole('table', { name: 'Consumo de la historia por creación y cambios' })).toHaveTextContent('Cambio');
    expect(metricasApi.leerConsumoHistoria).toHaveBeenCalledWith('h1', expect.anything());
  });

  it('sin datos explica desde cuándo se mide', async () => {
    render(<MemoryRouter><ConsumoHistoriaComponent historiaId="vieja" /></MemoryRouter>);
    expect(await screen.findByText(/No hay consumo registrado para esta historia/)).toBeInTheDocument();
  });
});

describe('formato de las métricas', () => {
  it('muestra fracciones de centavo y tokens legibles', () => {
    expect(formatoCosto(0)).toBe('US$0');
    expect(formatoCosto(0.00002)).toBe('menos de US$0,0001');
    expect(formatoCosto(0.0021)).toBe('US$0,0021');
    expect(formatoCosto(1.5)).toBe('US$1,50');
    expect(formatoTokenCorto(1_250_000)).toBe('1,3 M');
    expect(formatoTokenCorto(45_600)).toBe('45,6 mil');
  });
});
