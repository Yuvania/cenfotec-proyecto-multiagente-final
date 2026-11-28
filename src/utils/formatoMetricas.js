// Formato de las métricas del modelo: costos en dólares y tokens, en español de Costa Rica.
const formatoEntero = new Intl.NumberFormat('es-CR', { maximumFractionDigits: 0 });

// Los costos por llamada son de fracciones de centavo: se muestran con los decimales que hagan falta.
export const formatoCosto = (valor) => {
  const numero = Number(valor) || 0;
  if (numero === 0) return 'US$0';
  if (numero < 0.0001) return 'menos de US$0,0001';
  const decimales = numero < 0.01 ? 4 : numero < 1 ? 3 : 2;
  const texto = new Intl.NumberFormat('es-CR', { minimumFractionDigits: decimales, maximumFractionDigits: decimales }).format(numero);
  return `US$${texto}`;
};

export const formatoToken = (valor) => formatoEntero.format(Math.round(Number(valor) || 0));

// 12 345 678 → «12,3 M»; 45 600 → «45,6 mil». Para indicadores donde el número completo no cabe.
export const formatoTokenCorto = (valor) => {
  const numero = Number(valor) || 0;
  const uno = new Intl.NumberFormat('es-CR', { maximumFractionDigits: 1 });
  if (numero >= 1_000_000) return `${uno.format(numero / 1_000_000)} M`;
  if (numero >= 10_000) return `${uno.format(numero / 1_000)} mil`;
  return formatoToken(numero);
};

export const porcentaje = (parte, total) => (total > 0 ? Math.round((100 * parte) / total) : 0);

export const NOMBRE_MODO = Object.freeze({
  creacion: 'Creación',
  cambio: 'Cambio',
  prueba: 'Diagnóstico de pruebas',
  otro: 'Otro',
});

// «2026-11-28» → «28 nov».
export const diaCorto = (dia) => {
  const fecha = new Date(`${dia}T12:00:00Z`);
  return Number.isNaN(fecha.getTime()) ? dia : fecha.toLocaleDateString('es-CR', { day: 'numeric', month: 'short', timeZone: 'UTC' });
};
