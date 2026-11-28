import { describe, expect, it } from 'vitest';
import { listaOpcionMenu, listaRuta, rutaDeMigas } from '../rutas';
import { ACCION } from '../acciones';

// Barandas del registro único de pantallas (ver docs/arquitectura.md, skill «agregar-ruta»).
describe('registro de pantallas', () => {
  it('cada ruta es única y tiene componente', () => {
    const ruta = listaRuta.map((entrada) => entrada.ruta);
    expect(new Set(ruta).size).toBe(ruta.length);
    listaRuta.forEach((entrada) => expect(typeof entrada.componente).toBe('function'));
  });

  it('el menú sale del registro, en orden y sin órdenes repetidos', () => {
    const listaOpcion = listaOpcionMenu();
    expect(listaOpcion.map((opcion) => opcion.etiqueta)).toEqual(['Inicio', 'Notificaciones', 'Historias de usuario', 'Mantenimiento', 'Ayuda']);
    expect(new Set(listaOpcion.map((opcion) => opcion.orden)).size).toBe(listaOpcion.length);
    listaOpcion.forEach((opcion) => {
      expect(opcion.titulo).toBeTruthy();
      expect(opcion.icono).toBeTruthy();
    });
  });

  it('Mantenimiento agrupa Seguridad, Calidad y Métricas, y solo muestra lo permitido', () => {
    const grupo = listaOpcionMenu().find((opcion) => opcion.tipo === 'grupo');
    expect(grupo.listaSeccion.map((seccion) => [seccion.titulo, seccion.listaOpcion.map((opcion) => opcion.etiqueta)])).toEqual([
      ['Seguridad', ['Usuarios', 'Roles y acciones']],
      ['Calidad', ['Pruebas automatizadas']],
      ['Métricas', ['Consumo del modelo']],
    ]);
    const soloPruebas = listaOpcionMenu((accion) => !accion || accion === ACCION.PRUEBA_VER);
    expect(soloPruebas.find((opcion) => opcion.tipo === 'grupo').listaSeccion.map((seccion) => seccion.titulo)).toEqual(['Calidad']);
    const sinNada = listaOpcionMenu((accion) => !accion);
    expect(sinNada.some((opcion) => opcion.tipo === 'grupo')).toBe(false);
  });

  it('en móvil la barra inferior lleva Inicio, Notificaciones e Historias; el resto va en «Más»', () => {
    expect(listaOpcionMenu().filter((opcion) => opcion.barraMovil).map((opcion) => opcion.corta)).toEqual(['Inicio', 'Avisos', 'Historias']);
  });

  it('la ruta de migas sale del grupo y de la opción del menú', () => {
    expect(rutaDeMigas('/mantenimiento/pruebas')).toEqual({
      grupo: 'Mantenimiento', seccion: 'Calidad', opcion: { etiqueta: 'Pruebas automatizadas', destino: '/mantenimiento/pruebas' }, esPrincipal: true,
    });
    expect(rutaDeMigas('/mantenimiento/pruebas/abc').esPrincipal).toBe(false);
    expect(rutaDeMigas('/mantenimiento/consumo').seccion).toBe('Métricas');
    expect(rutaDeMigas('/historias')).toBeNull();
  });
});
