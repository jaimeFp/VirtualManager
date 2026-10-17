export const stateLabels = { running: "Encendida", paused: "Pausada", poweroff: "Apagada", saved: "Guardada", aborted: "Interrumpida" };
export const roleLabels = { admin: "Administrador", operator: "Operador", observer: "Observador" };
export const actionLabels = { start: "Iniciar", pause: "Pausar", resume: "Reanudar", shutdown: "Apagar", poweroff: "Forzar apagado", configure: "Configurar recursos" };
export const networkModeLabels = { none: "No instalada", null: "Desconectada", nat: "NAT", natnetwork: "Red NAT", bridged: "Adaptador puente", intnet: "Red interna", hostonly: "Solo anfitrión", generic: "Genérico" };

export function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, character => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character]);
}

export function online(agent) {
  const seen = Date.parse(agent.last_seen || "");
  return Number.isFinite(seen) && Date.now() - seen < 30000;
}

export function relativeTime(value) {
  const time = Date.parse(value || "");
  if (!Number.isFinite(time)) return "—";
  const seconds = Math.max(0, Math.floor((Date.now() - time) / 1000));
  if (seconds < 10) return "Ahora";
  if (seconds < 60) return `Hace ${seconds} s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `Hace ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `Hace ${hours} h`;
  return new Intl.DateTimeFormat("es-ES", { day: "2-digit", month: "short" }).format(time);
}

export function stateClass(state) {
  if (state === "running") return "status-running";
  if (state === "paused") return "status-paused";
  if (state === "poweroff") return "status-poweroff";
  return "status-other";
}
