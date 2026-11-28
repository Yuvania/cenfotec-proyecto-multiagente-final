// Registro único de pantallas: de aquí salen las rutas de la aplicación y las opciones del menú.
// Agregar una pantalla = agregar una entrada. Si debe verse en el menú, se le pone «menu».
// Si solo deben verla quienes tengan una acción, se le pone «accion» (src/config/acciones.js).
// Ver docs/arquitectura.md y la skill «agregar-ruta».
import React from 'react';
import { Navigate, useParams } from 'react-router-dom';
import { LayoutDashboard, FileText, HelpCircle, Bell, Settings } from 'lucide-react';
import { ACCION } from './acciones';
import { TableroComponent } from '../components/Dashboard/TableroComponent';
import { ListaHistoriaUsuarioComponent } from '../components/HistoriaUsuario/ListaHistoriaUsuarioComponent';
import { CrearHistoriaUsuarioComponent } from '../components/HistoriaUsuario/CrearHistoriaUsuarioComponent';
import { DetalleHistoriaUsuarioComponent } from '../components/HistoriaUsuario/DetalleHistoriaUsuarioComponent';
import { SolicitarCambioHistoriaComponent } from '../components/HistoriaUsuario/SolicitarCambioHistoriaComponent';
import { EditarHistoriaUsuarioComponent } from '../components/HistoriaUsuario/EditarHistoriaUsuarioComponent';
import { ListaHabilidadComponent } from '../components/Habilidad/ListaHabilidadComponent';
import { AyudaComponent } from '../components/Ayuda/AyudaComponent';
import { ListaLeccionComponent } from '../components/Leccion/ListaLeccionComponent';
import { MantenimientoRolesComponent, MantenimientoUsuariosComponent } from '../components/Mantenimiento/MantenimientoComponent';
import { NotificacionesComponent } from '../components/Notificaciones/NotificacionesComponent';
import { PruebasComponent } from '../components/Pruebas/PruebasComponent';
import { ResultadoPruebaComponent } from '../components/Pruebas/ResultadoPruebaComponent';
import { ConsumoModeloComponent } from '../components/Metricas/ConsumoModeloComponent';

// Grupos del menú: una opción que se abre y muestra sus opciones por sección.
// En web se despliega en la barra lateral, en tablet se abre un panel y en móvil va dentro de «Más».
export const listaGrupoMenu = Object.freeze([
  {
    id: 'mantenimiento',
    etiqueta: 'Mantenimiento',
    titulo: 'Usuarios, roles, pruebas y consumo del modelo',
    icono: Settings,
    orden: 80,
    listaSeccion: [
      { id: 'seguridad', titulo: 'Seguridad' },
      { id: 'calidad', titulo: 'Calidad' },
      { id: 'metricas', titulo: 'Métricas' },
    ],
  },
]);

// Las direcciones viejas siguen funcionando: llevan a la nueva.
const redirigir = (destino) => function Redireccion() {
  const parametro = useParams();
  return <Navigate to={destino.replace(/:(\w+)/g, (_, clave) => encodeURIComponent(parametro[clave] ?? ''))} replace />;
};

