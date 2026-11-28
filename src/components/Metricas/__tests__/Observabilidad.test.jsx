import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { metricasApi } from '../../../services/metricasApi';
import { ObservabilidadComponent } from '../ObservabilidadComponent';

const PANEL = {
  periodo: '7',
  lista_periodo: [{ codigo: '7', nombre: 'Últimos 7 días' }, { codigo: '30', nombre: 'Últimos 30 días' }, { codigo: 'todo', nombre: 'Todo' }],
  umbral: { paso_ms: 180000 },
  presupuesto: { mensual_usd: 60, historia_usd: 0.5, gastado_mes_usd: 51, porcentaje_mes: 85 },
  alerta: [
    { id: 'cuota', nivel: 'critica', titulo: 'Se agotó la cuota del modelo en la última hora', detalle: '1 paso(s) no pudieron terminar.' },
    { id: 'costo_alto', nivel: 'advertencia', titulo: '1 historia(s) costaron más del doble del promedio', detalle: 'Promedio: US$0,0100.',
      lista: [{ workflow_id: 'w2', titulo: 'Endoso de póliza' }] },
  ],
  latencia_agente: [
    { agente: 'asesor_tecnico', nombre: 'Asesor Técnico', cantidad: 4, p50_ms: 30000, p95_ms: 200000, maxima_ms: 200000, lentos: 1 },
  ],
  latencia_herramienta: [
    { herramienta: 'consultar_glosario', nombre: 'Glosario', cantidad: 9, p50_ms: 120, p95_ms: 900, maxima_ms: 900, fallidas: 0 },
  ],
  traza: [
    {
      workflow_id: 'w1', titulo: 'Consulta de saldos', modo: 'creacion', estado: 'con_reintento', inicio: '2026-11-28T10:00:00.000+00:00',
      fin: '2026-11-28T10:05:00.000+00:00', duracion_ms: 95000, costo_usd: 0.02, consultas_mcp: 5, lento: false,
      paso: [
        { agente: 'analista', nombre: 'Agente Analista', duracion_ms: 40000, intentos: 1, exitoso: true, codigo_error: null },
        { agente: 'redactor_revisor', nombre: 'Redactor-Revisor', duracion_ms: 55000, intentos: 2, exitoso: true, codigo_error: null },
      ],
    },
    {
      workflow_id: 'w2', titulo: 'Endoso de póliza', modo: 'cambio', estado: 'detenida', inicio: '2026-11-28T11:00:00.000+00:00',
      fin: '2026-11-28T11:02:00.000+00:00', duracion_ms: 20000, costo_usd: 0.6, consultas_mcp: 1, lento: false,
      paso: [{ agente: 'gestor_cambios', nombre: 'Gestor de Cambios', duracion_ms: 20000, intentos: 1, exitoso: false, codigo_error: 'PRESUPUESTO_AGOTADO' }],
    },
  ],
};

const mostrar = () => render(<MemoryRouter><ObservabilidadComponent /></MemoryRouter>);

describe('ObservabilidadComponent', () => {
  it('muestra alertas, tope de gasto, latencias y trazas con su estado en texto', async () => {
    metricasApi.leerObservabilidad.mockResolvedValueOnce(PANEL);
    const user = userEvent.setup();
    mostrar();

    const alertas = await screen.findByRole('list', { name: 'Alertas' });
    expect(within(alertas).getByText(/Crítica: Se agotó la cuota/)).toBeInTheDocument();
    expect(within(alertas).getByText(/Advertencia: 1 historia/)).toBeInTheDocument();
    expect(within(alertas).getByText('Endoso de póliza')).toBeInTheDocument();

    expect(screen.getByRole('meter', { name: 'Gasto del mes' })).toHaveAttribute('aria-valuenow', '85');
    expect(screen.getByText(/Cada historia puede gastar hasta US\$0,500/)).toBeInTheDocument();

    const agente = screen.getByRole('table', { name: 'Latencia por agente' });
    const asesor = within(agente).getByRole('rowheader', { name: 'Asesor Técnico' }).closest('tr');
    expect(within(asesor).getAllByText('03:20')).toHaveLength(2);
    expect(within(screen.getByRole('table', { name: 'Latencia por fuente' })).getByRole('rowheader', { name: 'Glosario' })).toBeInTheDocument();

    const trazas = screen.getByRole('list', { name: 'Trazas' });
    expect(within(trazas).getByText('Terminó con reintentos')).toBeInTheDocument();
    expect(within(trazas).getByText('Detenida por el tope de gasto')).toBeInTheDocument();
    await user.click(within(trazas).getByRole('button', { name: 'Ver 2 pasos' }));
    const pasos = screen.getByRole('list', { name: 'Pasos de Consulta de saldos' });
    expect(within(pasos).getByText('Respondió al intento 2')).toBeInTheDocument();
  });

  it('sin alertas lo dice, y cambia el periodo', async () => {
    const user = userEvent.setup();
    mostrar();
    expect(await screen.findByText('Ningún umbral se superó en este periodo.')).toBeInTheDocument();
    expect(screen.getByText('Sin trazas en este periodo.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Todo' }));
    await waitFor(() => expect(metricasApi.leerObservabilidad).toHaveBeenLastCalledWith('todo', expect.anything()));
  });
});
