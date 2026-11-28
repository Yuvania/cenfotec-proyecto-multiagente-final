import React, { useCallback, useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { NavLink, useLocation } from 'react-router-dom';
import { ChevronDown, Menu, X } from 'lucide-react';
import { listaOpcionMenu } from '../../config/rutas';

// Menú principal de la marca. Sale del registro único (src/config/rutas.jsx):
// - Web: barra lateral; los grupos (Mantenimiento) se despliegan con sus secciones.
// - Tablet: solo íconos; un grupo abre un panel al lado.
// - Móvil: barra inferior con las opciones marcadas «barraMovil» y «Más» para el resto.
const CONSULTA_TABLET = '(max-width: 1024px)';
const esTablet = () => typeof window !== 'undefined' && typeof window.matchMedia === 'function'
  && window.matchMedia(CONSULTA_TABLET).matches;

const dentroDe = (direccion, destino) => direccion === destino || direccion.startsWith(`${destino}/`);

const Contador = ({ valor }) => (valor > 0 ? (
  <span className="barra-lateral__contador" aria-label={`${valor} sin atender`}>{valor > 99 ? '99+' : valor}</span>
) : null);

const Enlace = ({ opcion, contador, alElegir, className = '' }) => {
  const { destino, etiqueta, corta, titulo, icono: Icono, exacta } = opcion;
  return (
    <NavLink
      to={destino}
      title={titulo}
      end={Boolean(exacta)}
      onClick={alElegir}
      className={({ isActive }) => `barra-lateral__enlace ${className} ${isActive ? 'active' : ''}`}
    >
      {Icono && <Icono size={18} aria-hidden="true" />}
      <span className="barra-lateral__etiqueta">{etiqueta}</span>
      <span className="barra-lateral__corta" aria-hidden="true">{corta ?? etiqueta}</span>
      <Contador valor={contador?.[opcion.contador]} />
    </NavLink>
  );
};

const ListaSeccion = ({ grupo, alElegir, claseEnlace }) => grupo.listaSeccion.map((seccion) => (
  <div key={seccion.id} className="barra-lateral__seccion" role="group" aria-label={seccion.titulo}>
    <p className="barra-lateral__seccion-titulo" aria-hidden="true">{seccion.titulo}</p>
    {seccion.listaOpcion.map((opcion) => (
      <NavLink key={opcion.destino} to={opcion.destino} title={opcion.titulo} onClick={alElegir}
        className={({ isActive }) => `${claseEnlace} ${isActive ? 'active' : ''}`}>
        {opcion.etiqueta}
      </NavLink>
    ))}
  </div>
));

const Grupo = ({ grupo }) => {
  const { pathname } = useLocation();
  const idPanel = useId();
  const contenedor = useRef(null);
  const activo = grupo.listaSeccion.some((seccion) => seccion.listaOpcion.some((opcion) => dentroDe(pathname, opcion.destino)));
  const [abierto, setAbierto] = useState(activo && !esTablet());
  const Icono = grupo.icono;

  // En web queda abierto mientras se está en una de sus pantallas; en tablet el panel se cierra al elegir.
  useEffect(() => { setAbierto(activo && !esTablet()); }, [pathname, activo]);

  useEffect(() => {
    if (!abierto || !esTablet()) return undefined;
    const cerrarAfuera = (evento) => { if (!contenedor.current?.contains(evento.target)) setAbierto(false); };
    const cerrarConEscape = (evento) => { if (evento.key === 'Escape') setAbierto(false); };
    document.addEventListener('mousedown', cerrarAfuera);
    document.addEventListener('keydown', cerrarConEscape);
    return () => {
      document.removeEventListener('mousedown', cerrarAfuera);
      document.removeEventListener('keydown', cerrarConEscape);
    };
  }, [abierto]);

  return (
    <div ref={contenedor} className={`barra-lateral__grupo barra-lateral__solo-escritorio ${abierto ? 'abierto' : ''}`}>
      <button
        type="button"
        className={`barra-lateral__enlace barra-lateral__grupo-boton ${activo ? 'active' : ''}`}
        aria-expanded={abierto}
        aria-controls={idPanel}
        title={grupo.titulo}
        onClick={() => setAbierto((valor) => !valor)}
      >
        <Icono size={18} aria-hidden="true" />
        <span className="barra-lateral__etiqueta">{grupo.etiqueta}</span>
        <ChevronDown size={14} aria-hidden="true" className="barra-lateral__chevron" />
      </button>
      <div id={idPanel} className="barra-lateral__submenu" hidden={!abierto}>
        <p className="barra-lateral__submenu-titulo" aria-hidden="true">{grupo.etiqueta}</p>
        <ListaSeccion grupo={grupo} claseEnlace="barra-lateral__subenlace" />
      </div>
    </div>
  );
};

// Móvil: «Más» abre una hoja con los grupos y las opciones que no caben en la barra inferior.
const HojaMas = ({ listaOpcion, contador, alCerrar }) => {
  const hoja = useRef(null);
  useEffect(() => {
    hoja.current?.querySelector('a, button')?.focus();
    const cerrarConEscape = (evento) => { if (evento.key === 'Escape') alCerrar(); };
    document.addEventListener('keydown', cerrarConEscape);
    return () => document.removeEventListener('keydown', cerrarConEscape);
  }, [alCerrar]);

  // Va al final del documento para quedar sobre el contenido y los botones flotantes; deja libre la barra inferior.
  return createPortal(
    <div className="hoja-mas" role="presentation" onMouseDown={(evento) => { if (evento.target === evento.currentTarget) alCerrar(); }}>
      <div ref={hoja} className="hoja-mas__panel" role="dialog" aria-modal="true" aria-label="Más opciones">
        <div className="hoja-mas__encabezado">
          <span className="hoja-mas__agarre" aria-hidden="true" />
          <button type="button" className="hoja-mas__cerrar" onClick={alCerrar} aria-label="Cerrar">
            <X size={18} aria-hidden="true" />
          </button>
        </div>
        {listaOpcion.map((opcion) => (opcion.tipo === 'grupo' ? (
          <section key={opcion.id} className="hoja-mas__grupo" aria-label={opcion.etiqueta}>
            <p className="hoja-mas__titulo">{opcion.etiqueta}</p>
            <ListaSeccion grupo={opcion} alElegir={alCerrar} claseEnlace="hoja-mas__enlace" />
          </section>
        ) : (
          <NavLink key={opcion.destino} to={opcion.destino} onClick={alCerrar}
            className={({ isActive }) => `hoja-mas__enlace hoja-mas__suelto ${isActive ? 'active' : ''}`}>
            {opcion.etiqueta}
            <Contador valor={contador?.[opcion.contador]} />
          </NavLink>
        )))}
      </div>
    </div>,
    document.body,
  );
};

export const MenuPrincipalComponent = ({ puede, contador }) => {
  const { pathname } = useLocation();
  const [mostrarMas, setMostrarMas] = useState(false);
  const cerrarMas = useCallback(() => setMostrarMas(false), []);
  const listaOpcion = listaOpcionMenu(puede);
  const listaMas = listaOpcion.filter((opcion) => opcion.tipo === 'grupo' || !opcion.barraMovil);
  const masActivo = listaMas.some((opcion) => (opcion.tipo === 'grupo'
    ? opcion.listaSeccion.some((seccion) => seccion.listaOpcion.some((item) => dentroDe(pathname, item.destino)))
    : dentroDe(pathname, opcion.destino)));

  return (
    <>
      <nav className="barra-lateral__nav" aria-label="Menú principal">
        {listaOpcion.map((opcion) => (opcion.tipo === 'grupo'
          ? <Grupo key={opcion.id} grupo={opcion} />
          : <Enlace key={opcion.destino} opcion={opcion} contador={contador}
            className={opcion.barraMovil ? '' : 'barra-lateral__solo-escritorio'} />))}
        {listaMas.length > 0 && (
          <button type="button" className={`barra-lateral__enlace barra-lateral__mas ${masActivo ? 'active' : ''}`}
            aria-haspopup="dialog" aria-expanded={mostrarMas} onClick={() => setMostrarMas(true)}>
            <Menu size={18} aria-hidden="true" />
            <span className="barra-lateral__corta" aria-hidden="true">Más</span>
            <span className="sr-only">Más opciones</span>
          </button>
        )}
      </nav>
      {mostrarMas && <HojaMas listaOpcion={listaMas} contador={contador} alCerrar={cerrarMas} />}
    </>
  );
};
