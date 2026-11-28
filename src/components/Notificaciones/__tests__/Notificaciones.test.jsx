import React from 'react';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { NotificacionesComponent, unirNotificaciones } from '../NotificacionesComponent';
import { pendientesApi } from '../../../services/pendientesApi';

const POR_DECIDIR = [
  { tipo: 'por_aprobar', workflow_id: 'f-1', titulo: 'Vigencia de póliza ficticia', creado_por: 'Analista de prueba', actualizado_en: '2030-01-02T10:00:00Z' },
  { tipo: 'cambio_por_decidir', workflow_id: 'f-2', titulo: 'Consulta de póliza ficticia', actualizado_en: '2030-01-02T08:00:00Z' },
];
const AVISOS = [
  { id: 'a-1', tipo: 'aprobada', titulo: 'Alta de beneficiario ficticio', creado_en: '2030-01-05T10:00:00Z', leido: true },
  { id: 'a-2', tipo: 'devuelta', titulo: 'Renovación ficticia', workflow_id: 'f-3', detalle: 'Falta un criterio', creado_en: '2030-01-01T10:00:00Z', leido: false },
];

const abrir = () => render(
  <MemoryRouter initialEntries={['/notificaciones']}>
    <Routes>
      <Route path="/notificaciones" element={<NotificacionesComponent />} />
      <Route path="/historias/nueva" element={<p>Asistente abierto</p>} />
    </Routes>
  </MemoryRouter>,
);

describe('Notificaciones', () => {
  beforeEach(() => {
    vi.mocked(pendientesApi.listar).mockResolvedValue({ por_decidir: POR_DECIDIR, avisos: AVISOS, total: 3 });
  });

  it('ordena: primero lo que requiere acción, después lo no leído y al final lo leído', () => {
    const lista = unirNotificaciones(POR_DECIDIR, AVISOS);
    expect(lista.map((item) => item.categoria)).toEqual(['por_aprobar', 'cambio_por_decidir', 'devuelta', 'aprobada']);
    expect(lista[0].detalle).toBe('Analista de prueba la envió para su aprobación.');
    expect(lista[2].detalle).toBe('Motivo: Falta un criterio');
  });

  it('muestra una sola lista con la categoría de cada notificación y filtra por categoría', async () => {
    const usuario = userEvent.setup();
    abrir();
    const lista = await screen.findByRole('region', { name: 'Lista de notificaciones' });
    expect(await within(lista).findAllByRole('listitem')).toHaveLength(4);
    expect(within(lista).getByText('Por aprobar')).toBeInTheDocument();
    expect(within(lista).getByText('Devuelta')).toBeInTheDocument();
    // Sin pestañas: los filtros muestran cuántas hay; las categorías vacías no aparecen.
    expect(screen.queryByRole('tab')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Rechazada/ })).not.toBeInTheDocument();

    await usuario.click(screen.getByRole('button', { name: /Requieren acción/ }));
    expect(within(lista).getAllByRole('listitem')).toHaveLength(2);
    await usuario.click(screen.getByRole('button', { name: /Devuelta/ }));
    expect(within(lista).getAllByRole('listitem')).toHaveLength(1);
    expect(within(lista).getByText('Renovación ficticia')).toBeInTheDocument();
  });

  it('marca un aviso como leído sin quitarlo y marca todos con un botón', async () => {
    const usuario = userEvent.setup();
    abrir();
    const boton = await screen.findByRole('button', { name: 'Marcar como leído' });
    // Después de marcar, el backend ya lo devuelve leído.
    vi.mocked(pendientesApi.listar).mockResolvedValue({ por_decidir: POR_DECIDIR, avisos: AVISOS.map((aviso) => ({ ...aviso, leido: true })), total: 2 });
    await usuario.click(boton);
    expect(pendientesApi.marcarLeido).toHaveBeenCalledWith('a-2');
    expect(screen.getByText('Renovación ficticia')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Marcar todo como leído' })).not.toBeInTheDocument();
  });

  it('«Revisar y decidir» abre la historia en el asistente', async () => {
    const usuario = userEvent.setup();
    abrir();
    await usuario.click(await screen.findByRole('button', { name: 'Revisar y decidir' }));
    expect(await screen.findByText('Asistente abierto')).toBeInTheDocument();
  });

  it('«Falló un agente» explica qué pasó y permite retomar la historia', async () => {
    const usuario = userEvent.setup();
    vi.mocked(pendientesApi.listar).mockResolvedValue({ por_decidir: [], total: 1, avisos: [{
      id: 'a-9', tipo: 'fallo', titulo: 'Consulta de saldos ficticia', workflow_id: 'f-9', leido: false,
      detalle: 'Asesor Técnico no pudo terminar: el proveedor del modelo no respondió. Se intentó 4 veces de forma automática.',
      creado_en: '2030-01-06T10:00:00Z',
    }] });
    abrir();
    const fila = (await screen.findByText('Consulta de saldos ficticia')).closest('li');
    expect(within(fila).getByText('Falló un agente')).toBeInTheDocument();
    expect(within(fila).getByText(/Asesor Técnico no pudo terminar/)).toBeInTheDocument();
    expect(within(fila).queryByText(/Motivo:/)).not.toBeInTheDocument();
    await usuario.click(within(fila).getByRole('button', { name: 'Retomar' }));
    expect(await screen.findByText('Asistente abierto')).toBeInTheDocument();
  });

  it('«Marcar todo como leído» llama al backend una sola vez', async () => {
    const usuario = userEvent.setup();
    abrir();
    await usuario.click(await screen.findByRole('button', { name: 'Marcar todo como leído' }));
    expect(pendientesApi.marcarTodoLeido).toHaveBeenCalledTimes(1);
  });
});
