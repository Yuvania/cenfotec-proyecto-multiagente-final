import React, { useCallback, useEffect, useState } from 'react';
import { TituloPaginaComponent } from '../Comun/TituloPaginaComponent';
import { AlertaComponent } from '../Comun/AlertaComponent';
import { mantenimientoApi } from '../../services/seguridadApi';
import { useSesion } from '../Sesion/SesionContext';
import { UsuariosMantenimientoComponent } from './UsuariosMantenimientoComponent';
import { RolesMantenimientoComponent } from './RolesMantenimientoComponent';

// Mantenimiento › Seguridad: a los usuarios se les asignan o quitan roles y a los roles se les asignan o quitan
// acciones. Son dos opciones del menú (Usuarios, y Roles y acciones) que comparten la carga de roles y acciones.
// Las acciones salen del catálogo del backend: una acción nueva aparece aquí sin tocar esta pantalla.
const useSeguridad = () => {
  const { seguridad } = useSesion();
  const [listaRol, setListaRol] = useState([]);
  const [listaAccion, setListaAccion] = useState([]);
  const [error, setError] = useState('');

  const cargarRol = useCallback(async () => {
    try {
      setListaRol(await mantenimientoApi.listarRol());
    } catch (fallo) {
      console.error('No se pudieron cargar los roles:', fallo);
      setError(fallo?.message || 'No se pudieron cargar los roles.');
    }
  }, []);

  useEffect(() => {
    if (!seguridad) return;
    cargarRol();
    mantenimientoApi.listarAccion().then(setListaAccion).catch((fallo) => {
      console.error('No se pudo cargar el catálogo de acciones:', fallo);
      setError(fallo?.message || 'No se pudo cargar el catálogo de acciones.');
    });
  }, [seguridad, cargarRol]);

  return { seguridad, listaRol, listaAccion, error, cargarRol };
};

const PaginaSeguridad = ({ titulo, descripcion, children, seguridad, error }) => (
  <div>
    <TituloPaginaComponent title={titulo} description={descripcion} />
    {!seguridad ? (
      <AlertaComponent type="info" title="La seguridad no está activa en este ambiente">
        En desarrollo local (sin ACCESO_USUARIO y ACCESO_CLAVE) todas las acciones están permitidas y no hay usuarios.
      </AlertaComponent>
    ) : (
      <>
        {error && <AlertaComponent type="danger" title="No se pudo cargar">{error}</AlertaComponent>}
        {children}
      </>
    )}
  </div>
);

export const MantenimientoUsuariosComponent = () => {
  const { seguridad, listaRol, error, cargarRol } = useSeguridad();
  return (
    <PaginaSeguridad titulo="Usuarios" descripcion="Busque a una persona y asígnele o quítele roles. Un cambio aplica de inmediato."
      seguridad={seguridad} error={error}>
      <UsuariosMantenimientoComponent listaRol={listaRol} alCambiar={cargarRol} />
    </PaginaSeguridad>
  );
};

export const MantenimientoRolesComponent = () => {
  const { seguridad, listaRol, listaAccion, error, cargarRol } = useSeguridad();
  return (
    <PaginaSeguridad titulo="Roles y acciones" descripcion="Elija un rol y marque las acciones que permite. Un cambio aplica de inmediato."
      seguridad={seguridad} error={error}>
      <RolesMantenimientoComponent listaRol={listaRol} listaAccion={listaAccion} alCambiar={cargarRol} />
    </PaginaSeguridad>
  );
};
