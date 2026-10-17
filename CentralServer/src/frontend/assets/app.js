const REFRESH_MS = 5000;
const tokenDialog = document.querySelector("#token-dialog");
const actionDialog = document.querySelector("#action-dialog");
const vmDetailDialog = document.querySelector("#vm-detail-dialog");
const tokenForm = document.querySelector("#token-form");
const toastRegion = document.querySelector("#toast-region");
const stateLabels = { running: "Encendida", paused: "Pausada", poweroff: "Apagada", saved: "Guardada", aborted: "Interrumpida" };
const actionLabels = { start: "Iniciar", pause: "Pausar", resume: "Reanudar", shutdown: "Apagar", poweroff: "Forzar apagado" };
let token = sessionStorage.getItem("vm_api_token") || "";
let selectedAgentId = sessionStorage.getItem("vm_selected_agent") || "";
let agents = [];
let machines = [];
let commands = [];
let selectedAction = null;
let lastError = "";
let previousCommandStates = new Map();
let refreshing = false;

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

function heartbeatLabel(agent) {
  return online(agent) ? "Conectado" : `Sin señal · ${relativeTime(agent.last_seen)}`;
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

function availableActions(machine) {
  return machine.state === "running"
    ? [["pause", "Pausar"], ["shutdown", "Apagar"], ["poweroff", "Forzar", true]]
    : machine.state === "paused"
      ? [["resume", "Reanudar"], ["poweroff", "Forzar", true]]
      : ["poweroff", "saved", "aborted"].includes(machine.state)
        ? [["start", "Iniciar"]]
        : [];
}

function actionButtons(machine) {
  const actions = availableActions(machine);
  return `<div class="row-actions">${actions.map(([action, label, danger]) => `<button class="action-button ${danger ? "danger" : ""}" data-action="${action}" data-agent="${escapeHtml(machine.agent_id)}" data-vm="${escapeHtml(machine.uuid)}" ${machine.agent_online ? "" : "disabled title=\"El agente no tiene conexión reciente\""}>${label}</button>`).join("") || "<span class=\"date-cell\">—</span>"}</div>`;
}

function renderMachines() {
  const query = document.querySelector("#machine-search").value.trim().toLocaleLowerCase("es");
  const filter = document.querySelector("#state-filter").value;
  const sortBy = document.querySelector("#machine-sort").value;
  const agent = agents.find(item => item.agent_id === selectedAgentId);
  document.querySelector("#machine-panel-title").textContent = agent ? `Máquinas de ${agent.hostname}` : "Máquinas virtuales";
  const status = document.querySelector("#selected-agent-status");
  if (!agent) {
    status.className = "selected-agent-status";
    status.innerHTML = "<i></i><span>Selecciona un agente para empezar</span>";
    document.querySelector("#inventory-health").innerHTML = "<i></i> Esperando selección";
    document.querySelector("#machine-count").textContent = "Selecciona un agente";
    document.querySelector("#machines-body").innerHTML = '<tr><td colspan="5" class="empty-cell">Selecciona un agente para mostrar sus máquinas virtuales.</td></tr>';
    return;
  }
  const isOnline = online(agent);
  status.className = `selected-agent-status ${isOnline ? "is-online" : "is-stale"}`;
  status.innerHTML = `<i></i><span>${isOnline ? "Conectado" : "Sin señal reciente"} · última señal ${relativeTime(agent.last_seen)}</span>`;
  let shown = machines.filter(machine => {
    if (machine.agent_id !== selectedAgentId) return false;
    const matchesQuery = `${machine.name} ${machine.uuid}`.toLocaleLowerCase("es").includes(query);
    const matchesState = filter === "all" || (filter === "other" ? !["running", "paused", "poweroff"].includes(machine.state) : machine.state === filter);
    return matchesQuery && matchesState;
  });
  const collator = new Intl.Collator("es", { sensitivity: "base", numeric: true });
  const compareMachines = (left, right) => {
    if (sortBy === "state") return collator.compare(stateLabels[left.state] || left.state, stateLabels[right.state] || right.state) || collator.compare(left.name, right.name);
    return collator.compare(left.name, right.name);
  };
  shown.sort(compareMachines);
  document.querySelector("#machine-count").textContent = `${shown.length} ${shown.length === 1 ? "máquina" : "máquinas"}`;
  document.querySelector("#inventory-health").innerHTML = `<i class="${isOnline ? "" : "stale-pulse"}"></i>${isOnline ? "Inventario actualizado" : "Inventario desactualizado"}`;
  const body = document.querySelector("#machines-body");
  if (!shown.length) {
    const hasMachines = machines.some(machine => machine.agent_id === selectedAgentId);
    body.innerHTML = `<tr><td colspan="5" class="empty-cell">${hasMachines ? "No hay máquinas que coincidan con el filtro." : "Este agente todavía no tiene máquinas virtuales."}</td></tr>`;
    return;
  }
  body.innerHTML = shown.map(machine => `<tr>
      <td><div class="machine-name"><span class="vm-glyph">▤</span><span><button class="vm-name-button" data-vm-detail="${escapeHtml(machine.uuid)}" data-agent="${escapeHtml(machine.agent_id)}" title="Ver detalle de ${escapeHtml(machine.name)}">${escapeHtml(machine.name)}</button><small>${escapeHtml(machine.uuid)}</small></span></div></td>
      <td><span class="agent-chip"><i class="${machine.agent_online ? "" : "offline"}"></i>${escapeHtml(machine.agent_name)}${machine.agent_online ? "" : " · sin señal"}</span></td>
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
  document.querySelector("#stat-online-foot").textContent = agents.length - onlineCount ? `${agents.length - onlineCount} sin señal reciente` : "Todos con señal reciente";
  document.querySelector("#agent-health-summary").textContent = agents.length - onlineCount
    ? `${onlineCount} conectados · ${agents.length - onlineCount} sin señal`
    : agents.length ? "Todos los agentes responden" : "Esperando primer agente";
  const list = document.querySelector("#agent-list");
  if (!agents.length) {
    list.innerHTML = '<div class="empty-agents">Aún no hay agentes registrados. Cuando un agente se conecte, aparecerá aquí.</div>';
    return;
  }
  list.innerHTML = agents.map(agent => {
    const count = (agent.vms || []).length;
    const platform = `${agent.platform || "Sistema"}${agent.version ? ` · v${agent.version}` : ""}`;
    return `<div class="agent-row ${online(agent) ? "" : "agent-stale"}"><span class="agent-icon">⌘</span><span class="agent-name"><strong title="${escapeHtml(agent.hostname)}">${escapeHtml(agent.hostname)}</strong><small>${escapeHtml(platform)}</small><span class="agent-vms">${count} ${count === 1 ? "máquina" : "máquinas"} · ${heartbeatLabel(agent)}</span></span><i class="agent-health ${online(agent) ? "" : "offline"}" title="${online(agent) ? "Conectado" : "Sin actividad reciente"}"></i><button class="agent-open-button" data-open-agent="${escapeHtml(agent.agent_id)}" title="Ver máquinas de ${escapeHtml(agent.hostname)}">Ver máquinas <span>→</span></button></div>`;
  }).join("");
}

function renderAgentSelector() {
  const selector = document.querySelector("#agent-selector");
  const selectedExists = agents.some(agent => agent.agent_id === selectedAgentId);
  if (!selectedExists) {
    selectedAgentId = "";
    sessionStorage.removeItem("vm_selected_agent");
  }
  const signature = agents.map(agent => `${agent.agent_id}:${agent.hostname}:${(agent.vms || []).length}:${online(agent)}`).join("|");
  if (selector.dataset.signature !== signature) {
    selector.innerHTML = `<option value="">Selecciona un agente</option>${agents.map(agent => {
    const count = (agent.vms || []).length;
    const connection = online(agent) ? "Conectado" : "Sin señal";
    return `<option value="${escapeHtml(agent.agent_id)}">${escapeHtml(agent.hostname)} · ${count} VM · ${connection}</option>`;
    }).join("")}`;
    selector.dataset.signature = signature;
  }
  if (selector.value !== selectedAgentId) selector.value = selectedAgentId;
}

function renderCommands() {
  const body = document.querySelector("#commands-body");
  const recent = commands.slice(0, 20);
  const pendingCount = commands.filter(command => command.status === "pending").length;
  const runningCount = commands.filter(command => command.status === "running").length;
  document.querySelector("#command-summary").textContent = `${pendingCount} pendientes · ${runningCount} en curso · últimas 20`;
  if (!recent.length) {
    body.innerHTML = '<tr><td colspan="5" class="empty-cell">Todavía no hay órdenes. Usa los controles de una máquina para enviar la primera.</td></tr>';
    return;
  }
  body.innerHTML = recent.map(command => {
    const statusClass = { pending: "command-pending", running: "command-running", success: "command-success", failed: "command-failed" }[command.status] || "command-pending";
    const statusLabel = { pending: "Pendiente", running: "En curso", success: "Completada", failed: "Fallida" }[command.status] || command.status;
    const machine = machines.find(item => item.uuid === command.vm_uuid && item.agent_id === command.agent_id);
    const row = `<tr><td class="action-label">${escapeHtml(actionLabels[command.action] || command.action)}</td><td>${escapeHtml(machine?.name || command.vm_uuid)}</td><td>${escapeHtml(machine?.agent_name || command.agent_id.slice(0, 8))}</td><td><span class="command-badge ${statusClass}">${statusLabel}</span></td><td class="date-cell">${relativeTime(command.completed_at || command.started_at || command.created_at)}</td></tr>`;
    const errorRow = command.status === "failed" && command.error
      ? `<tr class="command-error-row"><td colspan="5"><span class="error-symbol">!</span><strong>Error de ejecución:</strong> ${escapeHtml(command.error)}</td></tr>`
      : "";
    return row + errorRow;
  }).join("");
}

function render() {
  const running = machines.filter(machine => machine.state === "running").length;
  const outstanding = commands.filter(command => ["pending", "running"].includes(command.status)).length;
  document.querySelector("#stat-vms").textContent = machines.length;
  document.querySelector("#stat-running").textContent = running;
  document.querySelector("#stat-commands").textContent = outstanding;
  renderAgentSelector();
  renderMachines();
  renderAgents();
  renderCommands();
}

function updateView() {
  const hash = window.location.hash;
  const view = hash === "#maquinas" ? "machines" : hash === "#ordenes" ? "orders" : "dashboard";
  const isMachines = view === "machines";
  document.querySelector("#dashboard-screen").classList.toggle("hidden-screen", isMachines);
  document.querySelector("#machines-screen").classList.toggle("hidden-screen", !isMachines);
  document.querySelectorAll(".nav-link[data-view]").forEach(link => {
    link.classList.toggle("selected", link.dataset.view === view);
  });
  document.querySelector("#breadcrumb-current").textContent = view === "machines" ? "Máquinas virtuales" : view === "orders" ? "Órdenes" : "Resumen";
  if (view === "orders") requestAnimationFrame(() => document.querySelector("#ordenes").scrollIntoView({ behavior: "smooth", block: "start" }));
  if (isMachines) renderMachines();
}

async function refresh() {
  if (refreshing) return;
  if (!token) {
    if (!tokenDialog.open) tokenDialog.showModal();
    document.querySelector("#connection-label").textContent = "Credencial requerida";
    return;
  }
  refreshing = true;
  const refreshButton = document.querySelector("#refresh-button");
  refreshButton.classList.add("spinning");
  try {
    const [agentData, commandData] = await Promise.all([api("/api/v1/agents"), api("/api/v1/commands")]);
    const nextCommandStates = new Map(commandData.map(command => [command.id, command.status]));
    agents = agentData;
    commands = commandData;
    machines = agents.flatMap(agent => (agent.vms || []).map(vm => ({
      ...vm,
      agent_id: agent.agent_id,
      agent_name: agent.hostname,
      agent_online: online(agent),
      last_seen: agent.last_seen,
    })));
    for (const command of commandData) {
      const oldState = previousCommandStates.get(command.id);
      if (oldState && oldState !== command.status && ["success", "failed"].includes(command.status)) {
        const machine = machines.find(item => item.uuid === command.vm_uuid && item.agent_id === command.agent_id);
        const machineName = machine?.name || command.vm_uuid;
        notify(command.status === "success"
          ? `Orden completada: ${actionLabels[command.action] || command.action} · ${machineName}.`
          : `Falló ${actionLabels[command.action] || command.action} · ${machineName}: ${command.error || "sin detalle del error"}.`, command.status === "failed" ? "error" : "");
      }
    }
    previousCommandStates = nextCommandStates;
    render();
    document.querySelector("#connection-label").textContent = "Conectado y sincronizado";
    document.querySelector(".connection-dot").classList.add("online");
    document.querySelector("#updated-label").textContent = `Actualizado ${new Intl.DateTimeFormat("es-ES", { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(new Date())}`;
    document.querySelector("#updated-label").classList.remove("stale-data");
    document.querySelector("#machines-updated-label").textContent = `Inventario sincronizado ${new Intl.DateTimeFormat("es-ES", { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(new Date())}`;
    document.querySelector("#machines-updated-label").classList.remove("stale-data");
    lastError = "";
  } catch (error) {
    document.querySelector("#connection-label").textContent = "Error de conexión";
    document.querySelector(".connection-dot").classList.remove("online");
    document.querySelector("#updated-label").textContent = "Sin conexión · datos anteriores";
    document.querySelector("#updated-label").classList.add("stale-data");
    document.querySelector("#machines-updated-label").textContent = "Sin conexión · datos anteriores";
    document.querySelector("#machines-updated-label").classList.add("stale-data");
    if (error.message !== lastError) notify(error.message, "error");
    lastError = error.message;
  } finally {
    refreshing = false;
    refreshButton.classList.remove("spinning");
  }
}

function openVmDetails(machine) {
  document.querySelector("#detail-vm-name").textContent = machine.name;
  document.querySelector("#detail-vm-state").innerHTML = `<span class="status-badge ${stateClass(machine.state)}"><i></i>${escapeHtml(stateLabels[machine.state] || machine.state || "Desconocido")}</span>`;
  document.querySelector("#detail-agent").textContent = machine.agent_name;
  document.querySelector("#detail-agent-status").textContent = machine.agent_online ? "Conectado" : "Sin señal reciente";
  document.querySelector("#detail-agent-status").className = machine.agent_online ? "detail-online" : "detail-offline";
  document.querySelector("#detail-uuid").textContent = machine.uuid;
  document.querySelector("#detail-last-seen").textContent = relativeTime(machine.last_seen);
  const actions = availableActions(machine);
  document.querySelector("#detail-actions").innerHTML = actions.length
    ? actions.map(([action, label, danger]) => `<button class="action-button ${danger ? "danger" : ""}" data-action="${action}" data-agent="${escapeHtml(machine.agent_id)}" data-vm="${escapeHtml(machine.uuid)}" ${machine.agent_online ? "" : "disabled title=\"El agente no tiene conexión reciente\""}>${label}</button>`).join("")
    : '<span class="detail-no-actions">No hay acciones disponibles para este estado.</span>';
  vmDetailDialog.showModal();
}

function openAction(machine, action) {
  if (vmDetailDialog.open) vmDetailDialog.close();
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
  const detailButton = event.target.closest("button[data-vm-detail]");
  if (detailButton) {
    const machine = machines.find(item => item.uuid === detailButton.dataset.vmDetail && item.agent_id === detailButton.dataset.agent);
    if (machine) openVmDetails(machine);
    return;
  }
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const machine = machines.find(item => item.uuid === button.dataset.vm && item.agent_id === button.dataset.agent);
  if (machine) openAction(machine, button.dataset.action);
});

document.querySelector("#detail-actions").addEventListener("click", event => {
  const button = event.target.closest("button[data-action]");
  if (!button || button.disabled) return;
  const machine = machines.find(item => item.uuid === button.dataset.vm && item.agent_id === button.dataset.agent);
  if (machine) openAction(machine, button.dataset.action);
});

document.querySelector("#agent-list").addEventListener("click", event => {
  const button = event.target.closest("button[data-open-agent]");
  if (!button) return;
  selectedAgentId = button.dataset.openAgent;
  sessionStorage.setItem("vm_selected_agent", selectedAgentId);
  document.querySelector("#agent-selector").value = selectedAgentId;
  window.location.hash = "#maquinas";
  renderMachines();
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
const filterControls = ["#machine-search", "#state-filter", "#machine-sort"].map(selector => document.querySelector(selector));
function saveFilters() {
  sessionStorage.setItem("vm_machine_filters", JSON.stringify({
    query: filterControls[0].value,
    state: filterControls[1].value,
    sort: filterControls[2].value,
  }));
}
for (const control of filterControls) {
  control.addEventListener("change", () => { saveFilters(); renderMachines(); });
}
filterControls[0].addEventListener("input", () => { saveFilters(); renderMachines(); });
document.querySelector("#show-machines").addEventListener("click", () => {
  filterControls[0].value = "";
  filterControls[1].value = "all";
  filterControls[2].value = "name";
  saveFilters();
  renderMachines();
});
document.querySelector("#agent-selector").addEventListener("change", event => {
  selectedAgentId = event.target.value;
  if (selectedAgentId) sessionStorage.setItem("vm_selected_agent", selectedAgentId);
  else sessionStorage.removeItem("vm_selected_agent");
  renderMachines();
});
window.addEventListener("hashchange", updateView);
tokenForm.addEventListener("submit", event => {
  event.preventDefault();
  token = document.querySelector("#token-input").value.trim();
  sessionStorage.setItem("vm_api_token", token);
  tokenDialog.close();
  lastError = "";
  refresh();
});

if (!token) tokenDialog.showModal();
try {
  const saved = JSON.parse(sessionStorage.getItem("vm_machine_filters") || "{}");
  filterControls[0].value = saved.query || "";
  filterControls[1].value = ["all", "running", "paused", "poweroff", "other"].includes(saved.state) ? saved.state : "all";
  filterControls[2].value = ["name", "state"].includes(saved.sort) ? saved.sort : "name";
} catch { sessionStorage.removeItem("vm_machine_filters"); }
updateView();
refresh();
setInterval(refresh, REFRESH_MS);
