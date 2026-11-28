import React, { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { TituloPaginaComponent } from '../Comun/TituloPaginaComponent';
import { BotonComponent } from '../Comun/BotonComponent';
import { usePendientes } from '../../hooks/usePendientes';

// Notificaciones: una sola lista. Cada notificación lleva su categoría como etiqueta y arriba se filtra.
// Primero lo que requiere acción, después los avisos sin leer y al final los leídos, del más nuevo al más viejo.
export const CATEGORIA = Object.freeze({
  por_aprobar: { texto: 'Por aprobar', clase: 'accion', accion: true },
  cambio_por_decidir: { texto: 'Cambio por decidir', clase: 'cambio', accion: true },
  devuelta: { texto: 'Devuelta', clase: 'advertencia', accion: false },
  rechazada: { texto: 'Rechazada', clase: 'peligro', accion: false },
  aprobada: { texto: 'Aprobada', clase: 'exito', accion: false },
  // Un agente no pudo terminar después de los reintentos automáticos: se retoma desde aquí.
  fallo: { texto: 'Falló un agente', clase: 'peligro', accion: false },
});

// Los avisos que se retoman desde la notificación: la historia devuelta y la que se detuvo por un fallo.
const CATEGORIA_RETOMAR = Object.freeze(['devuelta', 'fallo']);

const FILTRO_TODAS = 'todas';
const FILTRO_ACCION = 'accion';

const fecha = (valor) => {
  if (!valor) return '';
  const leida = new Date(valor);
  return Number.isNaN(leida.getTime()) ? '' : leida.toLocaleString('es-CR', { dateStyle: 'medium', timeStyle: 'short' });
};

const instante = (valor) => {
  const leida = new Date(valor ?? 0).getTime();
  return Number.isNaN(leida) ? 0 : leida;
};

/** Une lo que espera decisión y los avisos en una lista con categoría, en el orden en que se muestran. */
export const unirNotificaciones = (porDecidir = [], avisos = []) => {
  const listaAccion = porDecidir.map((item) => ({
    id: `decidir-${item.workflow_id}`,
    categoria: CATEGORIA[item.tipo] ? item.tipo : 'por_aprobar',
    titulo: item.titulo,
    detalle: item.tipo === 'cambio_por_decidir'
      ? 'Falta su decisión sobre el cambio.'
      : `${item.creado_por ? `${item.creado_por} la envió` : 'Se envió'} para su aprobación.`,
    fecha: item.actualizado_en,
    leido: false,
    requiereAccion: true,
    workflowId: item.workflow_id,
  }));
  const listaAviso = avisos.map((aviso) => ({
    id: aviso.id,
    avisoId: aviso.id,
    categoria: CATEGORIA[aviso.tipo] ? aviso.tipo : 'devuelta',
    titulo: aviso.titulo,
    detalle: aviso.tipo === 'fallo' ? (aviso.detalle || 'Un agente no pudo terminar. El avance quedó guardado.')
      : aviso.detalle ? `Motivo: ${aviso.detalle}` : (aviso.tipo === 'aprobada' ? `${aviso.autor || 'El Product Owner'} la aprobó.` : ''),
    autor: aviso.autor,
    fecha: aviso.creado_en,
    leido: Boolean(aviso.leido),
    requiereAccion: false,
    workflowId: aviso.workflow_id,
  }));
  const peso = (item) => (item.requiereAccion ? 0 : item.leido ? 2 : 1);
  return [...listaAccion, ...listaAviso].sort((a, b) => peso(a) - peso(b) || instante(b.fecha) - instante(a.fecha));
};

export const NotificacionesComponent = () => {
  const navigate = useNavigate();
  const { por_decidir: porDecidir, avisos, cargando, marcarLeido, marcarTodoLeido } = usePendientes();
  const [filtro, setFiltro] = useState(FILTRO_TODAS);
  const listaNotificacion = useMemo(() => unirNotificaciones(porDecidir, avisos), [porDecidir, avisos]);
  const abrir = (workflowId) => navigate(`/historias/nueva?flujo=${encodeURIComponent(workflowId)}`);

  const listaFiltro = [
    { id: FILTRO_TODAS, texto: 'Todas', incluye: () => true },
    { id: FILTRO_ACCION, texto: 'Requieren acción', incluye: (item) => item.requiereAccion },
    ...Object.entries(CATEGORIA).map(([id, categoria]) => ({ id, texto: categoria.texto, incluye: (item) => item.categoria === id })),
  ].map((item) => ({ ...item, cuenta: listaNotificacion.filter(item.incluye).length }))
    // Las categorías sin notificaciones no se muestran; «Todas» y «Requieren acción» siempre.
    .filter((item) => item.id === FILTRO_TODAS || item.id === FILTRO_ACCION || item.cuenta > 0);

  const elegido = listaFiltro.find((item) => item.id === filtro) ?? listaFiltro[0];
  const listaVisible = listaNotificacion.filter(elegido.incluye);
  const haySinLeer = listaNotificacion.some((item) => !item.requiereAccion && !item.leido);

  return (
    <div className="notificaciones">
      <TituloPaginaComponent
        title="Notificaciones"
        description="Lo que espera su decisión y lo que pasó con sus historias. Filtre por categoría."
        action={haySinLeer ? (
          <BotonComponent variant="secondary" size="sm" onClick={marcarTodoLeido}>Marcar todo como leído</BotonComponent>
        ) : null}
      />

      <div className="notificaciones__filtros" role="group" aria-label="Filtrar por categoría">
        {listaFiltro.map((item) => (
          <button key={item.id} type="button" aria-pressed={elegido.id === item.id}
            className={`notificaciones__filtro ${elegido.id === item.id ? 'notificaciones__filtro--activo' : ''}`}
            onClick={() => setFiltro(item.id)}>
            {item.texto} <span className="notificaciones__cuenta">{item.cuenta}</span>
          </button>
        ))}
      </div>

      <section className="notificaciones__lista" aria-label="Lista de notificaciones">
        {listaVisible.length === 0 ? (
          <p className="notificaciones__vacio">
            {cargando ? 'Consultando…' : elegido.id === FILTRO_TODAS ? 'No tiene notificaciones.' : 'No hay notificaciones en esta categoría.'}
          </p>
        ) : (
          <ul>
            {listaVisible.map((item) => {
              const categoria = CATEGORIA[item.categoria];
              return (
                <li key={item.id} className={`notificaciones__fila ${item.leido ? 'notificaciones__fila--leida' : ''}`}>
                  <span className={`notificaciones__punto ${item.leido ? 'notificaciones__punto--leido' : ''}`} aria-hidden="true" />
                  <div className="notificaciones__texto">
                    <p className="notificaciones__meta">
                      <span className={`notificaciones__etiqueta notificaciones__etiqueta--${categoria.clase}`}>{categoria.texto}</span>
                      <span>
                        {item.requiereAccion ? 'Requiere su acción' : item.leido ? 'Aviso · leído' : 'Aviso'}
                        {item.fecha ? ` · ${fecha(item.fecha)}` : ''}
                      </span>
                    </p>
                    <p className="notificaciones__nombre">{item.titulo}</p>
                    {item.detalle && <p className="notificaciones__detalle">{item.detalle}</p>}
                  </div>
                  <div className="notificaciones__acciones">
                    {item.requiereAccion && (
                      <BotonComponent variant="primary" size="sm" onClick={() => abrir(item.workflowId)}>
                        {item.categoria === 'por_aprobar' ? 'Revisar y decidir' : 'Revisar'}
                      </BotonComponent>
                    )}
                    {CATEGORIA_RETOMAR.includes(item.categoria) && item.workflowId && (
                      <BotonComponent variant="secondary" size="sm" onClick={() => abrir(item.workflowId)}>Retomar</BotonComponent>
                    )}
                    {!item.requiereAccion && !item.leido && (
                      <BotonComponent variant="secondary" size="sm" onClick={() => marcarLeido(item.avisoId)}>Marcar como leído</BotonComponent>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
};
