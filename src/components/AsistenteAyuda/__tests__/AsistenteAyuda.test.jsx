import React from 'react';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { AsistenteAyudaComponent } from '../AsistenteAyudaComponent';
import { AyudaComponent } from '../../Ayuda/AyudaComponent';
import { buscarPregunta } from '../../../data/ayudaChat';

const abrir = async (user) => {
  render(<AsistenteAyudaComponent />);
  await user.click(screen.getByRole('button', { name: 'Abrir chat de ayuda' }));
  return screen.getByRole('dialog', { name: 'Chat de ayuda' });
};

describe('chat de ayuda sin modelo', () => {
  it('abre con preguntas sugeridas y responde con texto fijo y pasos', async () => {
    const user = userEvent.setup();
    const panel = await abrir(user);
    await user.click(within(panel).getByRole('button', { name: '¿Cómo creo una historia?' }));
    const registro = within(panel).getByRole('log');
    expect(within(registro).getAllByRole('listitem').length).toBeGreaterThanOrEqual(5);
    expect(registro).toHaveTextContent(/Nueva historia/);
  });

  it('explica que el código no es el identificador técnico', async () => {
    const user = userEvent.setup();
    const panel = await abrir(user);
    await user.click(within(panel).getByRole('button', { name: '¿Qué es el código de la HU?' }));
    expect(within(panel).getByRole('log')).toHaveTextContent(/HU-CODIGO-001/);
    expect(within(panel).getByRole('log')).toHaveTextContent(/GUID/);
  });

  it('busca por palabra clave y avisa cuando no entiende', async () => {
    const user = userEvent.setup();
    const panel = await abrir(user);
    await user.type(within(panel).getByLabelText('Escriba una palabra clave'), 'criterios');
    await user.click(within(panel).getByRole('button', { name: 'Enviar' }));
    expect(within(panel).getByRole('log')).toHaveTextContent(/Dado que/);
    await user.type(within(panel).getByLabelText('Escriba una palabra clave'), 'zzzz qqqq');
    await user.click(within(panel).getByRole('button', { name: 'Enviar' }));
    expect(within(panel).getByRole('log')).toHaveTextContent(/No tengo una respuesta fija/);
    expect(buscarPregunta('')).toBeNull();
  });

  it('se cierra desde el botón de cierre', async () => {
    const user = userEvent.setup();
    const panel = await abrir(user);
    await user.click(within(panel).getByRole('button', { name: 'Cerrar chat de ayuda' }));
    expect(screen.queryByRole('dialog', { name: 'Chat de ayuda' })).not.toBeInTheDocument();
  });
});

