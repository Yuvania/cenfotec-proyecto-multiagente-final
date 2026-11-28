import React, { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Bot, CheckCircle2, ExternalLink, MinusCircle, RotateCcw, AlertTriangle, XCircle } from 'lucide-react';
import { TituloPaginaComponent } from '../Comun/TituloPaginaComponent';
import { BotonComponent } from '../Comun/BotonComponent';
import { AlertaComponent } from '../Comun/AlertaComponent';
import { Permitido } from '../Sesion/SesionContext';
import { ACCION } from '../../config/acciones';
import { useEjecucionPrueba } from '../../hooks/usePruebas';
import { pruebasApi } from '../../services/pruebasApi';
import {
  CONFIANZA_DIAGNOSTICO, ESTADO_CASO, TIPO_DIAGNOSTICO, casosAprobados, duracion, estaActiva, numeroEjecucion,
} from '../../utils/formatoPruebas';
import { EstadoEjecucion, LineaTiempo } from './PruebasComponent';

const ICONO_CASO = Object.freeze({ aprobado: CheckCircle2, fallido: XCircle, inestable: AlertTriangle, omitido: MinusCircle });
const LISTA_FILTRO = Object.freeze([
  { id: 'todos', texto: 'Todos', incluye: () => true },
  { id: 'fallidos', texto: 'Fallidos', incluye: (caso) => caso.estado === 'fallido' },
  { id: 'aprobados', texto: 'Aprobados', incluye: (caso) => caso.estado === 'aprobado' || caso.estado === 'inestable' },
]);
const DISPOSITIVO = Object.freeze({ web: 'web', tablet: 'tablet', movil: 'móvil' });

// Lo que explicó el Agente de Pruebas: por qué falló, no solo que falló.
export const DiagnosticoCaso = ({ diagnostico }) => {
  if (!diagnostico) return null;
  if (diagnostico.estado !== 'listo') {
    return <p className="pruebas__meta">{diagnostico.motivo || 'El Agente de Pruebas no pudo diagnosticar este caso.'}</p>;
  }
  const tipo = TIPO_DIAGNOSTICO[diagnostico.tipo] ?? TIPO_DIAGNOSTICO.indeterminado;
  const acciones = diagnostico.exploracion?.acciones?.length ?? 0;
  return (
    <section className="pruebas__diagnostico" aria-label="Diagnóstico del Agente de Pruebas">
      <div className="pruebas__diagnostico-encabezado">
        <Bot size={16} aria-hidden="true" />
        <span className="pruebas__diagnostico-titulo">Diagnóstico del Agente de Pruebas</span>
        <span className={`pruebas__estado pruebas__estado--${tipo.clase}`}>{tipo.texto}</span>
        {diagnostico.confianza && <span className="pruebas__meta">{CONFIANZA_DIAGNOSTICO[diagnostico.confianza]}</span>}
      </div>
      {diagnostico.que_fallo && <p><strong>Qué falló:</strong> {diagnostico.que_fallo}</p>}
      {diagnostico.causa_probable && <p><strong>Causa probable:</strong> {diagnostico.causa_probable}</p>}
      {diagnostico.evidencia?.length > 0 && (
        <ul className="pruebas__evidencia">{diagnostico.evidencia.map((texto) => <li key={texto}>{texto}</li>)}</ul>
      )}
      {diagnostico.sugerencia && <p><strong>Sugerencia:</strong> {diagnostico.sugerencia}</p>}
      <p className="pruebas__meta">
        {acciones > 0 ? `Revisó la aplicación con ${acciones} ${acciones === 1 ? 'acción' : 'acciones'} en el navegador (Playwright MCP).`
          : 'Diagnosticó con la evidencia de la prueba.'} Es una propuesta: decide una persona.
      </p>
    </section>
  );
};

const Caso = ({ caso }) => {
  const estado = ESTADO_CASO[caso.estado] ?? ESTADO_CASO.fallido;
  const Icono = ICONO_CASO[caso.estado] ?? XCircle;
  return (
    <li className="pruebas__caso">
      <span className={`pruebas__icono pruebas__icono--${estado.clase}`} aria-hidden="true"><Icono size={16} /></span>
      <div className="pruebas__caso-texto">
        <p className="pruebas__caso-titulo">
          {caso.titulo}
          <span className="sr-only"> — {estado.texto}</span>
        </p>
        {caso.error && <p className="pruebas__caso-error">{caso.error.split('\n')[0]}</p>}
        <DiagnosticoCaso diagnostico={caso.diagnostico} />
        <p className="pruebas__meta">
          {[caso.modulo_nombre || caso.modulo, DISPOSITIVO[caso.dispositivo] ?? caso.dispositivo, duracion(caso.duracion_ms)].filter(Boolean).join(' · ')}
          {caso.estado === 'inestable' ? ' · pasó al reintentar' : ''}
        </p>
        {(caso.pasos?.length > 0 || caso.error) && (
          <details className="pruebas__detalle">
            <summary>Ver pasos{caso.error ? ' y error completo' : ''}</summary>
            {caso.pasos?.length > 0 && (
              <ol className="pruebas__pasos">{caso.pasos.map((paso, indice) => <li key={`${indice}-${paso}`}>{paso}</li>)}</ol>
            )}
            {caso.error && <pre className="pruebas__error-completo">{caso.error}</pre>}
          </details>
        )}
      </div>
    </li>
  );
};

