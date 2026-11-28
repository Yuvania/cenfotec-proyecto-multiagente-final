import React, { useEffect, useState } from 'react';
import { CheckCircle2, Circle, Loader2, XCircle } from 'lucide-react';
import { BotonComponent } from '../../Comun/BotonComponent';
import { duracionCorta, resumirAvance } from '../../../utils/formatoAvance';

const ICONO = Object.freeze({ trabajando: Loader2, listo: CheckCircle2, fallo: XCircle });
const TEXTO_ESTADO = Object.freeze({ trabajando: 'trabajando', listo: 'terminó', fallo: 'no pudo terminar' });

// Avance en vivo de los agentes en segundo plano: qué agente trabaja, qué consulta, si reintenta y cuánto lleva.
// La persona puede salir de la pantalla: los agentes siguen y le llega un aviso cuando esté lista.
export const AvanceAgentesComponent = ({ eventos, onSalir }) => {
  const [ahora, setAhora] = useState(() => Date.now());
  const { enCola, iniciado, filas } = resumirAvance(eventos, ahora);
  const trabajando = filas.some((fila) => fila.estado === 'trabajando');

  useEffect(() => {
    if (!trabajando) return undefined;
    const intervalo = window.setInterval(() => setAhora(Date.now()), 1000);
    return () => window.clearInterval(intervalo);
  }, [trabajando]);

  return (
    <section className="avance-agentes" aria-label="Avance de los agentes">
      {enCola && (
        <p className="avance-agentes__cola">
          En cola: {enCola === 1 ? 'hay 1 historia antes que esta' : `hay ${enCola} historias antes que esta`}. Empieza en cuanto se libere un lugar.
        </p>
      )}
      {!enCola && !iniciado && filas.length === 0 && <p className="avance-agentes__cola">Recibido. Los agentes empiezan en un momento…</p>}
      <ol className="avance-agentes__lista">
        {filas.map((fila) => {
          const Icono = ICONO[fila.estado] ?? Circle;
          return (
            <li key={`${fila.agente}-${fila.desde}`} className={`avance-agentes__fila avance-agentes__fila--${fila.estado}`}>
              <Icono size={18} aria-hidden="true" className={fila.estado === 'trabajando' ? 'avance-agentes__girando' : ''} />
              <div className="avance-agentes__texto">
                <p className="avance-agentes__nombre">
                  {fila.nombre}
                  <span className="sr-only">: {TEXTO_ESTADO[fila.estado]}</span>
                  <span className="avance-agentes__tiempo">{duracionCorta(fila.duracionMs)}</span>
                </p>
                {fila.fuentes && fila.estado === 'trabajando' && <p className="avance-agentes__detalle">Consulta {fila.fuentes}.</p>}
                {fila.reintento && (
                  <p className="avance-agentes__reintento" role="status">
                    {fila.reintento.texto} Reintento en {fila.reintento.espera} s (intento {fila.reintento.intento + 1} de {fila.reintento.de + 1}).
                  </p>
                )}
              </div>
            </li>
          );
        })}
      </ol>
      <div className="avance-agentes__pie">
        <p>Puede salir de esta pantalla: los agentes siguen trabajando y le llegará un aviso en Notificaciones cuando esté lista.</p>
        {onSalir && <BotonComponent variant="secondary" size="sm" onClick={onSalir}>Ir a mis historias</BotonComponent>}
      </div>
    </section>
  );
};
