import React from 'react';
import { Link } from 'react-router-dom';
import { TituloPaginaComponent } from '../Comun/TituloPaginaComponent';
import { AlertaComponent } from '../Comun/AlertaComponent';
import { useConsumoModelo } from '../../hooks/useConsumoModelo';
import { getStoryById } from '../../utils/storage';
import { duracion, fechaCorta } from '../../utils/formatoPruebas';
import { NOMBRE_MODO, formatoCosto, formatoToken, formatoTokenCorto } from '../../utils/formatoMetricas';
import { BarrasConsumoComponent, ColumnasDiaComponent } from './GraficoConsumoComponent';

// Mantenimiento › Consumo del modelo: cuánto cuesta cada historia, cada agente y cada día.
// Los datos los registra el backend con cada respuesta de OpenCode (ver docs/metricas.md).
const PERIODO_INICIAL = [
  { codigo: '7', nombre: 'Últimos 7 días' },
  { codigo: '30', nombre: 'Últimos 30 días' },
  { codigo: 'todo', nombre: 'Todo' },
];

const Indicador = ({ etiqueta, valor, detalle }) => (
  <div className="metricas__indicador">
    <p className="metricas__indicador-etiqueta">{etiqueta}</p>
    <p className="metricas__indicador-valor">{valor}</p>
    {detalle && <p className="metricas__indicador-detalle">{detalle}</p>}
  </div>
);

const promedioTexto = (promedio, nombre) => (promedio
  ? `${promedio.flujos} ${nombre} · ${formatoTokenCorto(promedio.tokens_total)} tokens · ${promedio.llamadas} llamadas`
  : 'Todavía no hay datos');

const TituloHistoria = ({ flujo }) => {
  const titulo = flujo.titulo || 'Sin título';
  // Solo se enlaza si la HU existe (una creación que no se aprobó ni se guardó no tiene detalle).
  return flujo.historia_id && getStoryById(flujo.historia_id)
    ? <Link to={`/historias/${encodeURIComponent(flujo.historia_id)}`}>{titulo}</Link>
    : <span>{titulo}</span>;
};