export const ResultadoPruebaComponent = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const { ejecucion, error } = useEjecucionPrueba(id);
  const [filtro, setFiltro] = useState('todos');
  const [repitiendo, setRepitiendo] = useState(false);
  const [errorRepetir, setErrorRepetir] = useState('');

  if (!ejecucion) {
    return (
      <div className="pruebas">
        <TituloPaginaComponent title="Resultados de la ejecución" />
        {error ? <AlertaComponent type="warning" title="No se pudo abrir">{error}</AlertaComponent> : <p className="pruebas__vacio">Consultando…</p>}
        <Link className="btn btn--outline btn--sm" to="/mantenimiento/pruebas"><ArrowLeft size={14} aria-hidden="true" /> Volver a Pruebas</Link>
      </div>
    );
  }

  const resumen = ejecucion.resumen;
  const listaCaso = ejecucion.casos ?? [];
  const fallidos = listaCaso.filter((caso) => caso.estado === 'fallido').length;
  const elegido = LISTA_FILTRO.find((item) => item.id === filtro) ?? LISTA_FILTRO[0];

  const repetir = async () => {
    setRepitiendo(true);
    setErrorRepetir('');
    try {
      await pruebasApi.repetirFallidos(ejecucion.id);
      navigate('/mantenimiento/pruebas');
    } catch (fallo) {
      console.warn('No se pudieron repetir los fallidos:', fallo?.message ?? fallo);
      setErrorRepetir(fallo?.message || 'No se pudieron repetir los casos fallidos.');
    } finally {
      setRepitiendo(false);
    }
  };

  return (
    <div className="pruebas">
      <TituloPaginaComponent
        title={`Ejecución ${numeroEjecucion(ejecucion.numero)} · ${ejecucion.alcance_nombre}`}
        description={[
          resumen ? `${casosAprobados(resumen)} casos` : null,
          resumen ? duracion(resumen.duracion_ms) : null,
          ejecucion.navegador_nombre, `ambiente ${ejecucion.ambiente_nombre}`, ejecucion.iniciada_por,
        ].filter(Boolean).join(' · ')}
        action={<EstadoEjecucion estado={ejecucion.estado} />}
      />

      <div className="pruebas__acciones">
        <Link className="btn btn--outline btn--sm" to="/mantenimiento/pruebas"><ArrowLeft size={14} aria-hidden="true" /> Volver a Pruebas</Link>
        {ejecucion.run_url && (
          <a className="btn btn--secondary btn--sm" href={ejecucion.run_url} target="_blank" rel="noreferrer">
            <ExternalLink size={14} aria-hidden="true" /> Evidencias en GitHub
          </a>
        )}
        {fallidos > 0 && (
          <Permitido accion={ACCION.PRUEBA_EJECUTAR}>
            <BotonComponent variant="primary" size="sm" icon={RotateCcw} onClick={repetir} disabled={repitiendo}>
              {repitiendo ? 'Iniciando…' : 'Volver a ejecutar los fallidos'}
            </BotonComponent>
          </Permitido>
        )}
      </div>
      {errorRepetir && <AlertaComponent type="warning" title="No se pudo iniciar">{errorRepetir}</AlertaComponent>}
      {ejecucion.mensaje && !estaActiva(ejecucion) && ejecucion.estado !== 'aprobada' && (
        <AlertaComponent type="info" title="Detalle">{ejecucion.mensaje}</AlertaComponent>
      )}

      {estaActiva(ejecucion) && (
        <section className="pruebas__tarjeta" aria-label="Avance">
          <LineaTiempo pasos={ejecucion.pasos} />
        </section>
      )}

      <section className="pruebas__tarjeta" aria-labelledby="prueba-casos">
        <div className="pruebas__encabezado">
          <h2 id="prueba-casos" className="pruebas__subtitulo">Casos de prueba</h2>
          <div className="pruebas__filtros" role="group" aria-label="Filtrar casos">
            {LISTA_FILTRO.map((item) => (
              <button key={item.id} type="button" aria-pressed={filtro === item.id}
                className={`pruebas__filtro ${filtro === item.id ? 'pruebas__filtro--activo' : ''}`} onClick={() => setFiltro(item.id)}>
                {item.texto} <span className="pruebas__cuenta">{listaCaso.filter(item.incluye).length}</span>
              </button>
            ))}
          </div>
        </div>
        {listaCaso.length === 0 ? (
          <p className="pruebas__vacio">{estaActiva(ejecucion) ? 'Los casos aparecen cuando termina la ejecución.' : 'Esta ejecución no tiene casos.'}</p>
        ) : (
          <ul className="pruebas__casos" aria-label="Casos">
            {listaCaso.filter(elegido.incluye).map((caso) => <Caso key={caso.id || `${caso.titulo}-${caso.dispositivo}`} caso={caso} />)}
          </ul>
        )}
      </section>

      <p className="pruebas__nota">
        Si el repositorio tiene configurado el modelo, el Agente de Pruebas explica cada caso fallido: abre la aplicación con un
        navegador real (Playwright MCP) y revisa la página, la consola y las llamadas a la API. En GitHub, el artefacto «evidencias» trae el reporte HTML de Playwright, el JUnit y, de cada caso fallido, la captura, el video y
        la traza (se abre en trace.playwright.dev).
      </p>
    </div>
  );
};