describe('página de Ayuda', () => {
  it('explica el asistente, las acciones, la arquitectura (con agentes y tecnologías), lo pendiente y el equipo', async () => {
    const user = userEvent.setup();
    render(<MemoryRouter><AyudaComponent /></MemoryRouter>);
    expect(screen.getByText('¿Cómo funciona el Asistente IA?')).toBeInTheDocument();
    expect(screen.getByText(/Paso 3 — Preguntas para Negocio/)).toBeInTheDocument();
    expect(screen.getByText(/Paso 5 — Aprobación del Product Owner/)).toBeInTheDocument();

    await user.click(screen.getByRole('tab', { name: /Acciones sobre una HU/ }));
    ['Retomar o descartar (HU en proceso)', 'Ver detalle', 'Editar', 'Solicitar cambio (solo HU aprobada)', 'Descargar', 'Eliminar'].forEach((titulo) => {
      expect(screen.getByRole('heading', { name: titulo })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('tab', { name: /Ejemplo de HU generada/ }));
    expect(screen.getByRole('img', { name: /historia de usuario generada/i })).toBeInTheDocument();

    // Arquitectura reúne cómo funciona, los agentes, las tecnologías, la construcción y el diseño.
    await user.click(screen.getByRole('tab', { name: /Arquitectura/ }));
    const panel = screen.getByRole('tabpanel');
    const indice = within(panel).getByRole('navigation', { name: 'Contenido de Arquitectura' });
    expect(within(indice).getAllByRole('link').map((enlace) => enlace.textContent))
      .toEqual(['Cómo funciona', 'Los agentes', 'Tecnologías', 'Cómo está construido', 'Diseño']);

    const menu = within(panel).getByText('Qué hace cada opción del menú').closest('.card');
    ['Inicio', 'Notificaciones', 'Historias de usuario', 'Mantenimiento', 'Ayuda'].forEach((opcion) => {
      expect(within(menu).getByRole('heading', { name: opcion })).toBeInTheDocument();
    });
    expect(within(menu).getByText(/Cambio por decidir/)).toBeInTheDocument();
    expect(within(menu).getByText(/Pruebas automatizadas/)).toBeInTheDocument();

    const consulta = within(panel).getByText('Cómo viaja una consulta entre los agentes').closest('.card');
    ['Agente y su MCP', 'Pinecone', 'OpenCode'].forEach((quien) => {
      expect(within(consulta).getByText(quien)).toBeInTheDocument();
    });
    expect(within(consulta).getAllByText('LangGraph')).toHaveLength(2);
    expect(within(consulta).getByText(/índice historias-usuario/)).toBeInTheDocument();

    const pruebas = within(panel).getByText('Cómo funcionan las pruebas automatizadas').closest('.card');
    ['Conexión con GitHub', 'GitHub Actions', 'Playwright', 'Playwright MCP y Agente de Pruebas'].forEach((quien) => {
      expect(within(pruebas).getByText(quien)).toBeInTheDocument();
    });
    expect(within(pruebas).getByText(/Todo se ejecuta en GitHub/)).toBeInTheDocument();

    ['Agente Analista', 'Asesor Técnico', 'Redactor-Revisor', 'Gestor de Cambios', 'Agente de Pruebas', 'Autonomía', 'Memoria (RAG)', 'Qué no hacen'].forEach((titulo) => {
      expect(within(panel).getByRole('heading', { name: titulo })).toBeInTheDocument();
    });
    expect(within(panel).getByText(/Python 3.12, FastAPI con Uvicorn/)).toBeInTheDocument();
    ['Orquestación de agentes', 'Conocimiento (RAG)', 'Repositorio de código', 'Trazabilidad'].forEach((titulo) => {
      expect(within(panel).getByRole('heading', { name: titulo })).toBeInTheDocument();
    });
    ['Capas del sistema', 'Cómo se hace un cambio', 'Pensado para producción', 'Preparado para programar con IA', 'Paleta de colores'].forEach((titulo) => {
      expect(within(panel).getByText(titulo)).toBeInTheDocument();
    });
    expect(within(panel).getByRole('heading', { name: 'Agregar un agente' })).toBeInTheDocument();

    // Agentes y Tecnologías ya no son pestañas aparte.
    expect(screen.queryByRole('tab', { name: /Los agentes/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: /Tecnologías/ })).not.toBeInTheDocument();
    expect(screen.getAllByRole('tab')).toHaveLength(7);

    await user.click(screen.getByRole('tab', { name: /Por definir/ }));
    expect(screen.getByRole('heading', { name: 'Bitácora de seguridad' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Avisos fuera de la aplicación' })).toBeInTheDocument();
    expect(screen.queryByText(/Falta construir el Agente Redactor-Revisor/)).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Usuarios e inicio de sesión' })).not.toBeInTheDocument();

    await user.click(screen.getByRole('tab', { name: /Equipo/ }));
    const nombres = screen.getAllByRole('listitem').map((item) => item.textContent);
    expect(nombres).toEqual(['Allam Fernandez', 'Gilberth Monge', 'Yuvania Castillo']);
  });

  it('no mantiene secciones antiguas de la Ayuda', () => {
    render(<MemoryRouter><AyudaComponent /></MemoryRouter>);
    expect(screen.queryByText(/Edición mediante Accordion/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Preguntas Frecuentes/)).not.toBeInTheDocument();
  });
});