export const TablaFlujoComponent = ({ lista, etiqueta }) => (
  <div className="metricas__tabla-contenedor">
    <table className="metricas__tabla" aria-label={etiqueta}>
      <thead>
        <tr>
          <th scope="col">Historia</th><th scope="col">Tipo</th><th scope="col">Último uso</th>
          <th scope="col" className="metricas__numero">Agentes</th><th scope="col" className="metricas__numero">Llamadas</th>
          <th scope="col" className="metricas__numero">Tokens</th><th scope="col" className="metricas__numero">Costo</th>
        </tr>
      </thead>
      <tbody>
        {lista.map((flujo) => (
          <tr key={flujo.workflow_id}>
            <td data-etiqueta="Historia"><TituloHistoria flujo={flujo} /></td>
            <td data-etiqueta="Tipo">{NOMBRE_MODO[flujo.modo] ?? flujo.modo}</td>
            <td data-etiqueta="Último uso">{fechaCorta(flujo.fin)}</td>
            <td data-etiqueta="Agentes" className="metricas__numero">{flujo.agentes}</td>
            <td data-etiqueta="Llamadas" className="metricas__numero">{flujo.llamadas}</td>
            <td data-etiqueta="Tokens" className="metricas__numero">{formatoToken(flujo.tokens_total)}</td>
            <td data-etiqueta="Costo" className="metricas__numero">{formatoCosto(flujo.costo_usd)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

// Fiabilidad: cuántos turnos de cada agente terminaron, cuántos necesitaron reintentos y cuánto tardan.
export const TablaFiabilidadComponent = ({ lista }) => (
  <div className="metricas__tabla-contenedor">
    <table className="metricas__tabla" aria-label="Fiabilidad por agente">
      <thead>
        <tr>
          <th scope="col">Agente</th><th scope="col" className="metricas__numero">Turnos</th>
          <th scope="col" className="metricas__numero">Con reintento</th><th scope="col" className="metricas__numero">Fallidos</th>
          <th scope="col" className="metricas__numero">Tasa de fallo</th><th scope="col" className="metricas__numero">Duración promedio</th>
          <th scope="col" className="metricas__numero">Máxima</th>
        </tr>
      </thead>
      <tbody>
        {lista.map((item) => (
          <tr key={item.agente}>
            <th scope="row" data-etiqueta="Agente" className="metricas__fila-nombre">{item.nombre}</th>
            <td data-etiqueta="Turnos" className="metricas__numero">{item.turnos}</td>
            <td data-etiqueta="Con reintento" className="metricas__numero">{item.con_reintento}</td>
            <td data-etiqueta="Fallidos" className="metricas__numero">{item.fallidos}</td>
            <td data-etiqueta="Tasa de fallo" className={`metricas__numero ${item.tasa_fallo > 0 ? 'metricas__alerta' : ''}`}>
              {`${String(item.tasa_fallo).replace('.', ',')} %`}
            </td>
            <td data-etiqueta="Duración promedio" className="metricas__numero">{duracion(item.duracion_promedio_ms)}</td>
            <td data-etiqueta="Máxima" className="metricas__numero">{duracion(item.duracion_maxima_ms)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

export const ConsumoModeloComponent = () => {
  const { periodo, setPeriodo, panel, cargando, error } = useConsumoModelo('30');
  const listaPeriodo = panel?.lista_periodo ?? PERIODO_INICIAL;
  const total = panel?.total;
  const listaAgente = (panel?.por_agente ?? []).map((item) => ({ ...item, clave: item.agente }));
  const prueba = panel?.prueba;
  const sinDatos = !cargando && total && total.llamadas === 0 && !prueba?.llamadas;

  return (
    <div className="metricas">
      <TituloPaginaComponent
        title="Consumo del modelo"
        description="Tokens y costo de cada historia, de cada agente y de cada día. Muestra cuánto cuesta crear o cambiar una historia."
      />

      <div className="metricas__filtros" role="group" aria-label="Periodo">
        {listaPeriodo.map((item) => (
          <button key={item.codigo} type="button" className="metricas__filtro" aria-pressed={periodo === item.codigo}
            onClick={() => setPeriodo(item.codigo)}>
            {item.nombre}
          </button>
        ))}
      </div>

      {error && <AlertaComponent type="warning" title="Atención">{error}</AlertaComponent>}
      {panel?.aviso_costo && <AlertaComponent type="info" title="Sobre el costo">{panel.aviso_costo}</AlertaComponent>}

      <div className="metricas__indicadores" aria-label="Indicadores" aria-busy={cargando}>
        <Indicador etiqueta="Costo total" valor={total ? formatoCosto(total.costo_usd) : '—'}
          detalle={prueba?.costo_usd ? `+ ${formatoCosto(prueba.costo_usd)} del Agente de Pruebas` : 'Historias y cambios'} />
        <Indicador etiqueta="Tokens" valor={total ? formatoTokenCorto(total.tokens_total) : '—'}
          detalle={total ? `${formatoTokenCorto(total.tokens_entrada)} de entrada · ${formatoTokenCorto(total.tokens_salida + total.tokens_razonamiento)} de salida` : null} />
        <Indicador etiqueta="Costo promedio por historia creada" valor={panel?.promedio_creacion ? formatoCosto(panel.promedio_creacion.costo_usd) : '—'}
          detalle={promedioTexto(panel?.promedio_creacion, panel?.promedio_creacion?.flujos === 1 ? 'historia' : 'historias')} />
        <Indicador etiqueta="Costo promedio por cambio" valor={panel?.promedio_cambio ? formatoCosto(panel.promedio_cambio.costo_usd) : '—'}
          detalle={promedioTexto(panel?.promedio_cambio, panel?.promedio_cambio?.flujos === 1 ? 'cambio' : 'cambios')} />
        <Indicador etiqueta="Llamadas al modelo" valor={total ? formatoToken(total.llamadas) : '—'}
          detalle={total?.fallidas ? `${total.fallidas} con error (también se cobran)` : 'Ninguna con error'} />
      </div>

      {sinDatos && (
        <p className="metricas__vacio">
          Todavía no hay consumo registrado en este periodo. Se registra solo desde que se instaló esta medición, cada vez que un agente responde.
        </p>
      )}

      <div className="metricas__columnas-grid">
        <section className="metricas__tarjeta" aria-labelledby="metricas-agente">
          <h2 id="metricas-agente" className="metricas__subtitulo">Costo por agente</h2>
          {listaAgente.length ? <BarrasConsumoComponent lista={listaAgente} etiqueta="Costo por agente" />
            : <p className="metricas__vacio">{cargando ? 'Consultando…' : 'Sin datos.'}</p>}
        </section>
        <section className="metricas__tarjeta" aria-labelledby="metricas-dia">
          <h2 id="metricas-dia" className="metricas__subtitulo">Costo por día</h2>
          {(panel?.por_dia?.length ?? 0) > 0 ? <ColumnasDiaComponent lista={panel.por_dia} />
            : <p className="metricas__vacio">{cargando ? 'Consultando…' : 'Sin datos.'}</p>}
        </section>
      </div>

      <section className="metricas__tarjeta" aria-labelledby="metricas-fiabilidad">
        <h2 id="metricas-fiabilidad" className="metricas__subtitulo">Fiabilidad por agente</h2>
        <p className="metricas__nota">
          Cada turno de un agente en el flujo: si terminó, si necesitó reintentos automáticos (fallos pasajeros, hasta 3) y cuánto tardó.
        </p>
        {(panel?.fiabilidad?.length ?? 0) > 0 ? <TablaFiabilidadComponent lista={panel.fiabilidad} />
          : <p className="metricas__vacio">{cargando ? 'Consultando…' : 'Sin datos.'}</p>}
      </section>

      <section className="metricas__tarjeta" aria-labelledby="metricas-historia">
        <h2 id="metricas-historia" className="metricas__subtitulo">Por historia</h2>
        <p className="metricas__nota">Cada creación o cambio de una historia, del más reciente al más antiguo (hasta 50).</p>
        {(panel?.por_flujo?.length ?? 0) > 0 ? <TablaFlujoComponent lista={panel.por_flujo} etiqueta="Consumo por historia" />
          : <p className="metricas__vacio">{cargando ? 'Consultando…' : 'Sin datos.'}</p>}
      </section>

      <div className="metricas__columnas-grid">
        <section className="metricas__tarjeta" aria-labelledby="metricas-prueba">
          <h2 id="metricas-prueba" className="metricas__subtitulo">Agente de Pruebas</h2>
          {prueba?.ejecuciones ? (
            <p className="metricas__texto">
              Diagnosticó fallos en {prueba.ejecuciones} {prueba.ejecuciones === 1 ? 'ejecución' : 'ejecuciones'}: {prueba.llamadas} llamadas,{' '}
              {formatoToken(prueba.tokens_total)} tokens y {formatoCosto(prueba.costo_usd)}. Corre en GitHub y su consumo llega con el resumen de cada ejecución.
            </p>
          ) : (
            <p className="metricas__vacio">Sin diagnósticos en este periodo. Solo consume cuando una prueba falla.</p>
          )}
        </section>
        <section className="metricas__tarjeta" aria-labelledby="metricas-modelo">
          <h2 id="metricas-modelo" className="metricas__subtitulo">Modelo</h2>
          {(panel?.por_modelo?.length ?? 0) > 0 ? (
            <ul className="metricas__lista">
              {panel.por_modelo.map((item) => (
                <li key={`${item.proveedor}/${item.modelo}`}>
                  <code>{item.proveedor}/{item.modelo}</code>: {formatoToken(item.tokens_total)} tokens · {formatoCosto(item.costo_usd)}
                </li>
              ))}
            </ul>
          ) : <p className="metricas__vacio">Sin datos.</p>}
        </section>
      </div>

      <p className="metricas__nota">
        Se guardan solo cantidades (tokens, costo y duración), nunca lo que se le preguntó al modelo ni lo que respondió.
        Si Langfuse está configurado, cada llamada también aparece ahí con sus tokens y su costo.
      </p>
    </div>
  );
};
