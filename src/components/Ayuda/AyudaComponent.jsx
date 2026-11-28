import React from 'react';
import { TituloPaginaComponent } from '../Comun/TituloPaginaComponent';
import { SeccionesConPestanasComponent } from '../HistoriaUsuario/detalle/SeccionesConPestanasComponent';
import { TarjetaItemsAyudaComponent } from './TarjetaItemsAyudaComponent';
import { EjemploHuAyudaComponent } from './EjemploHuAyudaComponent';
import { EquipoAyudaComponent } from './EquipoAyudaComponent';
import { ArquitecturaAyudaComponent } from './ArquitecturaAyudaComponent';
import {
  ACCIONES_HISTORIA, NAVEGACION_ASISTENTE, PASOS_ASISTENTE, PENDIENTES, PRUEBAS_AUTOMATIZADAS,
} from '../../data/ayudaDocumentacion';

// Arquitectura reúne cómo funciona, los agentes, las tecnologías, la construcción y el diseño.
const SECCIONES = [
  {
    id: 'asistente',
    titulo: 'Pasos del asistente',
    contenido: (
      <TarjetaItemsAyudaComponent
        title="¿Cómo funciona el Asistente IA?"
        subtitle="Flujo principal de 5 pasos"
        items={PASOS_ASISTENTE}
      >
        <h5 className="ayuda-item__titulo ayuda-item__titulo--aparte">Cómo moverse entre pasos</h5>
        <ul className="ayuda-item__puntos">
          {NAVEGACION_ASISTENTE.map((texto) => <li key={texto}>{texto}</li>)}
        </ul>
      </TarjetaItemsAyudaComponent>
    ),
  },
  {
    id: 'acciones',
    titulo: 'Acciones sobre una HU',
    contenido: (
      <TarjetaItemsAyudaComponent
        title="Qué hace cada acción"
        subtitle="Íconos en el listado de historias (con una breve descripción al pasar el cursor)"
        items={ACCIONES_HISTORIA}
      />
    ),
  },
  { id: 'ejemplo', titulo: 'Ejemplo de HU generada', contenido: <EjemploHuAyudaComponent /> },
  { id: 'arquitectura', titulo: 'Arquitectura', contenido: <ArquitecturaAyudaComponent /> },
  {
    id: 'pruebas',
    titulo: 'Pruebas automatizadas',
    contenido: (
      <TarjetaItemsAyudaComponent
        title="Pruebas automatizadas con Playwright"
        subtitle="Qué prueban, dónde corren y cómo se configuran"
        items={PRUEBAS_AUTOMATIZADAS}
      />
    ),
  },
  {
    id: 'pendientes',
    titulo: 'Por definir',
    contenido: (
      <TarjetaItemsAyudaComponent
        title="Lo que falta definir"
        subtitle="Propuestas y decisiones pendientes: roles y permisos, usuarios y aviso al Product Owner, entre otras"
        items={PENDIENTES}
      />
    ),
  },
  { id: 'equipo', titulo: 'Equipo', contenido: <EquipoAyudaComponent /> },
];

export const AyudaComponent = () => (
  <div>
    <TituloPaginaComponent
      title="Centro de Ayuda y Documentación"
      description="Cómo funciona el sistema de Historias de Usuario. Para dudas puntuales, use el chat de ayuda (botón «¿Cómo se usa?», abajo a la derecha)."
    />
    <SeccionesConPestanasComponent etiqueta="Secciones de la ayuda" inicial="asistente" secciones={SECCIONES} />
  </div>
);
