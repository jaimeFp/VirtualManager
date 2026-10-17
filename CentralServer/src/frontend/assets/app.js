const REFRESH_MS = 5000;
const tokenDialog = document.querySelector("#token-dialog");
const actionDialog = document.querySelector("#action-dialog");
const tokenForm = document.querySelector("#token-form");
const toastRegion = document.querySelector("#toast-region");
const stateLabels = { running: "Encendida", paused: "Pausada", poweroff: "Apagada", saved: "Guardada", aborted: "Interrumpida" };
const actionLabels = { start: "Iniciar", pause: "Pausar", resume: "Reanudar", shutdown: "Apagar", poweroff: "Forzar apagado" };
let token = sessionStorage.getItem("vm_api_token") || "";
let agents = [];
let machines = [];
let commands = [];
let selectedAction = null;
let lastError = "";

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, character => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character]);
}

function notify(message, type = "") {
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.textContent = message;
  toastRegion.append(toast);
  setTimeout(() => toast.remove(), 4200);
}

function online(agent) {
  const seen = Date.parse(agent.last_seen || "");
  return Number.isFinite(seen) && Date.now() - seen < 30000;
}

function relativeTime(value) {
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

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Authorization": `Bearer ${token}`, "Content-Type": "application/json", ...options.headers },
  });
  if (response.status === 401) {
    token = "";
    sessionStorage.removeItem("vm_api_token");
    if (!tokenDialog.open) tokenDialog.showModal();
    throw new Error("Credencial no válida. Introduce de nuevo el token de acceso.");
  }
  if (!response.ok) {
    let detail = `Error ${response.status}`;
    try { detail = (await response.json()).detail || detail; } catch { /* Respuesta sin JSON. */ }
    throw new Error(detail);
  }
  return response.json();
}

function stateClass(state) {
  if (state === "running") return "status-running";
  if (state === "paused") return "status-paused";
  if (state === "poweroff") return "status-poweroff";
  return "status-other";
}

function actionButtons(machine) {
  const actions = machine.state === "running"
    ? [["pause", "Pausar"], ["shutdown", "Apagar"], ["poweroff", "Forzar", true]]
    : machine.state === "paused"
      ? [["resume", "Reanudar"], ["poweroff", "Forzar", true]]
      : ["poweroff", "saved", "aborted"].includes(machine.state)
        ? [["start", "Iniciar"]]
        : [];
  return `<div class="row-actions">${actions.map(([action, label, danger]) => `<button class="action-button ${danger ? "danger" : ""}" data-action="${action}" data-agent="${escapeHtml(machine.agent_id)}" data-vm="${escapeHtml(machine.uuid)}">${label}</button>`).join("") || "<span class=\"date-cell\">—</span>"}</div>`;
}

function renderMachines() {
  const query = document.querySelector("#machine-search").value.trim().toLocaleLowerCase("es");
  const filter = document.querySelector("#state-filter").value;
  const shown = machines.filter(machine => {
    const matchesQuery = `${machine.name} ${machine.agent_name} ${machine.uuid}`.toLocaleLowerCase("es").includes(query);
    const matchesState = filter === "all" || (filter === "other" ? !["running", "paused", "poweroff"].includes(machine.state) : machine.state === filter);
    return matchesQuery && matchesState;
  });
  document.querySelector("#machine-count").textContent = `${shown.length} ${shown.length === 1 ? "máquina" : "máquinas"}`;
  const body = document.querySelector("#machines-body");
  if (!shown.length) {
    body.innerHTML = `<tr><td colspan="5" class="empty-cell">${machines.length ? "No hay máquinas que coincidan con el filtro." : "No se han detectado máquinas virtuales."}</td></tr>`;
    return;
  }
  body.innerHTML = shown.map(machine => `<tr>
    <td><div class="machine-name"><span class="vm-glyph">▤</span><span><strong title="${escapeHtml(machine.name)}">${escapeHtml(machine.name)}</strong><small>${escapeHtml(machine.uuid)}</small></span></div></td>
    <td><span class="agent-chip"><i class="${machine.agent_online ? "" : "offline"}"></i>${escapeHtml(machine.agent_name)}</span></td>
    <td><span class="status-badge ${stateClass(machine.state)}"><i></i>${escapeHtml(stateLabels[machine.state] || machine.state || "Desconocido")}</span></td>
    <td class="date-cell">${relativeTime(machine.last_seen)}</td>
    <td>${actionButtons(machine)}</td>
  </tr>`).join("");
}

