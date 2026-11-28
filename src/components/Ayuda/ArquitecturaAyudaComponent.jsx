import React from 'react';
import { TarjetaComponent } from '../Comun/TarjetaComponent';
import { TarjetaItemsAyudaComponent } from './TarjetaItemsAyudaComponent';
import { AgenteAyudaComponent } from './AgenteAyudaComponent';
import { FlujoAyudaComponent } from './FlujoAyudaComponent';
import {
  CAMBIO_ARQUITECTURA, CAPA_ARQUITECTURA, DISPOSITIVO_DISENO, FLUJO_CONSULTA, FLUJO_PRUEBAS, IA_ARQUITECTURA,
  NOTA_FLUJO_CONSULTA, NOTA_FLUJO_PRUEBAS, OPCION_MENU, PALETA_COLOR, PRINCIPIO_ARQUITECTURA, PRODUCCION_ARQUITECTURA,
  REPOSITORIO_PRUEBAS, RESUMEN_ARQUITECTURA, TECNOLOGIAS, TIPOGRAFIA_DISENO,
} from '../../data/ayudaDocumentacion';

const ListaPunto = ({ lista }) => (
  <ul className="ayuda-item__puntos">
    {lista.map((texto) => <li key={texto}>{texto}</li>)}
  </ul>
);

// Paleta de colores: la muestra usa la variable del tema, así se ve bien en modo claro y oscuro.
const PaletaComponent = () => (
  <TarjetaComponent title="Paleta de colores" subtitle="Cada color es una variable del tema (src/styles/_theme.scss) con su valor en modo claro y oscuro">
    <ul className="ayuda-paleta">
      {PALETA_COLOR.map(({ nombre, variable, claro, oscuro, uso }) => (
        <li key={variable} className="ayuda-paleta__color">
          <span className="ayuda-paleta__muestra" style={{ backgroundColor: `var(${variable})` }} aria-hidden="true" />
          <div>
            <p className="ayuda-paleta__nombre">{nombre}</p>
            <p className="ayuda-paleta__valor"><code>{variable}</code> · claro {claro} · oscuro {oscuro}</p>
            <p className="ayuda-paleta__uso">{uso}</p>
          </div>
        </li>
      ))}
    </ul>
  </TarjetaComponent>
);

const idGrupo = (id) => `ayuda-arquitectura-${id}`;

// Grupos de la sección, en orden. Cada uno tiene su título y sus tarjetas.
const LISTA_GRUPO = [
  {
    id: 'funciona',
    titulo: 'Cómo funciona',
    contenido: (
      <>
        <TarjetaComponent title="Para ponerse al día" subtitle="Lo esencial del proyecto en un minuto">
          <ListaPunto lista={RESUMEN_ARQUITECTURA} />
        </TarjetaComponent>
        <TarjetaItemsAyudaComponent
          title="Qué hace cada opción del menú"
          subtitle="Lo que encuentra en cada parte de la aplicación"
          items={OPCION_MENU}
        />
        <FlujoAyudaComponent
          title="Cómo viaja una consulta entre los agentes"
          subtitle="Desde que usted envía el requerimiento hasta que ve el resultado"
          pasos={FLUJO_CONSULTA}
          nota={NOTA_FLUJO_CONSULTA}
        />
        <FlujoAyudaComponent
          title="Cómo funcionan las pruebas automatizadas"
          subtitle="Se ordenan desde la aplicación, pero todo corre en GitHub"
          pasos={FLUJO_PRUEBAS}
          nota={NOTA_FLUJO_PRUEBAS}
        />
      </>
    ),
  },
  { id: 'agentes', titulo: 'Los agentes', contenido: <AgenteAyudaComponent /> },
  {
    id: 'tecnologias',
    titulo: 'Tecnologías',
    contenido: (
      <>
        <TarjetaItemsAyudaComponent title="Con qué está hecha la aplicación" subtitle="Tecnologías y para qué se usa cada una" items={TECNOLOGIAS} />
        <TarjetaComponent title="Repositorio de pruebas del Asesor Técnico" subtitle="El código que el Asesor revisa para encontrar el impacto de un cambio">
          <ListaPunto lista={REPOSITORIO_PRUEBAS} />
        </TarjetaComponent>
      </>
    ),
  },
  {
    id: 'construido',
    titulo: 'Cómo está construido',
    contenido: (
      <>
        <TarjetaItemsAyudaComponent
          title="Principios"
          subtitle="Es un prototipo, pero su estructura está pensada para crecer y llegar a producción"
          items={PRINCIPIO_ARQUITECTURA}
        />
        <TarjetaItemsAyudaComponent title="Capas del sistema" subtitle="Cada capa tiene una responsabilidad" items={CAPA_ARQUITECTURA} />
        <TarjetaItemsAyudaComponent
          title="Cómo se hace un cambio"
          subtitle="Los cambios frecuentes se resuelven en un solo lugar"
          items={CAMBIO_ARQUITECTURA}
        />
        <TarjetaComponent title="Pensado para producción" subtitle="Lo que ya está resuelto aunque sea un prototipo">
          <ListaPunto lista={PRODUCCION_ARQUITECTURA} />
        </TarjetaComponent>
        <TarjetaComponent title="Preparado para programar con IA" subtitle="Para que otra persona o herramienta de IA mantenga la estructura y el diseño">
          <ListaPunto lista={IA_ARQUITECTURA} />
        </TarjetaComponent>
      </>
    ),
  },
  {
    id: 'diseno',
    titulo: 'Diseño',
    contenido: (
      <>
        <PaletaComponent />
        <TarjetaItemsAyudaComponent title="Tipografía" subtitle="Dos familias, cargadas desde Google Fonts" items={TIPOGRAFIA_DISENO} />
        <TarjetaItemsAyudaComponent title="Web, tablet y móvil" subtitle="La estructura se adapta sola; las pantallas no hacen nada especial" items={DISPOSITIVO_DISENO} />
      </>
    ),
  },
];

const irAGrupo = (evento, id) => {
  evento.preventDefault();
  document.getElementById(idGrupo(id))?.scrollIntoView({ behavior: 'smooth', block: 'start' });
};

// Todo lo que hace falta para entender el proyecto: cómo funciona, los agentes, las tecnologías, cómo está
// construido y cómo se ve. Un índice arriba lleva a cada grupo.
export const ArquitecturaAyudaComponent = () => (
  <>
    <nav className="ayuda-indice" aria-label="Contenido de Arquitectura">
      <ul className="ayuda-indice__lista">
        {LISTA_GRUPO.map((grupo) => (
          <li key={grupo.id}>
            <a className="ayuda-indice__enlace" href={`#${idGrupo(grupo.id)}`} onClick={(evento) => irAGrupo(evento, grupo.id)}>
              {grupo.titulo}
            </a>
          </li>
        ))}
      </ul>
    </nav>
    {LISTA_GRUPO.map((grupo) => (
      <section key={grupo.id} id={idGrupo(grupo.id)} className="ayuda-grupo" aria-labelledby={`${idGrupo(grupo.id)}-titulo`}>
        <h2 id={`${idGrupo(grupo.id)}-titulo`} className="ayuda-grupo__titulo">{grupo.titulo}</h2>
        {grupo.contenido}
      </section>
    ))}
  </>
);
