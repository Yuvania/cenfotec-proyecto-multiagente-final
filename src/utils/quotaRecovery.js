export const QUOTA_RECOVERY_UNKNOWN = 'Cuota agotada. OpenCode no informó cuándo se restablecerá. Inténtalo nuevamente más tarde.';
export const QUOTA_RECOVERY_ELAPSED = 'Cuota agotada. El tiempo de recuperación informado por OpenCode ya se cumplió. Puedes reintentar manualmente.';

export function quotaRemainingSeconds(retryAt, now = Date.now()) {
  if (typeof retryAt !== 'string'
    || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)$/.test(retryAt)
    || !Number.isFinite(now)) return null;
  const recoveryTime = Date.parse(retryAt);
  if (!Number.isFinite(recoveryTime)) return null;
  const remaining = recoveryTime - now;
  return remaining <= 0 ? 0 : Math.ceil(remaining / 1000);
}

export function formatQuotaDuration(seconds) {
  if (!Number.isFinite(seconds) || seconds <= 0) return null;
  const roundedSeconds = Math.ceil(seconds);
  if (roundedSeconds < 60) {
    return `${roundedSeconds} ${roundedSeconds === 1 ? 'segundo' : 'segundos'}`;
  }
  if (roundedSeconds < 3600) {
    const minutes = Math.ceil(roundedSeconds / 60);
    return `${minutes} ${minutes === 1 ? 'minuto' : 'minutos'}`;
  }

  let hours = Math.floor(roundedSeconds / 3600);
  let minutes = Math.ceil((roundedSeconds % 3600) / 60);
  if (minutes === 60) {
    hours += 1;
    minutes = 0;
  }
  const hourLabel = `${hours} ${hours === 1 ? 'hora' : 'horas'}`;
  return minutes ? `${hourLabel} y ${minutes} ${minutes === 1 ? 'minuto' : 'minutos'}` : hourLabel;
}

// Flujo de agentes: «Se agotó la cuota del modelo. Vuelve a las 3:40 p. m. (en 25 minutos)».
export function quotaRecoveryWorkflowMessage(retryAt, now = Date.now()) {
  const seconds = quotaRemainingSeconds(retryAt, now);
  const guardado = 'El avance quedó guardado.';
  if (seconds === null) return `Se agotó la cuota del modelo y OpenCode no informó cuándo vuelve. ${guardado} Reintente más tarde.`;
  if (seconds === 0) return `Se agotó la cuota del modelo, pero ya debería haber vuelto. ${guardado} Puede reintentar.`;
  const hora = new Date(Date.parse(retryAt)).toLocaleTimeString('es-CR', { hour: 'numeric', minute: '2-digit' });
  return `Se agotó la cuota del modelo. Vuelve a las ${hora} (en ${formatQuotaDuration(seconds)}). ${guardado}`;
}

export function quotaRecoveryMessage(retryAt, now = Date.now()) {
  const seconds = quotaRemainingSeconds(retryAt, now);
  if (seconds === null) return QUOTA_RECOVERY_UNKNOWN;
  if (seconds === 0) return QUOTA_RECOVERY_ELAPSED;
  return `Cuota agotada. OpenCode informó que podrás volver a intentar la consulta dentro de ${formatQuotaDuration(seconds)}.`;
}
