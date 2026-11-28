import React, { useEffect, useState } from 'react';
import { TarjetaComponent } from '../Comun/TarjetaComponent';
import { metricasApi } from '../../services/metricasApi';
import { formatoCosto, formatoToken } from '../../utils/formatoMetricas';
import { BarrasConsumoComponent } from './GraficoConsumoComponent';
import { TablaFlujoComponent } from './ConsumoModeloComponent';

// Detalle de una HU › Consumo del modelo: lo que costó crearla y cada cambio, por agente.
export const ConsumoHistoriaComponent = ({ historiaId }) => {
  const [dato, setDato] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    const controlador = new AbortController();
    metricasApi.leerConsumoHistoria(historiaId, { signal: controlador.signal })
      .then((respuesta) => setDato(respuesta))
      .catch((fallo) => {
        if (controlador.signal.aborted) return;
        console.warn('No se pudo consultar el consumo de la historia:', fallo?.message ?? fallo);
        setError(fallo?.message || 'No se pudo consultar el consumo de la historia.');
      });
    return () => controlador.abort();
  }, [historiaId]);

  if (error) return <TarjetaComponent title="Consumo del modelo"><p className="metricas__vacio">{error}</p></TarjetaComponent>;
  if (!dato) return <TarjetaComponent title="Consumo del modelo"><p className="metricas__vacio">Consultando…</p></TarjetaComponent>;

  const { total } = dato;
  if (!total?.llamadas) {
    return (
      <TarjetaComponent title="Consumo del modelo">
        <p className="metricas__vacio">
          No hay consumo registrado para esta historia. Se mide desde que se instaló esta métrica, en las historias creadas o cambiadas con los agentes.
        </p>
      </TarjetaComponent>
    );
  }
  return (
    <TarjetaComponent title="Consumo del modelo" subtitle="Lo que costó crear esta historia y cada cambio, sumando a todos los agentes">
      <p className="metricas__resumen-historia">
        <strong>{formatoCosto(total.costo_usd)}</strong> · {formatoToken(total.tokens_total)} tokens · {total.llamadas} llamadas al modelo
      </p>
      <h4 className="metricas__subtitulo">Por agente</h4>
      <BarrasConsumoComponent lista={dato.por_agente.map((item) => ({ ...item, clave: item.agente }))} etiqueta="Consumo de la historia por agente" />
      {dato.por_flujo.length > 1 && (
        <>
          <h4 className="metricas__subtitulo metricas__subtitulo--aparte">Creación y cambios</h4>
          <TablaFlujoComponent lista={dato.por_flujo} etiqueta="Consumo de la historia por creación y cambios" />
        </>
      )}
    </TarjetaComponent>
  );
};
