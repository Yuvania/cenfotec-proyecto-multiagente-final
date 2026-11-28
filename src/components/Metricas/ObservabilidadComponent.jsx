import React, { useState } from 'react';
import { AlertCircle, AlertTriangle, CheckCircle } from 'lucide-react';
import { TituloPaginaComponent } from '../Comun/TituloPaginaComponent';
import { AlertaComponent } from '../Comun/AlertaComponent';
import { useObservabilidad } from '../../hooks/useConsumoModelo';
import { duracion, fechaCorta } from '../../utils/formatoPruebas';
import { NOMBRE_MODO, formatoCosto, formatoLatencia } from '../../utils/formatoMetricas';

// Mantenimiento › Observabilidad: ¿está funcionando bien ahora? Latencia por paso, alertas con los umbrales
// aprobados y el estado de cada traza (cada creación o cambio de una historia). Es aparte del consumo, que
// responde «¿cuánto gastamos?». Ver docs/metricas.md.
const PERIODO_INICIAL = [
  { codigo: '7', nombre: 'Últimos 7 días' },
  { codigo: '30', nombre: 'Últimos 30 días' },
  { codigo: 'todo', nombre: 'Todo' },
];

export const ESTADO_TRAZA = Object.freeze({
  ok: { texto: 'Terminó', clase: 'ok', Icono: CheckCircle },
  con_reintento: { texto: 'Terminó con reintentos', clase: 'advertencia', Icono: AlertTriangle },
  fallo: { texto: 'Falló', clase: 'critica', Icono: AlertCircle },
  detenida: { texto: 'Detenida por el tope de gasto', clase: 'critica', Icono: AlertCircle },
});

const porcentajeTexto = (valor) => `${String(Math.round(valor * 10) / 10).replace('.', ',')} %`;

const EstadoTraza = ({ estado }) => {
  const dato = ESTADO_TRAZA[estado] ?? ESTADO_TRAZA.fallo;
  const { Icono } = dato;
  // El estado nunca va solo por color: lleva ícono y texto.
  return (
    <span className={`observabilidad__estado observabilidad__estado--${dato.clase}`}>
      <Icono size={14} aria-hidden="true" />{dato.texto}
    </span>
  );
};

const Presupuesto = ({ presupuesto }) => {
  if (!presupuesto) return null;
  const { mensual_usd: tope, gastado_mes_usd: gastado, porcentaje_mes: porcentaje, historia_usd: porHistoria } = presupuesto;
  const nivel = porcentaje >= 100 ? 'critica' : porcentaje >= 80 ? 'advertencia' : 'ok';
  return (
    <section className="metricas__tarjeta" aria-labelledby="observabilidad-presupuesto">
      <h2 id="observabilidad-presupuesto" className="metricas__subtitulo">Tope de gasto</h2>
      {tope ? (
        <>
          <p className="metricas__texto">
            Este mes: <strong>{formatoCosto(gastado)}</strong> de {formatoCosto(tope)} ({porcentajeTexto(porcentaje ?? 0)}).
          </p>
          <div className="observabilidad__medidor" role="meter" aria-label="Gasto del mes" aria-valuemin={0} aria-valuemax={100}
            aria-valuenow={Math.min(100, Math.round(porcentaje ?? 0))}>
            <div className={`observabilidad__medidor-relleno observabilidad__medidor-relleno--${nivel}`}
              style={{ width: `${Math.min(100, porcentaje ?? 0)}%` }} />
          </div>
        </>
      ) : <p className="metricas__texto">Sin tope mensual configurado.</p>}
      <p className="metricas__nota">
        {porHistoria ? `Cada historia puede gastar hasta ${formatoCosto(porHistoria)}. ` : 'Sin tope por historia. '}
        Al llegar a un tope, los agentes se detienen, el avance queda guardado y la persona puede terminar la historia en modo manual.
      </p>
    </section>
  );
};

