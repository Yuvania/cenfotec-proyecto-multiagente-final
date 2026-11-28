import React from 'react';
import { TarjetaComponent } from '../Comun/TarjetaComponent';

// Recorrido paso a paso: cada paso dice qué pieza actúa («quien») y qué hace. Debajo, notas opcionales.
// pasos: [{ quien, texto }] · nota: [texto]
export const FlujoAyudaComponent = ({ title, subtitle, pasos, nota = [] }) => (
  <TarjetaComponent title={title} subtitle={subtitle}>
    <ol className="ayuda-flujo">
      {pasos.map((paso, indice) => (
        <li key={`${indice}-${paso.quien}`} className="ayuda-flujo__paso">
          <span className="ayuda-flujo__numero" aria-hidden="true">{indice + 1}</span>
          <div className="ayuda-flujo__cuerpo">
            <p className="ayuda-flujo__quien">{paso.quien}</p>
            <p className="ayuda-item__texto">{paso.texto}</p>
          </div>
        </li>
      ))}
    </ol>
    {nota.length > 0 && (
      <ul className="ayuda-item__puntos ayuda-flujo__nota">
        {nota.map((texto) => <li key={texto}>{texto}</li>)}
      </ul>
    )}
  </TarjetaComponent>
);
