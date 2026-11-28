// Preguntas frecuentes del chat de ayuda. Texto fijo: no usa ningún modelo ni consume cuota.
// Cada respuesta es una lista de párrafos; "pasos" se muestra como lista numerada.
export const BIENVENIDA_AYUDA =
  'Hola, soy el asistente de ayuda. Elija una pregunta y le explico cómo usar el sistema.';

export const PREGUNTAS_AYUDA = [
  {
    id: 'crear',
    pregunta: '¿Cómo creo una historia?',
    texto: 'Para crear una historia de usuario:',
    pasos: [
      'Entre a «Historias de usuario» en el menú y presione «Nueva historia».',
      'Complete el requerimiento: título, tipo de información, sistema, área solicitante y descripción.',
      'Pulse «Analizar Requerimiento» para que el Agente Analista lo revise.',
      'Lleve a Negocio, en una sola ronda, las preguntas del Analista y las decisiones del Asesor Técnico, y registre las respuestas.',
      'Revise la historia (Como / Quiero / Para) y los criterios que redactó el Redactor-Revisor.',
      'El Product Owner la aprueba y queda en el Repositorio de HU.',
    ],
  },
  {
    id: 'codigo',
    pregunta: '¿Qué es el código de la HU?',
    texto:
      'Es el identificador que ve el equipo, con el formato PREFIJO-CODIGO-001 (por ejemplo HU-CODIGO-001). El consecutivo se propone solo al crear la historia. Internamente cada historia también tiene un identificador técnico (GUID) que no se muestra y que no es el código.',
  },
  {
    id: 'analisis',
    pregunta: '¿Qué hace el análisis del requerimiento?',
    texto:
      'El Agente Analista revisa el requerimiento y clasifica la información en conocida, faltante, supuesta y ambigua. Con lo faltante arma preguntas por categoría para llevar a Negocio. Si cambia el título, el tipo de información o la descripción del requerimiento, la historia queda marcada para volver a analizarse.',
  },
  {
    id: 'criterios',
    pregunta: '¿Cómo edito los criterios de aceptación?',
    texto: 'Cada criterio tiene tres partes. Para editarlos:',
    pasos: [
      'Abra la historia y pulse "Editar" (o use el paso de criterios al crearla).',
      'Complete "Dado que", "Cuando" y "Entonces" en cada criterio.',
      'Use "Agregar criterio" para sumar otro o "Quitar" para eliminarlo.',
      'Debe quedar al menos un criterio completo.',
    ],
  },
  {
    id: 'reanalisis',
    pregunta: '¿Cuándo debo volver a analizar?',
    texto:
      'Cuando cambia el requerimiento (título, tipo de información o descripción) el sistema avisa que el análisis quedó desactualizado. Cambiar solo los criterios no obliga a analizar de nuevo: la historia se marca como "Criterios modificados" para que se revise.',
  },
  {
    id: 'editar',
    pregunta: '¿Cómo modifico una historia ya creada?',
    texto:
      'Abra la historia desde la lista y pulse "Editar". La pantalla muestra secciones colapsables; abra la que necesite, haga el cambio y guarde.',
  },
  {
    id: 'aprobar',
    pregunta: '¿Qué pasa cuando el Product Owner aprueba?',
    texto:
      'La historia aprobada se guarda, anonimizada, en el Repositorio de HU. Es la memoria que el agente consulta en análisis futuros para encontrar historias similares.',
  },
  {
    id: 'cambios',
    pregunta: '¿Qué hago si llega un cambio a una HU aprobada?',
    texto:
      'Para corregir redacción o datos mal escritos use Editar: se guarda en el lugar y queda registrado quién y cuándo. Si Negocio pide algo distinto, use Solicitar cambio (ícono de acciones del listado, en historias aprobadas): se vuelve a analizar y, si faltó una pregunta, se propone una lección aprendida (LEC-001, LEC-002…) para análisis futuros.',
  },
  {
    id: 'retomar',
    pregunta: '¿Puedo dejar una historia a medias y seguir otro día?',
    texto:
      'Sí. Cada vez que el flujo espera una respuesta, el avance se guarda. Vaya a Historias de Usuario: arriba, en «En proceso», pulse Retomar y se abre en el paso donde quedó. En las preguntas puede usar «Guardar sin enviar» para dejar respuestas a medias.',
  },
  {
    id: 'impacto',
    pregunta: '¿Qué es el impacto en otros módulos?',
    texto:
      'El Asesor Técnico revisa el código del sistema justo después del primer análisis del Analista y explica, sin detalle técnico, qué otras funciones afecta el cambio (por ejemplo, una carga masiva o un reporte). Se muestra en el paso 3, junto con las decisiones que Negocio debe tomar, en la misma ronda que las preguntas del Analista. La historia se redacta después, ya con esos impactos como criterios.',
  },
  {
    id: 'datos',
    pregunta: '¿Puedo usar datos reales del negocio?',
    texto:
      'No. Las fuentes de los agentes y el código que revisa el Asesor Técnico son de ejemplo o anonimizados. Anonimice cualquier dato personal antes de escribirlo.',
  },
  {
    id: 'guardado',
    pregunta: '¿Dónde se guardan las historias?',
    texto:
      'En la base de datos del sistema, por lo que las ve todo el equipo desde cualquier navegador. El navegador solo guarda una copia temporal para mostrarlas más rápido.',
  },
  {
    id: 'arquitectura',
    pregunta: '¿Cómo está construido el sistema?',
    texto:
      'Por capas (interfaz, API, orquestación, agentes, herramientas y datos) y con registros: cada agente es una carpeta con su definición, y las pantallas salen de un registro único. Así, agregar un agente o una pantalla se hace en un solo lugar. El detalle está en Ayuda → Arquitectura.',
  },
  {
    id: 'funcionamiento',
    pregunta: '¿Cómo trabajan los agentes por dentro?',
    texto: 'Cada uno de los 4 agentes tiene su propio servidor MCP. En pocas palabras:',
    pasos: [
      'La aplicación envía el requerimiento y LangGraph decide qué agente actúa.',
      'El agente se conecta a su MCP: las herramientas le dicen qué busca cada una y en qué espacio de Pinecone.',
      'El MCP busca en Pinecone (glosario, estándares, checklist, HU aprobadas, lecciones o código) y devuelve los resultados.',
      'El agente se los pasa a OpenCode, que con el modelo escribe la respuesta.',
      'LangGraph pasa el resultado al siguiente agente y, al final, regresa a la aplicación.',
    ],
  },
  {
    id: 'pruebas',
    pregunta: '¿Cómo funcionan las pruebas automatizadas?',
    texto: 'Se ordenan desde la aplicación, pero todo corre en GitHub:',
    pasos: [
      'En Mantenimiento › Pruebas automatizadas elige qué probar y presiona Ejecutar pruebas.',
      'La aplicación se conecta a GitHub con un token y arranca las pruebas.',
      'GitHub levanta la aplicación con Docker y Playwright la recorre en web, tablet y móvil.',
      'Si algo falla, el Agente de Pruebas lo revisa con un navegador por Playwright MCP y explica por qué.',
      'El tablero muestra el resultado; las evidencias quedan en GitHub. El detalle está en Ayuda → Arquitectura.',
    ],
  },
  {
    id: 'consumo',
    pregunta: '¿Cuánto cuesta crear una historia?',
    texto:
      'Cada respuesta del modelo guarda sus tokens y su costo, asociados a la historia y al agente. En Mantenimiento › Métricas › Consumo del modelo se ve el costo promedio por historia creada y por cambio, por agente y por día; en el detalle de una historia, la pestaña «Consumo del modelo» muestra lo que costó esa historia. Hace falta la acción «Ver el consumo del modelo».',
  },
  {
    id: 'segundo-plano',
    pregunta: '¿Puedo salir mientras trabajan los agentes?',
    texto:
      'Sí. Los agentes trabajan en segundo plano: la pantalla muestra en vivo qué agente trabaja, qué consulta y si reintenta, pero puede salir con «Ir a mis historias». En Historias de usuario → En proceso la verá como «Los agentes están trabajando ahora», y cuando terminen le llegará «Lista para continuar» en Notificaciones.',
  },
  {
    id: 'fallo',
    pregunta: '¿Qué pasa si falla un agente?',
    texto: 'El avance nunca se pierde. Así se maneja:',
    pasos: [
      'Si el fallo es pasajero (tardó demasiado o el proveedor no respondió), se reintenta solo hasta 3 veces.',
      'Si se agotó la cuota del modelo, la pantalla dice a qué hora vuelve.',
      'Si aun así no termina, a quien creó la historia le llega en Notificaciones «Falló un agente», con el motivo.',
      'Desde esa notificación, o desde Historias de usuario → En proceso, use Retomar para volver a intentarlo.',
    ],
  },
  {
    id: 'pendientes',
    pregunta: '¿Dónde veo lo que tengo por aprobar?',
    texto:
      'En Notificaciones, en el menú (en el móvil, «Avisos»): el número indica cuántas cosas esperan su decisión o avisos tiene sin leer. Es una sola lista y cada notificación lleva su categoría (Por aprobar, Cambio por decidir, Devuelta, Rechazada o Aprobada); arriba puede filtrar por categoría o por «Requieren acción».',
  },
  {
    id: 'mantenimiento',
    pregunta: '¿Cómo doy permisos a una persona?',
    texto:
      'En Mantenimiento (solo para administradores). En Usuarios se busca a la persona y se le marcan sus roles; en Roles se elige un rol y se marcan sus acciones, por ejemplo Aprobar historia. El cambio aplica de inmediato. Solo quien tenga la acción de aprobar ve la opción Aprobar en el paso 5.',
  },
];

