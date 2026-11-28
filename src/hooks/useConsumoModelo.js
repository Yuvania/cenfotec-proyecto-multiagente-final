import { useCallback, useEffect, useRef, useState } from 'react';
import { metricasApi } from '../services/metricasApi';

/** Panel «Consumo del modelo»: totales, por agente, por día y por historia del periodo elegido. */
export const useConsumoModelo = (periodoInicial = '30') => {
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
      const respuesta = await metricasApi.leerConsumo(elegido, { signal: controlador.signal });
      if (!controlador.signal.aborted) setPanel(respuesta);
    } catch (fallo) {
      if (controlador.signal.aborted) return;
      console.warn('No se pudo consultar el consumo del modelo:', fallo?.message ?? fallo);
      setError(fallo?.message || 'No se pudo consultar el consumo del modelo.');
    } finally {
      if (!controlador.signal.aborted) setCargando(false);
    }
  }, []);

  useEffect(() => {
    cargar(periodo);
    return () => pedido.current?.abort();
  }, [cargar, periodo]);

  return { periodo, setPeriodo, panel, cargando, error, recargar: () => cargar(periodo) };
};
