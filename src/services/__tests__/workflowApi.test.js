import { afterEach, describe, expect, it, vi } from 'vitest';
import { getWorkflow, resumeWorkflow, retryWorkflow, startWorkflow, WorkflowApiError } from '../workflowApi.js';

afterEach(() => vi.unstubAllGlobals());

describe('workflowApi', () => {
  it('starts pre_grooming through the same-origin API without writing browser storage', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ workflow_id: 'wf-1' }), { status: 201 }));
    vi.stubGlobal('fetch', fetchMock);
    const before = Object.keys(localStorage);
    const body = { mode: 'pre_grooming', requirement: 'Requisito de prueba' };

    await expect(startWorkflow(body)).resolves.toEqual({ workflow_id: 'wf-1' });
    expect(fetchMock).toHaveBeenCalledWith('/api/workflows', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify(body),
      credentials: 'same-origin',
      cache: 'no-store',
    }));
    expect(Object.keys(localStorage)).toEqual(before);
  });

  it('gets a workflow and resumes with its interrupt_id in the request body', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ workflow_id: 'wf/1' }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'interrupted' }), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    const controller = new AbortController();
    const body = { kind: 'business_answers', interrupt_id: 'interrupt-1', response: { answers: [] } };

    await getWorkflow('wf/1', { signal: controller.signal });
    await resumeWorkflow('wf/1', body, { signal: controller.signal });

    expect(fetchMock.mock.calls[0][0]).toBe('/api/workflows/wf%2F1');
    expect(fetchMock.mock.calls[0][1].signal).toBe(controller.signal);
    expect(fetchMock.mock.calls[1][0]).toBe('/api/workflows/wf%2F1/resume');
    expect(fetchMock.mock.calls[1][1]).toMatchObject({ method: 'POST', body: JSON.stringify(body) });
  });

  it.each([400, 404, 409, 422, 503, 504])('reports a safe, actionable message for HTTP %s', async (status) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      error: { code: 'PUBLIC_ERROR', message: 'internal-looking raw error', retryable: status >= 500 },
    }), { status })));

    await expect(getWorkflow('wf-1')).rejects.toMatchObject({
      name: 'WorkflowApiError', status, retryable: status >= 500,
    });
    await expect(getWorkflow('wf-1')).rejects.not.toHaveProperty('message', 'internal-looking raw error');
    expect(WorkflowApiError).toBeDefined();
  });

  it('explains that a missing workflow must be restarted', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      error: { code: 'WORKFLOW_NOT_FOUND', message: 'Not found', retryable: false },
    }), { status: 404 })));

    await expect(getWorkflow('lost-workflow')).rejects.toThrow(/no se encontró el flujo.*inicie uno nuevo/i);
  });

  it('does not turn an intentional cancellation into a network failure', async () => {
    const abort = new DOMException('Aborted', 'AbortError');
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(abort));
    await expect(getWorkflow('wf-1')).rejects.toBe(abort);
  });
});

describe('agentes en segundo plano', () => {
  const sse = (eventos) => {
    const texto = eventos.map((evento) => `event: ${evento.tipo}\ndata: ${JSON.stringify(evento)}\n\n`).join('');
    // Se parte el texto en pedazos para comprobar que se arma bien aunque un evento llegue cortado.
    const pedazos = [texto.slice(0, 25), texto.slice(25, 90), texto.slice(90)];
    return new Response(new ReadableStream({
      start(controlador) {
        pedazos.forEach((pedazo) => controlador.enqueue(new TextEncoder().encode(pedazo)));
        controlador.close();
      },
    }), { status: 200, headers: { 'Content-Type': 'text/event-stream' } });
  };
  const json = (cuerpo, status = 200) => new Response(JSON.stringify(cuerpo), { status });
  const EN_CURSO = { workflow_id: 'wf-9', en_curso: true };
  const RESULTADO = { workflow_id: 'wf-9', status: 'interrupted', interrupt: { kind: 'business_answers' } };

  it('pide el modo en segundo plano, muestra el avance en vivo y devuelve el resultado final', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(json(EN_CURSO, 202))
      .mockResolvedValueOnce(sse([
        { tipo: 'inicio' },
        { tipo: 'agente_inicio', agente: 'analista' },
        { tipo: 'agente_consulta', agente: 'analista', herramientas: ['consultar_glosario'] },
        { tipo: 'fin', estado: 'listo', espera: 'business_answers' },
      ]))
      .mockResolvedValueOnce(json(RESULTADO));
    vi.stubGlobal('fetch', fetchMock);
    const eventos = [];

    await expect(startWorkflow({ mode: 'pre_grooming', requirement: 'R' }, { alAvance: (e) => eventos.push(e.tipo) }))
      .resolves.toEqual(RESULTADO);
    expect(fetchMock.mock.calls[0][1].headers.Prefer).toBe('respond-async');
    expect(fetchMock.mock.calls[1][0]).toBe('/api/workflows/wf-9/avance');
    expect(fetchMock.mock.calls[1][1].headers.Accept).toBe('text/event-stream');
    expect(eventos).toEqual(['aceptado', 'inicio', 'agente_inicio', 'agente_consulta', 'fin']);
  });

  it('si se corta el avance en vivo, consulta hasta que termina sin repetir eventos', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    try {
      const fetchMock = vi.fn()
        .mockResolvedValueOnce(json(EN_CURSO, 202))
        .mockResolvedValueOnce(sse([{ tipo: 'inicio' }]))  // se corta sin «fin»
        .mockResolvedValueOnce(json({ en_curso: true, eventos: [{ tipo: 'inicio' }, { tipo: 'agente_inicio', agente: 'analista' }] }))
        .mockResolvedValueOnce(json({ en_curso: false, eventos: [{ tipo: 'inicio' }, { tipo: 'agente_inicio', agente: 'analista' }, { tipo: 'fin', estado: 'listo' }], resultado: { estado: 'listo' } }))
        .mockResolvedValueOnce(json(RESULTADO));
      vi.stubGlobal('fetch', fetchMock);
      const eventos = [];
      const promesa = retryWorkflow('wf-9', { alAvance: (e) => eventos.push(e.tipo) });
      await vi.runAllTimersAsync();
      await expect(promesa).resolves.toEqual(RESULTADO);
      expect(eventos).toEqual(['aceptado', 'inicio', 'agente_inicio', 'fin']);
    } finally {
      vi.useRealTimers();
    }
  });

  it('el error de los agentes llega como el de siempre, con la hora de la cuota', async () => {
    const vuelve = new Date(Date.now() + 25 * 60000).toISOString();
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(json(EN_CURSO, 202))
      .mockResolvedValueOnce(sse([{ tipo: 'fin', estado: 'error', error: { code: 'OPENCODE_RATE_LIMITED', status: 503, message: 'x', retryable: true, retry_at: vuelve } }])));
    const error = await resumeWorkflow('wf-9', { kind: 'business_answers' }).catch((fallo) => fallo);
    expect(error).toBeInstanceOf(WorkflowApiError);
    expect(error.code).toBe('OPENCODE_RATE_LIMITED');
    expect(error.message).toMatch(/Se agotó la cuota del modelo\. Vuelve a las .+ \(en 25 minutos\)/);
  });

  it('un backend sin el modo responde como siempre y no se espera nada', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(json(RESULTADO, 201));
    vi.stubGlobal('fetch', fetchMock);
    await expect(startWorkflow({ mode: 'pre_grooming', requirement: 'R' })).resolves.toEqual(RESULTADO);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