function renderAgents() {
  document.querySelector("#agent-count").textContent = agents.length;
  const onlineCount = agents.filter(online).length;
  document.querySelector("#stat-agents").textContent = agents.length;
  document.querySelector("#stat-online").textContent = onlineCount;
  document.querySelector("#stat-agents-foot").textContent = agents.length ? `${onlineCount} conectados ahora` : "Sin agentes registrados";
  const list = document.querySelector("#agent-list");
  if (!agents.length) {
    list.innerHTML = '<div class="empty-agents">Aún no hay agentes registrados. Cuando un agente se conecte, aparecerá aquí.</div>';
    return;
  }
  list.innerHTML = agents.map(agent => {
    const count = (agent.vms || []).length;
    const platform = `${agent.platform || "Sistema"}${agent.version ? ` · v${agent.version}` : ""}`;
    return `<div class="agent-row"><span class="agent-icon">⌘</span><span class="agent-name"><strong title="${escapeHtml(agent.hostname)}">${escapeHtml(agent.hostname)}</strong><small>${escapeHtml(platform)}</small><span class="agent-vms">${count} ${count === 1 ? "máquina" : "máquinas"} · ${relativeTime(agent.last_seen)}</span></span><i class="agent-health ${online(agent) ? "" : "offline"}" title="${online(agent) ? "Conectado" : "Sin actividad reciente"}"></i></div>`;
  }).join("");
}

function renderCommands() {
  const body = document.querySelector("#commands-body");
  const recent = commands.slice(0, 20);
  if (!recent.length) {
    body.innerHTML = '<tr><td colspan="5" class="empty-cell">Todavía no hay órdenes. Usa los controles de una máquina para enviar la primera.</td></tr>';
    return;
  }
  body.innerHTML = recent.map(command => {
    const statusClass = { pending: "command-pending", running: "command-running", success: "command-success", failed: "command-failed" }[command.status] || "command-pending";
    const statusLabel = { pending: "Pendiente", running: "En curso", success: "Completada", failed: "Fallida" }[command.status] || command.status;
    const machine = machines.find(item => item.uuid === command.vm_uuid && item.agent_id === command.agent_id);
    return `<tr title="${escapeHtml(command.error || "")}"><td class="action-label">${escapeHtml(actionLabels[command.action] || command.action)}</td><td>${escapeHtml(machine?.name || command.vm_uuid)}</td><td>${escapeHtml(machine?.agent_name || command.agent_id.slice(0, 8))}</td><td><span class="command-badge ${statusClass}">${statusLabel}</span></td><td class="date-cell">${relativeTime(command.created_at)}</td></tr>`;
  }).join("");
}

function render() {
  const running = machines.filter(machine => machine.state === "running").length;
  const outstanding = commands.filter(command => ["pending", "running"].includes(command.status)).length;
  document.querySelector("#stat-vms").textContent = machines.length;
  document.querySelector("#stat-running").textContent = running;
  document.querySelector("#stat-commands").textContent = outstanding;
  renderMachines();
  renderAgents();
  renderCommands();
}