// Preguntas que se ofrecen como botones al abrir el chat.
export const SUGERENCIA_INICIAL = ['crear', 'retomar', 'impacto', 'codigo'];

export const TEXTO_SIN_COINCIDENCIA =
  'No tengo una respuesta fija para eso. Este asistente solo responde las preguntas de la lista; elija una de ellas.';

const normalizar = (valor) =>
  String(valor || '')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase();

// Búsqueda simple por palabras para el cuadro de texto: no interpreta preguntas abiertas.
export const buscarPregunta = (consulta) => {
  const palabras = normalizar(consulta)
    .split(/[^a-z0-9]+/)
    .filter((palabra) => palabra.length > 3);
  if (!palabras.length) return null;
  let mejor = null;
  let puntaje = 0;
  PREGUNTAS_AYUDA.forEach((item) => {
    const enPregunta = normalizar(item.pregunta);
    const enRespuesta = normalizar(`${item.texto} ${(item.pasos || []).join(' ')}`);
    // La coincidencia con la pregunta pesa más que la coincidencia con el texto de la respuesta.
    const total = palabras.reduce(
      (suma, palabra) => suma + (enPregunta.includes(palabra) ? 3 : 0) + (enRespuesta.includes(palabra) ? 1 : 0),
      0,
    );
    if (total > puntaje) {
      puntaje = total;
      mejor = item;
    }
  });
  return mejor;
};