// ruta: relativa a la raíz ('' es el inicio). componente: lo que se muestra.
// accion (opcional): acción (o lista; basta una) que hace falta para abrirla. menu.accion la reemplaza solo
// para mostrar la opción en el menú.
// menu (opcional): etiqueta, corta (en la barra inferior del móvil, máximo 9 letras), título (texto
// emergente), ícono, orden, si la ruta debe coincidir exacta, contador (el número que se muestra al lado),
// barraMovil (si va en la barra inferior del móvil; las demás van en «Más») y, si pertenece a un grupo,
// grupo y seccion (de listaGrupoMenu).
// Las pantallas internas de un grupo (por ejemplo, los resultados de una ejecución) toman la ruta
// «Mantenimiento › Calidad › …» de la opción del menú cuya dirección las contiene.
export const listaRuta = Object.freeze([
  {
    ruta: '',
    componente: TableroComponent,
    menu: { etiqueta: 'Inicio', corta: 'Inicio', titulo: 'Ir al inicio', icono: LayoutDashboard, orden: 10, exacta: true, barraMovil: true },
  },
  {
    ruta: 'notificaciones',
    componente: NotificacionesComponent,
    menu: { etiqueta: 'Notificaciones', corta: 'Avisos', titulo: 'Lo que espera su decisión y lo que pasó con sus historias', icono: Bell, orden: 15, contador: 'notificaciones', barraMovil: true },
  },
  { ruta: 'pendientes', componente: redirigir('/notificaciones') },
  {
    ruta: 'historias',
    componente: ListaHistoriaUsuarioComponent,
    accion: ACCION.HISTORIA_VER,
    // «Nueva historia» está en el listado: crear queda junto a lo que se crea.
    menu: { etiqueta: 'Historias de usuario', corta: 'Historias', titulo: 'Ver y crear historias de usuario', icono: FileText, orden: 20, barraMovil: true },
  },
  {
    ruta: 'historias/nueva',
    componente: CrearHistoriaUsuarioComponent,
    // También se abre para retomar una historia en proceso: responder a negocio o decidir como Product Owner.
    accion: [ACCION.HISTORIA_CREAR, ACCION.HISTORIA_RESPONDER_NEGOCIO, ACCION.HISTORIA_APROBAR,
      ACCION.HISTORIA_DEVOLVER, ACCION.HISTORIA_RECHAZAR],
  },
  { ruta: 'historias/:id', componente: DetalleHistoriaUsuarioComponent, accion: ACCION.HISTORIA_VER },
  { ruta: 'historias/:id/editar', componente: EditarHistoriaUsuarioComponent, accion: ACCION.HISTORIA_EDITAR },
  { ruta: 'historias/:id/solicitar-cambio', componente: SolicitarCambioHistoriaComponent, accion: ACCION.CAMBIO_SOLICITAR },
  { ruta: 'lecciones', componente: ListaLeccionComponent, accion: ACCION.LECCION_VER },
  { ruta: 'skills', componente: ListaHabilidadComponent },
  {
    ruta: 'mantenimiento/usuarios',
    componente: MantenimientoUsuariosComponent,
    accion: ACCION.MANTENIMIENTO_VER,
    menu: { etiqueta: 'Usuarios', corta: 'Usuarios', titulo: 'Usuarios y sus roles', orden: 81, grupo: 'mantenimiento', seccion: 'seguridad' },
  },
  {
    ruta: 'mantenimiento/roles',
    componente: MantenimientoRolesComponent,
    accion: ACCION.MANTENIMIENTO_VER,
    menu: { etiqueta: 'Roles y acciones', corta: 'Roles', titulo: 'Roles y las acciones que permiten', orden: 82, grupo: 'mantenimiento', seccion: 'seguridad' },
  },
  {
    ruta: 'mantenimiento/pruebas',
    componente: PruebasComponent,
    accion: ACCION.PRUEBA_VER,
    menu: { etiqueta: 'Pruebas automatizadas', corta: 'Pruebas', titulo: 'Ejecutar las pruebas de la aplicación y ver sus resultados', orden: 83, grupo: 'mantenimiento', seccion: 'calidad' },
  },
  { ruta: 'mantenimiento/pruebas/:id', componente: ResultadoPruebaComponent, accion: ACCION.PRUEBA_VER },
  {
    ruta: 'mantenimiento/consumo',
    componente: ConsumoModeloComponent,
    accion: ACCION.METRICA_VER,
    menu: { etiqueta: 'Consumo del modelo', corta: 'Consumo', titulo: 'Tokens y costo por historia, por agente y por día', orden: 84, grupo: 'mantenimiento', seccion: 'metricas' },
  },
  { ruta: 'mantenimiento', componente: redirigir('/mantenimiento/usuarios') },
  { ruta: 'pruebas', componente: redirigir('/mantenimiento/pruebas') },
  { ruta: 'pruebas/:id', componente: redirigir('/mantenimiento/pruebas/:id') },
  {
    ruta: 'ayuda',
    componente: AyudaComponent,
    menu: { etiqueta: 'Ayuda', corta: 'Ayuda', titulo: 'Ver Ayuda', icono: HelpCircle, orden: 90 },
  },
]);

const opcionDe = ({ ruta, menu: { accion: _accion, ...menu } }) => ({ ...menu, destino: `/${ruta}` });

/**
 * Opciones del menú principal, en su orden. «puede» filtra las que la persona no tiene permitidas.
 * Una opción suelta es { tipo: 'enlace', ... }; un grupo es { tipo: 'grupo', ..., listaSeccion: [{ titulo, listaOpcion }] }
 * y solo aparece si la persona puede abrir alguna de sus opciones.
 */
export const listaOpcionMenu = (puede = () => true) => {
  const listaPermitida = listaRuta.filter((entrada) => entrada.menu && puede(entrada.menu.accion ?? entrada.accion));
  const listaSuelta = listaPermitida.filter((entrada) => !entrada.menu.grupo).map((entrada) => ({ tipo: 'enlace', ...opcionDe(entrada) }));
  const listaGrupo = listaGrupoMenu.map(({ listaSeccion, ...grupo }) => ({
    tipo: 'grupo',
    ...grupo,
    listaSeccion: listaSeccion.map((seccion) => ({
      ...seccion,
      listaOpcion: listaPermitida
        .filter((entrada) => entrada.menu.grupo === grupo.id && entrada.menu.seccion === seccion.id)
        .map(opcionDe)
        .sort((a, b) => a.orden - b.orden),
    })).filter((seccion) => seccion.listaOpcion.length > 0),
  })).filter((grupo) => grupo.listaSeccion.length > 0);
  return [...listaSuelta, ...listaGrupo].sort((a, b) => a.orden - b.orden);
};

/** «Mantenimiento › Calidad › Pruebas automatizadas» para la dirección actual, o null si no está en un grupo. */
export const rutaDeMigas = (direccion) => {
  const listaOpcionGrupo = listaRuta.filter((entrada) => entrada.menu?.grupo);
  const opcion = listaOpcionGrupo
    .filter((entrada) => direccion === `/${entrada.ruta}` || direccion.startsWith(`/${entrada.ruta}/`))
    .sort((a, b) => b.ruta.length - a.ruta.length)[0];
  if (!opcion) return null;
  const grupo = listaGrupoMenu.find((item) => item.id === opcion.menu.grupo);
  const seccion = grupo?.listaSeccion.find((item) => item.id === opcion.menu.seccion);
  return {
    grupo: grupo?.etiqueta,
    seccion: seccion?.titulo,
    opcion: { etiqueta: opcion.menu.etiqueta, destino: `/${opcion.ruta}` },
    esPrincipal: direccion === `/${opcion.ruta}`,
  };
};