const Alertas = ({ lista, cargando }) => {
  if (cargando && !lista) return <p className="metricas__vacio">Consultando…</p>;
  if (!lista?.length) {
    return (
      <AlertaComponent type="success" title="Sin alertas">
        Ningún umbral se superó en este periodo.
      </AlertaComponent>
    );
  }
  return (
    <ul className="observabilidad__alertas" aria-label="Alertas">
      {lista.map((alerta) => (
        <li key={alerta.id}>
          <AlertaComponent type={alerta.nivel === 'critica' ? 'danger' : 'warning'}
            title={`${alerta.nivel === 'critica' ? 'Crítica' : 'Advertencia'}: ${alerta.titulo}`}>
            {alerta.detalle}
            {alerta.lista?.length > 0 && (
              <span className="observabilidad__alerta-lista">{alerta.lista.map((item) => item.titulo).join(' · ')}</span>
            )}
          </AlertaComponent>
        </li>
      ))}
    </ul>
  );
};

const TablaLatencia = ({ lista, etiqueta, columna, clave, extra }) => (
  <div className="metricas__tabla-contenedor">
    <table className="metricas__tabla" aria-label={etiqueta}>
      <thead>
        <tr>
          <th scope="col">{columna}</th><th scope="col" className="metricas__numero">Veces</th>
          <th scope="col" className="metricas__numero">Mediana</th><th scope="col" className="metricas__numero">95 %</th>
          <th scope="col" className="metricas__numero">Máxima</th><th scope="col" className="metricas__numero">{extra.titulo}</th>
        </tr>
      </thead>
      <tbody>
        {lista.map((item) => (
          <tr key={item[clave]}>
            <th scope="row" data-etiqueta={columna} className="metricas__fila-nombre">{item.nombre}</th>
            <td data-etiqueta="Veces" className="metricas__numero">{item.cantidad}</td>
            <td data-etiqueta="Mediana" className="metricas__numero">{formatoLatencia(item.p50_ms)}</td>
            <td data-etiqueta="95 %" className="metricas__numero">{formatoLatencia(item.p95_ms)}</td>
            <td data-etiqueta="Máxima" className="metricas__numero">{formatoLatencia(item.maxima_ms)}</td>
            <td data-etiqueta={extra.titulo} className={`metricas__numero ${item[extra.campo] > 0 ? 'metricas__alerta' : ''}`}>
              {item[extra.campo]}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

const Traza = ({ traza }) => {
  const [abierta, setAbierta] = useState(false);
  const idPasos = `traza-${traza.workflow_id}`;
  return (
    <li className="observabilidad__traza">
      <div className="observabilidad__traza-cabecera">
        <div>
          <p className="observabilidad__traza-titulo">{traza.titulo}</p>
          <p className="metricas__nota">
            {NOMBRE_MODO[traza.modo] ?? traza.modo} · {fechaCorta(traza.fin)} · {duracion(traza.duracion_ms)} ·{' '}
            {formatoCosto(traza.costo_usd)} · {traza.consultas_mcp} {traza.consultas_mcp === 1 ? 'consulta' : 'consultas'} a las fuentes
            {traza.lento ? ' · con un paso de más de 3 minutos' : ''}
          </p>
        </div>
        <EstadoTraza estado={traza.estado} />
      </div>
      <button type="button" className="observabilidad__traza-boton" aria-expanded={abierta} aria-controls={idPasos}
        onClick={() => setAbierta((valor) => !valor)}>
        {abierta ? 'Ocultar pasos' : `Ver ${traza.paso.length} ${traza.paso.length === 1 ? 'paso' : 'pasos'}`}
      </button>
      {abierta && (
        <ol id={idPasos} className="observabilidad__pasos" aria-label={`Pasos de ${traza.titulo}`}>
          {traza.paso.map((paso, indice) => (
            <li key={`${paso.agente}-${indice}`}>
              <span>{paso.nombre}</span>
              <span className="metricas__numero">{formatoLatencia(paso.duracion_ms)}</span>
              <span>
                {paso.exitoso ? (paso.intentos > 1 ? `Respondió al intento ${paso.intentos}` : 'Respondió')
                  : `No respondió${paso.codigo_error === 'PRESUPUESTO_AGOTADO' ? ' (tope de gasto)' : ''}`}
              </span>
            </li>
          ))}
        </ol>
      )}
      <p className="metricas__nota">Traza en Langfuse: busque la sesión o el flujo <code>{traza.workflow_id}</code>.</p>
    </li>
  );
};

export const ObservabilidadComponent = () => {
  const { periodo, setPeriodo, panel, cargando, error } = useObservabilidad('7');
  const listaPeriodo = panel?.lista_periodo ?? PERIODO_INICIAL;

  return (
    <div className="metricas observabilidad">
      <TituloPaginaComponent
        title="Observabilidad"
        description="Si los agentes están funcionando bien: alertas, cuánto tarda cada paso y cómo terminó cada historia."
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

      <section className="metricas__tarjeta" aria-labelledby="observabilidad-alertas" aria-busy={cargando}>
        <h2 id="observabilidad-alertas" className="metricas__subtitulo">Alertas</h2>
        <Alertas lista={panel?.alerta} cargando={cargando} />
        <p className="metricas__nota">
          Umbrales: una historia que cuesta más del doble del promedio de 30 días, un paso de más de 3 minutos, un agente
          con más de 10 % de fallos en 24 horas (mínimo 5 turnos), un error de cuota en la última hora y llamadas con costo
          estimado o sin precio.
        </p>
      </section>

      <Presupuesto presupuesto={panel?.presupuesto} />

      <section className="metricas__tarjeta" aria-labelledby="observabilidad-agente">
        <h2 id="observabilidad-agente" className="metricas__subtitulo">Latencia por paso</h2>
        <p className="metricas__nota">Cuánto tarda el turno de cada agente. «95 %»: el 95 % de los turnos tardó eso o menos.</p>
        {(panel?.latencia_agente?.length ?? 0) > 0
          ? <TablaLatencia lista={panel.latencia_agente} etiqueta="Latencia por agente" columna="Agente" clave="agente"
            extra={{ titulo: 'Más de 3 min', campo: 'lentos' }} />
          : <p className="metricas__vacio">{cargando ? 'Consultando…' : 'Sin datos.'}</p>}
        <h3 className="metricas__subtitulo metricas__subtitulo--aparte">Fuentes de conocimiento (MCP)</h3>
        {(panel?.latencia_herramienta?.length ?? 0) > 0
          ? <TablaLatencia lista={panel.latencia_herramienta} etiqueta="Latencia por fuente" columna="Fuente" clave="herramienta"
            extra={{ titulo: 'Sin respuesta', campo: 'fallidas' }} />
          : <p className="metricas__vacio">{cargando ? 'Consultando…' : 'Sin datos.'}</p>}
      </section>

      <section className="metricas__tarjeta" aria-labelledby="observabilidad-traza">
        <h2 id="observabilidad-traza" className="metricas__subtitulo">Trazas</h2>
        <p className="metricas__nota">Cada creación o cambio de una historia (hasta 30), con el estado de su último paso.</p>
        {(panel?.traza?.length ?? 0) > 0
          ? <ul className="observabilidad__trazas" aria-label="Trazas">{panel.traza.map((traza) => <Traza key={traza.workflow_id} traza={traza} />)}</ul>
          : <p className="metricas__vacio">{cargando ? 'Consultando…' : 'Sin trazas en este periodo.'}</p>}
      </section>

      <p className="metricas__nota">
        Se guardan solo tiempos, estados y cantidades, nunca lo que se le preguntó al modelo ni lo que respondió.
      </p>
    </div>
  );
};
