import { useCallback, useEffect, useRef, useState } from 'react';
import { metricasApi } from '../services/metricasApi';

/** Lee un panel de métricas del periodo elegido; cancela el pedido anterior si se cambia el periodo. */
export const usePanelMetrica = (leer, periodoInicial, mensajeError) => {
  const [periodo, setPeriodo] = useState(periodoInicial);
  const [panel, setPanel] = useState(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState('');
  const pedido = useRef(null);

  const cargar = useCallback(async (elegido) => {
    pedido.current?.abort();
    const controlador = new AbortController();
    pedido.current = controlador;
    setCargando(true);
    setError('');
    try {
      const respuesta = await leer(elegido, { signal: controlador.signal });
      if (!controlador.signal.aborted) setPanel(respuesta);
    } catch (fallo) {
      if (controlador.signal.aborted) return;
      console.warn(`${mensajeError}:`, fallo?.message ?? fallo);
      setError(fallo?.message || `${mensajeError}.`);
    } finally {
      if (!controlador.signal.aborted) setCargando(false);
    }
  }, [leer, mensajeError]);

  useEffect(() => {
    cargar(periodo);
    return () => pedido.current?.abort();
  }, [cargar, periodo]);

  return { periodo, setPeriodo, panel, cargando, error, recargar: () => cargar(periodo) };
};

/** Panel «Consumo del modelo»: totales, por agente, por día y por historia del periodo elegido. */
export const useConsumoModelo = (periodoInicial = '30') => usePanelMetrica(
  metricasApi.leerConsumo, periodoInicial, 'No se pudo consultar el consumo del modelo',
);

/** Panel «Observabilidad»: latencia por paso, alertas y estado de cada traza. */
export const useObservabilidad = (periodoInicial = '7') => usePanelMetrica(
  metricasApi.leerObservabilidad, periodoInicial, 'No se pudo consultar la observabilidad',
);
