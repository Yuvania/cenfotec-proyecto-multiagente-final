import React, { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { CheckCircle2, Circle, ExternalLink, Loader2, MinusCircle, Play, Square, XCircle } from 'lucide-react';
import { TituloPaginaComponent } from '../Comun/TituloPaginaComponent';
import { BotonComponent } from '../Comun/BotonComponent';
import { AlertaComponent } from '../Comun/AlertaComponent';
import { SelectorComponent } from '../Comun/SelectorComponent';
import { useConfirmacion } from '../Comun/ConfirmacionComponent';
import { Permitido } from '../Sesion/SesionContext';
import { ACCION } from '../../config/acciones';
import { usePruebas } from '../../hooks/usePruebas';
import {
  ESTADO_EJECUCION, casosAprobados, duracion, estaActiva, fechaCorta, numeroEjecucion,
} from '../../utils/formatoPruebas';

// Tablero de las pruebas de Playwright. Corren en GitHub Actions (ver docs/pruebas-automatizadas.md).
const ICONO_ETAPA = Object.freeze({
  completa: CheckCircle2, en_curso: Loader2, fallida: XCircle, pendiente: Circle, omitida: MinusCircle, cancelada: MinusCircle,
});

export const EstadoEjecucion = ({ estado }) => {
  const actual = ESTADO_EJECUCION[estado] ?? { texto: estado, clase: 'neutro' };
  return <span className={`pruebas__estado pruebas__estado--${actual.clase}`}>{actual.texto}</span>;
};

const Indicador = ({ etiqueta, valor, detalle, clase = '' }) => (
  <div className={`pruebas__indicador ${clase}`}>
    <p className="pruebas__indicador-etiqueta">{etiqueta}</p>
    <p className="pruebas__indicador-valor">{valor}</p>
    {detalle && <p className="pruebas__indicador-detalle">{detalle}</p>}
  </div>
);

// Primero la opción del menú (como en la aplicación) y después lo que hay dentro de ella.
const NuevaEjecucion = ({ configuracion, bloqueada, enviando, alEjecutar }) => {
  const [ambiente, setAmbiente] = useState('pruebas');
  const [menu, setMenu] = useState('aplicacion');
  const [alcance, setAlcance] = useState('regresion');
  const [navegador, setNavegador] = useState('chromium');

  // En producción solo se ofrece lo que permite producción (las básicas, que solo leen).
  const listaPermitida = useMemo(() => (configuracion?.lista_alcance ?? [])
    .filter((item) => ambiente !== 'produccion' || item.permite_produccion), [configuracion, ambiente]);
  const listaMenu = useMemo(() => (configuracion?.lista_menu ?? [])
    .filter((item) => listaPermitida.some((alcanceItem) => alcanceItem.menu === item.codigo)), [configuracion, listaPermitida]);
  const listaAlcance = useMemo(() => listaPermitida.filter((item) => item.menu === menu), [listaPermitida, menu]);

  useEffect(() => {
    if (listaMenu.length && !listaMenu.some((item) => item.codigo === menu)) setMenu(listaMenu[0].codigo);
  }, [listaMenu, menu]);

  useEffect(() => {
    if (listaAlcance.length && !listaAlcance.some((item) => item.codigo === alcance)) setAlcance(listaAlcance[0].codigo);
  }, [listaAlcance, alcance]);

  const elegido = listaAlcance.find((item) => item.codigo === alcance);
  const ambienteElegido = configuracion?.lista_ambiente?.find((item) => item.codigo === ambiente);
  const enviar = (evento) => {
    evento.preventDefault();
    alEjecutar({ alcance, ambiente, navegador });
  };

  return (
    <form className="pruebas__tarjeta pruebas__nueva" onSubmit={enviar} aria-label="Nueva ejecución">
      <h2 className="pruebas__subtitulo">Nueva ejecución</h2>
      <div className="pruebas__campos">
        <SelectorComponent
          id="prueba-menu"
          label="Opción del menú"
          value={menu}
          onChange={(evento) => setMenu(evento.target.value)}
          options={listaMenu.map((item) => ({ value: item.codigo, label: item.nombre }))}
        />
        <SelectorComponent
          id="prueba-alcance"
          label="Qué probar"
          value={alcance}
          onChange={(evento) => setAlcance(evento.target.value)}
          options={listaAlcance.map((item) => ({ value: item.codigo, label: item.nombre }))}
          hint={elegido?.descripcion}
        />
        <SelectorComponent
          id="prueba-ambiente"
          label="Ambiente"
          value={ambiente}
          onChange={(evento) => setAmbiente(evento.target.value)}
          options={(configuracion?.lista_ambiente ?? []).map((item) => ({ value: item.codigo, label: item.nombre }))}
          hint={ambienteElegido?.descripcion}
        />
        <SelectorComponent
          id="prueba-navegador"
          label="Navegador"
          value={navegador}
          onChange={(evento) => setNavegador(evento.target.value)}
          options={(configuracion?.lista_navegador ?? []).map((item) => ({ value: item.codigo, label: item.nombre }))}
          hint="Cada caso se prueba en web, tablet y móvil."
        />
      </div>
      <div className="pruebas__pie-formulario">
        <BotonComponent type="submit" variant="primary" icon={Play} disabled={bloqueada || enviando || !listaAlcance.length}>
          {enviando ? 'Iniciando…' : 'Ejecutar pruebas'}
        </BotonComponent>
        {bloqueada && <p className="form-hint">Hay una ejecución en curso: espere a que termine o cancélela.</p>}
      </div>
    </form>
  );
};

export const LineaTiempo = ({ pasos = [] }) => (
  <ol className="pruebas__linea" aria-label="Avance de la ejecución">
    {pasos.map((paso) => {
      const Icono = ICONO_ETAPA[paso.estado] ?? Circle;
      return (
        <li key={paso.codigo} className={`pruebas__etapa pruebas__etapa--${paso.estado}`}>
          <Icono size={16} aria-hidden="true" className={paso.estado === 'en_curso' ? 'pruebas__girando' : ''} />
          <span>{paso.nombre}</span>
          <span className="sr-only">: {paso.estado.replace('_', ' ')}</span>
        </li>
      );
    })}
  </ol>
);

const EjecucionActual = ({ ejecucion, alCancelar }) => (
  <section className="pruebas__tarjeta pruebas__actual" aria-labelledby="prueba-actual-titulo">
    <div className="pruebas__encabezado">
      <h2 id="prueba-actual-titulo" className="pruebas__subtitulo">
        Ejecución actual <span className="pruebas__numero">{numeroEjecucion(ejecucion.numero)}</span>
      </h2>
      <EstadoEjecucion estado={ejecucion.estado} />
    </div>
    <p className="pruebas__meta">
      {ejecucion.alcance_nombre} · {ejecucion.navegador_nombre} · ambiente {ejecucion.ambiente_nombre}
      {ejecucion.iniciada_por ? ` · Iniciada por ${ejecucion.iniciada_por}` : ''} · {fechaCorta(ejecucion.creado_en)}
    </p>
    <LineaTiempo pasos={ejecucion.pasos} />
    {ejecucion.mensaje && <p className="form-hint">{ejecucion.mensaje}</p>}
    <div className="pruebas__acciones">
      {ejecucion.run_url && (
        <a className="btn btn--secondary btn--sm" href={ejecucion.run_url} target="_blank" rel="noreferrer">
          <ExternalLink size={14} aria-hidden="true" /> Ver en vivo en GitHub
        </a>
      )}
      <Permitido accion={ACCION.PRUEBA_EJECUTAR}>
        <BotonComponent variant="outline" size="sm" icon={Square} onClick={() => alCancelar(ejecucion)}>Cancelar ejecución</BotonComponent>
      </Permitido>
    </div>
  </section>
);

const fechaLarga = (valor) => new Date(valor).toLocaleDateString('es-CR', { day: 'numeric', month: 'long', year: 'numeric' });

// El token de GitHub con vencimiento corto (90 días): se avisa 14 días antes para renovarlo a tiempo.
export const AvisoTokenComponent = ({ token }) => {
  if (!token) return null;
  if (!token.informado) {
    return <p className="pruebas__nota">El token de GitHub no informa fecha de vencimiento: se recomienda uno con vencimiento de 90 días.</p>;
  }
  if (token.dias < 0) {
    return (
      <AlertaComponent type="danger" title="El token de GitHub venció">
        Venció el {fechaLarga(token.vence_en)}. Cree uno nuevo (90 días) y actualice GITHUB_PRUEBAS_TOKEN en el servicio.
      </AlertaComponent>
    );
  }
  if (token.por_vencer) {
    return (
      <AlertaComponent type="warning" title="El token de GitHub vence pronto">
        Vence el {fechaLarga(token.vence_en)} ({token.dias === 1 ? 'mañana' : `en ${token.dias} días`}). Renuévelo con vencimiento de 90 días
        y actualice GITHUB_PRUEBAS_TOKEN en el servicio.
      </AlertaComponent>
    );
  }
  return <p className="pruebas__nota">El token de GitHub vence el {fechaLarga(token.vence_en)}.</p>;
};

export const PruebasComponent = () => {
  const confirmar = useConfirmacion();
  const { configuracion, panel, cargando, error, enviando, ejecutar, cancelar } = usePruebas();
  const { indicador, activa, lista_ejecucion: listaEjecucion } = panel;
  const ultima = indicador?.ultima;
  const listaReciente = listaEjecucion.filter((item) => !estaActiva(item));

  const alCancelar = async (ejecucion) => {
    if (await confirmar({
      titulo: 'Cancelar ejecución',
      mensaje: `¿Cancelar la ejecución ${numeroEjecucion(ejecucion.numero)}? Los casos que ya corrieron no se guardan.`,
      textoConfirmar: 'Cancelar ejecución',
      peligro: true,
    })) await cancelar(ejecucion.id);
  };

  return (
    <div className="pruebas">
      <TituloPaginaComponent
        title="Pruebas automatizadas"
        description="Pruebas de la aplicación con Playwright en web, tablet y móvil. Elija qué probar y ejecútelas."
      />

      {configuracion && !configuracion.configurado && (
        <AlertaComponent type="info" title="Las pruebas todavía no están conectadas con GitHub">
          Falta {configuracion.faltante.join(' y ')} en el servicio. La guía está en Ayuda → Pruebas automatizadas.
        </AlertaComponent>
      )}
      {error && <AlertaComponent type="warning" title="Atención">{error}</AlertaComponent>}
      <AvisoTokenComponent token={configuracion?.token} />

      <div className="pruebas__indicadores" aria-label="Indicadores">
        <Indicador etiqueta="Última ejecución" valor={ultima ? numeroEjecucion(ultima.numero) : '—'}
          detalle={ultima ? `${ultima.total} casos` : 'Todavía no hay ejecuciones'} />
        <Indicador etiqueta="Casos aprobados" valor={ultima ? ultima.aprobados : '—'} clase="pruebas__indicador--exito" />
        <Indicador etiqueta="Casos fallidos" valor={ultima ? ultima.fallidos : '—'}
          clase={ultima?.fallidos ? 'pruebas__indicador--peligro' : ''} />
        <Indicador etiqueta="Duración" valor={ultima ? duracion(ultima.duracion_ms) : '—'} />
        <Indicador etiqueta="Éxito (últimas 10)" valor={indicador?.tasa_exito === null || indicador?.tasa_exito === undefined
          ? '—' : `${indicador.tasa_exito} %`} />
      </div>

      <div className="pruebas__columnas">
        <Permitido accion={ACCION.PRUEBA_EJECUTAR}>
          <NuevaEjecucion
            configuracion={configuracion}
            bloqueada={estaActiva(activa) || configuracion?.configurado === false}
            enviando={enviando}
            alEjecutar={ejecutar}
          />
        </Permitido>
        {estaActiva(activa) ? <EjecucionActual ejecucion={activa} alCancelar={alCancelar} /> : (
          <section className="pruebas__tarjeta pruebas__actual" aria-label="Ejecución actual">
            <h2 className="pruebas__subtitulo">Ejecución actual</h2>
            <p className="pruebas__vacio">No hay ninguna ejecución en curso.</p>
          </section>
        )}
      </div>

      <section className="pruebas__tarjeta" aria-labelledby="prueba-recientes">
        <h2 id="prueba-recientes" className="pruebas__subtitulo">Ejecuciones recientes</h2>
        {listaReciente.length === 0 ? (
          <p className="pruebas__vacio">{cargando ? 'Consultando…' : 'Todavía no hay ejecuciones terminadas.'}</p>
        ) : (
          <div className="pruebas__tabla-contenedor">
            <table className="pruebas__tabla">
              <thead>
                <tr>
                  <th scope="col">Ejecución</th><th scope="col">Qué se probó</th><th scope="col">Resultado</th>
                  <th scope="col">Casos</th><th scope="col">Duración</th><th scope="col">Iniciada por</th>
                  <th scope="col"><span className="sr-only">Acciones</span></th>
                </tr>
              </thead>
              <tbody>
                {listaReciente.map((item) => (
                  <tr key={item.id}>
                    <td className="pruebas__numero" data-etiqueta="Ejecución">{numeroEjecucion(item.numero)}</td>
                    <td data-etiqueta="Qué se probó">
                      <div>
                        {item.alcance_nombre}{item.solo_fallidos ? ' (solo fallidos)' : ''}
                        <span className="pruebas__meta-tabla">{item.navegador_nombre} · {item.ambiente_nombre}</span>
                      </div>
                    </td>
                    <td data-etiqueta="Resultado"><EstadoEjecucion estado={item.estado} /></td>
                    <td data-etiqueta="Casos">{casosAprobados(item.resumen)}</td>
                    <td data-etiqueta="Duración">{duracion(item.resumen?.duracion_ms)}</td>
                    <td data-etiqueta="Iniciada por">{item.iniciada_por || '—'}</td>
                    <td>
                      <Link className="btn btn--outline btn--sm" to={`/mantenimiento/pruebas/${item.id}`}
                        aria-label={`Ver resultados de la ejecución ${numeroEjecucion(item.numero)}`}>
                        Ver resultados
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <p className="pruebas__nota">
        Las evidencias (reporte HTML, JUnit, capturas, videos y trazas) quedan en GitHub con cada ejecución.
        Solo los roles con la acción «Ejecutar pruebas automatizadas» ven el botón. Cada ejecución queda a nombre de quien la inició.
      </p>
    </div>
  );
};