async function refresh() {
  if (!token) {
    if (!tokenDialog.open) tokenDialog.showModal();
    document.querySelector("#connection-label").textContent = "Credencial requerida";
    return;
  }
  const refreshButton = document.querySelector("#refresh-button");
  refreshButton.classList.add("spinning");
  try {
    const [agentData, commandData] = await Promise.all([api("/api/v1/agents"), api("/api/v1/commands")]);
    agents = agentData;
    commands = commandData;
    machines = agents.flatMap(agent => (agent.vms || []).map(vm => ({
      ...vm,
      agent_id: agent.agent_id,
      agent_name: agent.hostname,
      agent_online: online(agent),
      last_seen: agent.last_seen,
    })));
    render();
    document.querySelector("#connection-label").textContent = "Conectado y sincronizado";
    document.querySelector(".connection-dot").classList.add("online");
    document.querySelector("#updated-label").textContent = `Actualizado ${new Intl.DateTimeFormat("es-ES", { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(new Date())}`;
    lastError = "";
  } catch (error) {
    document.querySelector("#connection-label").textContent = "Error de conexión";
    document.querySelector(".connection-dot").classList.remove("online");
    if (error.message !== lastError) notify(error.message, "error");
    lastError = error.message;
  } finally {
    refreshButton.classList.remove("spinning");
  }
}

function openAction(machine, action) {
  selectedAction = { machine, action };
  const destructive = action === "poweroff";
  document.querySelector("#action-title").textContent = actionLabels[action];
  document.querySelector("#action-description").textContent = destructive
    ? "El apagado forzado puede causar pérdida de datos en la máquina virtual. ¿Quieres continuar?"
    : `Se enviará la orden al agente ${machine.agent_name}.`;
  document.querySelector("#action-vm-name").textContent = machine.name;
  document.querySelector("#action-vm-agent").textContent = `${machine.agent_name} · ${machine.uuid}`;
  document.querySelector("#confirm-action").innerHTML = `${destructive ? "Forzar apagado" : "Enviar orden"} <span>→</span>`;
  document.querySelector("#confirm-action").classList.toggle("danger-button", destructive);
  actionDialog.showModal();
}

document.querySelector("#machines-body").addEventListener("click", event => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const machine = machines.find(item => item.uuid === button.dataset.vm && item.agent_id === button.dataset.agent);
  if (machine) openAction(machine, button.dataset.action);
});

document.querySelector("#confirm-action").addEventListener("click", async () => {
  if (!selectedAction) return;
  const button = document.querySelector("#confirm-action");
  actionDialog.classList.add("busy");
  button.textContent = "Enviando…";
  try {
    await api("/api/v1/commands", {
      method: "POST",
      body: JSON.stringify({ agent_id: selectedAction.machine.agent_id, vm_uuid: selectedAction.machine.uuid, action: selectedAction.action }),
    });
    actionDialog.close();
    notify(`Orden «${actionLabels[selectedAction.action]}» enviada a ${selectedAction.machine.name}.`);
    selectedAction = null;
    await refresh();
  } catch (error) {
    notify(error.message, "error");
  } finally {
    actionDialog.classList.remove("busy");
    button.innerHTML = "Enviar orden <span>→</span>";
  }
});

document.querySelector("#token-button").addEventListener("click", () => {
  document.querySelector("#token-input").value = token;
  tokenDialog.showModal();
});
document.querySelector("#settings-button").addEventListener("click", () => document.querySelector("#token-button").click());
document.querySelector("#cancel-token").addEventListener("click", () => tokenDialog.close());
document.querySelector("#cancel-action").addEventListener("click", () => actionDialog.close());
document.querySelector("#refresh-button").addEventListener("click", refresh);
document.querySelector("#machine-search").addEventListener("input", renderMachines);
document.querySelector("#state-filter").addEventListener("change", renderMachines);
document.querySelector("#show-machines").addEventListener("click", () => document.querySelector("#machine-search").focus());
tokenForm.addEventListener("submit", event => {
  event.preventDefault();
  token = document.querySelector("#token-input").value.trim();
  sessionStorage.setItem("vm_api_token", token);
  tokenDialog.close();
  lastError = "";
  refresh();
});

if (!token) tokenDialog.showModal();
refresh();
setInterval(refresh, REFRESH_MS);
