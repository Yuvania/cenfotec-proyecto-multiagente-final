import React from 'react';
import { diaCorto, formatoCosto, formatoToken, porcentaje } from '../../utils/formatoMetricas';

// Gráficos sencillos del consumo, de una sola serie (sin leyenda: el título la nombra). Las barras usan el
// color principal del tema, validado en claro y oscuro; el texto siempre va en los colores de texto.

/**
 * Barras horizontales con nombre, barra y valor. Es también la tabla: cada fila muestra sus números.
 * lista: [{ clave, nombre, costo_usd, tokens_total, llamadas }]
 */
export const BarrasConsumoComponent = ({ lista, etiqueta, medida = 'costo_usd' }) => {
  const maximo = Math.max(...lista.map((item) => Number(item[medida]) || 0), 0);
  const total = lista.reduce((suma, item) => suma + (Number(item[medida]) || 0), 0);
  return (
    <table className="metricas__barras" aria-label={etiqueta}>
      <thead className="sr-only">
        <tr><th scope="col">Nombre</th><th scope="col">Parte</th><th scope="col">Costo</th><th scope="col">Tokens</th><th scope="col">Llamadas</th></tr>
      </thead>
      <tbody>
        {lista.map((item) => {
          const valor = Number(item[medida]) || 0;
          const ancho = maximo > 0 && valor > 0 ? Math.max(2, (100 * valor) / maximo) : 0;
          return (
            <tr key={item.clave} className="metricas__barra-fila"
              title={`${item.nombre}: ${formatoCosto(item.costo_usd)} · ${formatoToken(item.tokens_total)} tokens · ${item.llamadas} llamadas`}>
              <th scope="row" className="metricas__barra-nombre">{item.nombre}</th>
              <td className="metricas__barra-pista">
                <span className="metricas__barra" style={{ width: `${ancho}%` }} aria-hidden="true" />
                <span className="sr-only">{porcentaje(valor, total)} % del total</span>
              </td>
              <td className="metricas__barra-valor">{formatoCosto(item.costo_usd)}</td>
              <td className="metricas__barra-detalle">{formatoToken(item.tokens_total)} tokens</td>
              <td className="metricas__barra-detalle">{item.llamadas} {item.llamadas === 1 ? 'llamada' : 'llamadas'}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
};

/** Columnas por día (costo). Cada columna dice su valor al pasar el cursor o enfocarla; debajo, la tabla para lectores de pantalla. */
export const ColumnasDiaComponent = ({ lista }) => {
  const maximo = Math.max(...lista.map((dia) => dia.costo_usd), 0);
  const cada = Math.max(1, Math.ceil(lista.length / 10));
  return (
    <figure className="metricas__columnas-figura">
      <ol className="metricas__columnas" aria-hidden="true">
        {lista.map((dia, indice) => (
          <li key={dia.dia} className="metricas__columna" title={`${diaCorto(dia.dia)}: ${formatoCosto(dia.costo_usd)} · ${formatoToken(dia.tokens_total)} tokens`}>
            <span className="metricas__columna-barra" style={{ height: `${maximo > 0 && dia.costo_usd > 0 ? Math.max(2, (100 * dia.costo_usd) / maximo) : 0}%` }} />
            <span className="metricas__columna-dia">{indice % cada === 0 ? diaCorto(dia.dia) : ''}</span>
          </li>
        ))}
      </ol>
      <figcaption className="metricas__nota">Máximo en un día: {formatoCosto(maximo)}. Pase el cursor sobre una columna para ver su valor.</figcaption>
      <table className="sr-only">
        <caption>Costo por día</caption>
        <thead><tr><th scope="col">Día</th><th scope="col">Costo</th><th scope="col">Tokens</th></tr></thead>
        <tbody>
          {lista.map((dia) => (
            <tr key={dia.dia}><td>{diaCorto(dia.dia)}</td><td>{formatoCosto(dia.costo_usd)}</td><td>{formatoToken(dia.tokens_total)}</td></tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
};
