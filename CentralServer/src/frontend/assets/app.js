import { api } from "./api.js";
import { actionLabels, escapeHtml, networkModeLabels, online, relativeTime, roleLabels, stateClass, stateLabels } from "./helpers.js";

const REFRESH_MS = 5000;
const loginDialog = document.querySelector("#login-dialog");
const actionDialog = document.querySelector("#action-dialog");
const agentAccessDialog = document.querySelector("#agent-access-dialog");
const loginForm = document.querySelector("#login-form");
const toastRegion = document.querySelector("#toast-region");
let authenticated = false;
let currentUsername = "";
let currentRole = "";
let selectedAgentId = sessionStorage.getItem("vm_selected_agent") || "";
let managementAgents = [];
const pendingAgentScopes = new Map();
let editingAgentUserId = "";
let agents = [];
let machines = [];
let commands = [];
let selectedAction = null;
let configuringMachine = null;
let lastError = "";
let previousCommandStates = new Map();
let refreshing = false;
let commandRoute = "";

function notify(message, type = "") {
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.textContent = message;
  toastRegion.append(toast);
  setTimeout(() => toast.remove(), 4200);
}

function heartbeatLabel(agent) {
  return online(agent) ? "Conectado" : `Sin señal · ${relativeTime(agent.last_seen)}`;
}

window.addEventListener("virtualmanager:unauthorized", () => {
  authenticated = false;
  if (!loginDialog.open) loginDialog.showModal();
});

function updateUserBadge() {
  const badge = document.querySelector("#user-badge");
  badge.textContent = currentUsername.slice(0, 2).toUpperCase() || "VM";
  badge.title = currentUsername ? `${currentUsername} · ${roleLabels[currentRole] || ""}` : "Sesión de usuario";
  document.querySelector("#users-nav-link").classList.toggle("hidden-screen", currentRole !== "admin");
}

async function restoreSession() {
  try {
    const session = await api("/api/v1/auth/me");
    authenticated = true;
    currentUsername = session.username;
    currentRole = session.role;
    updateUserBadge();
    updateView();
    await refresh();
  } catch (error) {
    if (error.status !== 401) notify(error.message, "error");
    if (!loginDialog.open) loginDialog.showModal();
  }
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
  if (currentRole === "observer") return '<div class="row-actions"><span class="date-cell">Solo lectura</span></div>';
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

function renderVmCommands() {
  const body = document.querySelector("#vm-commands-body");
  const recent = commands.slice(0, 20);
  const pendingCount = commands.filter(command => command.status === "pending").length;
  const runningCount = commands.filter(command => command.status === "running").length;
  document.querySelector("#command-summary").textContent = `${pendingCount} pendientes · ${runningCount} en curso · últimas 20`;
  if (!recent.length) {
    body.innerHTML = '<tr><td colspan="4" class="empty-cell">Esta máquina todavía no tiene órdenes.</td></tr>';
    return;
  }
  body.innerHTML = recent.map(command => {
    const statusClass = { pending: "command-pending", running: "command-running", success: "command-success", failed: "command-failed" }[command.status] || "command-pending";
    const statusLabel = { pending: "Pendiente", running: "En curso", success: "Completada", failed: "Fallida" }[command.status] || command.status;
    const row = `<tr><td class="action-label">${escapeHtml(actionLabels[command.action] || command.action)}</td><td><span class="command-badge ${statusClass}">${statusLabel}</span></td><td class="date-cell">${relativeTime(command.created_at)}</td><td class="date-cell">${relativeTime(command.completed_at)}</td></tr>`;
    const errorRow = command.status === "failed" && command.error
      ? `<tr class="command-error-row"><td colspan="4"><span class="error-symbol">!</span><strong>Error de ejecución:</strong> ${escapeHtml(command.error)}</td></tr>`
      : "";
    return row + errorRow;
  }).join("");
}

function render() {
  const running = machines.filter(machine => machine.state === "running").length;
  document.querySelector("#stat-vms").textContent = machines.length;
  document.querySelector("#stat-running").textContent = running;
  renderAgentSelector();
  renderMachines();
  renderAgents();
  renderVmDetails();
}

function updateView() {
  const hash = window.location.hash;
  const detailMatch = hash.match(/^#vm\/([^/]+)\/(.+)$/);
  let view = detailMatch ? "detail" : hash === "#maquinas" ? "machines" : hash === "#usuarios" && currentRole === "admin" ? "users" : "dashboard";
  if (hash === "#usuarios" && currentRole !== "admin") window.location.hash = "#inicio";
  if (commandRoute !== (view === "detail" ? hash : "")) {
    commandRoute = view === "detail" ? hash : "";
    commands = [];
    previousCommandStates = new Map();
  }
  if (detailMatch) {
    try { selectedAgentId = decodeURIComponent(detailMatch[1]); } catch { selectedAgentId = ""; }
    sessionStorage.setItem("vm_selected_agent", selectedAgentId);
  }
  document.querySelector("#dashboard-screen").classList.toggle("hidden-screen", view !== "dashboard");
  document.querySelector("#machines-screen").classList.toggle("hidden-screen", view !== "machines");
  document.querySelector("#vm-detail-screen").classList.toggle("hidden-screen", view !== "detail");
  document.querySelector("#users-screen").classList.toggle("hidden-screen", view !== "users");
  document.querySelectorAll(".nav-link[data-view]").forEach(link => {
    link.classList.toggle("selected", link.dataset.view === (view === "detail" ? "machines" : view));
  });
  document.querySelector("#breadcrumb-current").textContent = view === "machines" ? "Máquinas virtuales" : view === "detail" ? "Detalle de máquina" : view === "users" ? "Usuarios" : "Resumen";
  if (view === "machines") renderMachines();
  if (view === "detail") renderVmDetails();
  if (view === "users") loadUsers();
  refresh();
}

function routeMachine() {
  const match = window.location.hash.match(/^#vm\/([^/]+)\/(.+)$/);
  if (!match) return null;
  try {
    const agentId = decodeURIComponent(match[1]);
    const uuid = decodeURIComponent(match[2]);
    return machines.find(machine => machine.agent_id === agentId && machine.uuid === uuid) || null;
  } catch { return null; }
}

function renderVmDetails() {
  if (!document.querySelector("#vm-detail-screen").classList.contains("hidden-screen")) {
    const machine = routeMachine();
    if (!machine) {
      document.querySelector("#detail-vm-name").textContent = "Máquina no disponible";
      document.querySelector("#detail-vm-state").textContent = "No se ha encontrado en el inventario del agente.";
      document.querySelector("#vm-page-actions").innerHTML = "";
      document.querySelector("#detail-vm-memory").textContent = "—";
      document.querySelector("#detail-vm-cpus").textContent = "—";
      document.querySelector("#detail-vm-networks").innerHTML = '<tr><td colspan="5" class="empty-cell">Cargando configuración…</td></tr>';
      document.querySelector("#vm-commands-body").innerHTML = '<tr><td colspan="4" class="empty-cell">Cargando inventario de la máquina…</td></tr>';
      return;
    }
    document.querySelector("#detail-vm-name").textContent = machine.name;
    document.querySelector("#detail-vm-state").innerHTML = `<span class="status-badge ${stateClass(machine.state)}"><i></i>${escapeHtml(stateLabels[machine.state] || machine.state || "Desconocido")}</span>`;
    document.querySelector("#detail-agent").textContent = machine.agent_name;
    document.querySelector("#detail-agent-status").textContent = machine.agent_online ? "Conectado" : "Sin señal reciente";
    document.querySelector("#detail-agent-status").className = machine.agent_online ? "detail-online" : "detail-offline";
    document.querySelector("#detail-uuid").textContent = machine.uuid;
    document.querySelector("#detail-last-seen").textContent = relativeTime(machine.last_seen);
    document.querySelector("#detail-vm-memory").textContent = Number.isFinite(machine.memory_mb) ? `${machine.memory_mb.toLocaleString("es-ES")} MB` : "No disponible";
    document.querySelector("#detail-vm-cpus").textContent = Number.isFinite(machine.cpu_count) ? `${machine.cpu_count} ${machine.cpu_count === 1 ? "núcleo" : "núcleos"}` : "No disponible";
    const adapters = Array.isArray(machine.network_adapters) ? machine.network_adapters : [];
    document.querySelector("#detail-vm-networks").innerHTML = adapters.length ? adapters.map(adapter => `<tr><td>Interfaz ${adapter.slot}</td><td>${adapter.enabled ? "Activa" : "Desactivada"}</td><td>${escapeHtml(networkModeLabels[adapter.mode] || adapter.mode || "—")}</td><td>${escapeHtml(adapter.adapter || "—")}</td><td>${adapter.cable_connected ? "Conectado" : "Desconectado"}</td></tr>`).join("") : '<tr><td colspan="5" class="empty-cell">El agente aún no ha informado de las interfaces.</td></tr>';
    const configButton = document.querySelector("#edit-vm-config");
    configButton.disabled = currentRole === "observer" || !machine.agent_online || machine.state !== "poweroff";
    configButton.title = currentRole === "observer" ? "El perfil observador es de solo lectura" : !machine.agent_online ? "El agente no tiene conexión reciente" : machine.state !== "poweroff" ? "Apaga la máquina antes de cambiar su configuración" : "Configurar RAM, CPU e interfaces de red";
    const actions = currentRole === "observer" ? [] : availableActions(machine);
    document.querySelector("#vm-page-actions").innerHTML = currentRole === "observer" ? '<span class="detail-no-actions">Acceso de solo lectura.</span>' : actions.length
      ? actions.map(([action, label, danger]) => `<button class="action-button ${danger ? "danger" : ""}" data-action="${action}" data-agent="${escapeHtml(machine.agent_id)}" data-vm="${escapeHtml(machine.uuid)}" ${machine.agent_online ? "" : "disabled title=\"El agente no tiene conexión reciente\""}>${label}</button>`).join("")
      : '<span class="detail-no-actions">No hay acciones disponibles para este estado.</span>';
    document.querySelector("#detail-updated-label").textContent = `Señal ${relativeTime(machine.last_seen).toLowerCase()}`;
    renderVmCommands();
  }
}

async function loadUsers() {
  if (currentRole !== "admin") return;
  try {
    const [users, agents] = await Promise.all([api("/api/v1/users"), api("/api/v1/agents")]);
    managementAgents = agents;
    renderCreateAgentOptions();
    pendingAgentScopes.clear();
    document.querySelector("#users-body").innerHTML = users.map(user => {
      const selectedAgents = new Set(user.agent_ids || []);
      pendingAgentScopes.set(user.id, [...selectedAgents]);
      const agentCount = user.role === "admin" ? "Todos" : `${selectedAgents.size} asignados`;
      return `<tr><td><strong>${escapeHtml(user.username)}</strong></td><td><select aria-label="Rol de ${escapeHtml(user.username)}" data-user-role="${escapeHtml(user.id)}"><option value="admin" ${user.role === "admin" ? "selected" : ""}>Administrador</option><option value="operator" ${user.role === "operator" ? "selected" : ""}>Operador</option><option value="observer" ${user.role === "observer" ? "selected" : ""}>Observador</option></select></td><td><select aria-label="Acceso de ${escapeHtml(user.username)}" data-user-active="${escapeHtml(user.id)}"><option value="true" ${user.is_active ? "selected" : ""}>Puede iniciar sesión</option><option value="false" ${!user.is_active ? "selected" : ""}>Acceso bloqueado</option></select></td><td><button class="text-button" aria-label="Gestionar agentes permitidos de ${escapeHtml(user.username)}" data-edit-agent-access="${escapeHtml(user.id)}">${agentCount}</button></td><td><button class="text-button" data-save-user="${escapeHtml(user.id)}">Guardar</button></td></tr>`;
    }).join("");
  } catch (error) { notify(error.message, "error"); }
}

function openAgentAccessDialog(userId, row) {
  editingAgentUserId = userId;
  const username = row.cells[0].textContent.trim();
  const role = row.querySelector(`[data-user-role="${CSS.escape(userId)}"]`).value;
  const selectedAgents = new Set(pendingAgentScopes.get(userId) || []);
  document.querySelector("#agent-access-title").textContent = `Agentes de ${username}`;
  document.querySelector("#agent-access-description").textContent = role === "admin"
    ? "Las cuentas administradoras tienen acceso a todos los agentes."
    : role === "operator"
      ? "El operador podrá consultar y enviar órdenes a los agentes seleccionados."
      : "El observador podrá consultar únicamente los agentes seleccionados.";
  document.querySelector("#agent-access-list").innerHTML = role === "admin"
    ? '<div class="global-access-note">Acceso global a todos los agentes registrados.</div>'
    : managementAgents.length
      ? managementAgents.map(agent => `<label class="modal-agent-option"><input type="checkbox" data-access-agent value="${escapeHtml(agent.agent_id)}" ${selectedAgents.has(agent.agent_id) ? "checked" : ""}><span><strong>${escapeHtml(agent.hostname)}</strong><small>${escapeHtml(agent.platform || "Agente")}${agent.version ? ` · v${escapeHtml(agent.version)}` : ""}</small></span></label>`).join("")
      : '<div class="global-access-note">Todavía no hay agentes registrados.</div>';
  agentAccessDialog.showModal();
}

document.querySelector("#users-body").addEventListener("click", async event => {
  const accessButton = event.target.closest("[data-edit-agent-access]");
  if (accessButton) {
    openAgentAccessDialog(accessButton.dataset.editAgentAccess, accessButton.closest("tr"));
    return;
  }
  const button = event.target.closest("[data-save-user]");
  if (!button) return;
  const id = button.dataset.saveUser;
  try {
    const role = document.querySelector(`[data-user-role="${CSS.escape(id)}"]`).value;
    const agentIds = [...(pendingAgentScopes.get(id) || [])];
    await api(`/api/v1/users/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify({ role, is_active: document.querySelector(`[data-user-active="${CSS.escape(id)}"]`).value === "true", agent_ids: agentIds }) });
    notify("Permisos actualizados.");
    await loadUsers();
  } catch (error) { notify(error.message, "error"); }
});

document.querySelector("#users-body").addEventListener("change", event => {
  const roleSelect = event.target.closest("[data-user-role]");
  if (!roleSelect) return;
  const row = roleSelect.closest("tr");
  const id = roleSelect.dataset.userRole;
  const agentButton = row.querySelector(`[data-edit-agent-access="${CSS.escape(id)}"]`);
  agentButton.textContent = roleSelect.value === "admin"
    ? "Todos"
    : `${(pendingAgentScopes.get(id) || []).length} asignados`;
});

document.querySelector("#cancel-agent-access").addEventListener("click", () => agentAccessDialog.close());
document.querySelector("#save-agent-access").addEventListener("click", async () => {
  if (!editingAgentUserId) return;
  const id = editingAgentUserId;
  const row = document.querySelector(`[data-save-user="${CSS.escape(id)}"]`).closest("tr");
  const role = row.querySelector(`[data-user-role="${CSS.escape(id)}"]`).value;
  const active = row.querySelector(`[data-user-active="${CSS.escape(id)}"]`).value === "true";
  const agentIds = role === "admin" ? [] : [...document.querySelectorAll("#agent-access-list [data-access-agent]:checked")].map(input => input.value);
  const button = document.querySelector("#save-agent-access");
  button.disabled = true;
  try {
    await api(`/api/v1/users/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify({ role, is_active: active, agent_ids: agentIds }) });
    pendingAgentScopes.set(id, agentIds);
    agentAccessDialog.close();
    notify("Acceso a agentes actualizado.");
    await loadUsers();
  } catch (error) { notify(error.message, "error"); }
  finally { button.disabled = false; }
});

const userCreateForm = document.querySelector("#user-create-form");
const createAgentAccess = document.querySelector("#create-agent-access");
function updateCreateAgentAccess() {
  const role = userCreateForm.elements.role.value;
  createAgentAccess.hidden = role === "admin";
  document.querySelector("#create-agent-access-title").textContent = role === "operator"
    ? "Agentes que podrá gestionar"
    : "Agentes que podrá observar";
  document.querySelector("#create-agent-access-description").textContent = role === "operator"
    ? "El operador podrá consultar y enviar órdenes a los agentes seleccionados."
    : "El observador podrá consultar únicamente los agentes seleccionados.";
}

function renderCreateAgentOptions() {
  const options = document.querySelector("#create-agent-options");
  options.innerHTML = managementAgents.length
    ? managementAgents.map(agent => `<label class="create-agent-option"><input type="checkbox" name="agent_ids" value="${escapeHtml(agent.agent_id)}"><span><strong>${escapeHtml(agent.hostname)}</strong><small>${escapeHtml(agent.platform || "Agente")}${agent.version ? ` · v${escapeHtml(agent.version)}` : ""}</small></span></label>`).join("")
    : '<span class="create-agent-empty">No hay agentes registrados todavía.</span>';
  updateCreateAgentAccess();
}

userCreateForm.elements.role.addEventListener("change", updateCreateAgentAccess);
updateCreateAgentAccess();
const userPasswordInput = userCreateForm.elements.password;
const userPasswordFeedback = document.querySelector("#user-password-feedback");
function passwordIsSecure(password) {
  return password.length >= 12 && /[a-z]/.test(password) && /[A-Z]/.test(password) && /\d/.test(password) && /[^A-Za-z0-9]/.test(password);
}
userPasswordInput.addEventListener("input", () => {
  const hasPassword = Boolean(userPasswordInput.value);
  const isSecure = passwordIsSecure(userPasswordInput.value);
  userPasswordFeedback.textContent = hasPassword && !isSecure
    ? "Usa al menos 12 caracteres e incluye mayúsculas, minúsculas, números y símbolos."
    : "";
  userPasswordFeedback.classList.toggle("is-visible", hasPassword && !isSecure);
  userPasswordInput.setCustomValidity(hasPassword && !isSecure ? "La contraseña todavía no es segura." : "");
});

userCreateForm.addEventListener("submit", async event => {
  event.preventDefault();
  const form = event.currentTarget;
  if (!form.reportValidity()) return;
  const data = new FormData(form);
  try {
    const role = data.get("role");
    const agentIds = role === "admin" ? [] : [...document.querySelectorAll("#create-agent-options input:checked")].map(input => input.value);
    await api("/api/v1/users", { method: "POST", body: JSON.stringify({ username: data.get("username"), password: data.get("password"), role, agent_ids: agentIds }) });
    form.reset();
    updateCreateAgentAccess();
    notify("Usuario creado.");
    await loadUsers();
  } catch (error) { notify(error.message, "error"); }
});

async function refresh() {
  if (refreshing) return;
  if (!authenticated) return;
  refreshing = true;
  const refreshButton = document.querySelector("#refresh-button");
  refreshButton.classList.add("spinning");
  try {
    const agentData = await api("/api/v1/agents");
    agents = agentData;
    machines = agents.flatMap(agent => (agent.vms || []).map(vm => ({
      ...vm,
      agent_id: agent.agent_id,
      agent_name: agent.hostname,
      agent_online: online(agent),
      last_seen: agent.last_seen,
    })));
    const currentMachine = routeMachine();
    const commandData = currentMachine
      ? await api(`/api/v1/commands?agent_id=${encodeURIComponent(currentMachine.agent_id)}&vm_uuid=${encodeURIComponent(currentMachine.uuid)}`)
      : [];
    if (!currentMachine) previousCommandStates = new Map();
    const nextCommandStates = new Map(commandData.map(command => [command.id, command.status]));
    commands = commandData;
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
    if (error.status !== 401 && error.message !== lastError) notify(error.message, "error");
    lastError = error.message;
  } finally {
    refreshing = false;
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

function openVmConfiguration(machine) {
  configuringMachine = machine;
  const form = document.querySelector("#vm-config-form");
  form.elements.memory_mb.value = machine.memory_mb || 1024;
  form.elements.cpu_count.value = machine.cpu_count || 1;
  const existing = new Map((machine.network_adapters || []).map(adapter => [adapter.slot, adapter]));
  const modes = ["nat", "natnetwork", "bridged", "intnet", "hostonly", "generic", "null", "none"];
  document.querySelector("#network-config-list").innerHTML = Array.from({ length: 8 }, (_, index) => {
    const slot = index + 1;
    const adapter = existing.get(slot) || { enabled: false, mode: "nat", adapter: "", cable_connected: true };
    return `<div class="network-config-row"><label class="network-enabled"><input type="checkbox" data-network-enabled="${slot}" ${adapter.enabled ? "checked" : ""}><span>NIC ${slot}</span></label><label>Modo<select data-network-mode="${slot}">${modes.map(mode => `<option value="${mode}" ${adapter.mode === mode ? "selected" : ""}>${escapeHtml(networkModeLabels[mode])}</option>`).join("")}</select></label><label>Nombre de red<input type="text" data-network-adapter="${slot}" maxlength="255" value="${escapeHtml(adapter.adapter || "")}" placeholder="Opcional"></label><label class="network-cable"><input type="checkbox" data-network-cable="${slot}" ${adapter.cable_connected !== false ? "checked" : ""}><span>Cable conectado</span></label></div>`;
  }).join("");
  document.querySelector("#config-dialog").showModal();
}

document.querySelector("#edit-vm-config").addEventListener("click", () => {
  const machine = routeMachine();
  if (machine && currentRole !== "observer" && machine.state === "poweroff" && machine.agent_online) openVmConfiguration(machine);
});
document.querySelector("#cancel-vm-config").addEventListener("click", () => document.querySelector("#config-dialog").close());
document.querySelector("#vm-config-form").addEventListener("submit", async event => {
  event.preventDefault();
  if (!configuringMachine) return;
  const form = event.currentTarget;
  const button = document.querySelector("#save-vm-config");
  const network_adapters = Array.from({ length: 8 }, (_, index) => {
    const slot = index + 1;
    return {
      slot,
      enabled: document.querySelector(`[data-network-enabled="${slot}"]`).checked,
      mode: document.querySelector(`[data-network-mode="${slot}"]`).value,
      adapter: document.querySelector(`[data-network-adapter="${slot}"]`).value.trim(),
      cable_connected: document.querySelector(`[data-network-cable="${slot}"]`).checked,
    };
  });
  button.disabled = true;
  button.textContent = "Enviando…";
  try {
    await api("/api/v1/commands", {
      method: "POST",
      body: JSON.stringify({
        agent_id: configuringMachine.agent_id,
        vm_uuid: configuringMachine.uuid,
        action: "configure",
        payload: { memory_mb: Number(form.elements.memory_mb.value), cpu_count: Number(form.elements.cpu_count.value), network_adapters },
      }),
    });
    document.querySelector("#config-dialog").close();
    notify(`Configuración enviada a ${configuringMachine.name}.`);
    configuringMachine = null;
    await refresh();
  } catch (error) {
    notify(error.message, "error");
  } finally {
    button.disabled = false;
    button.innerHTML = "Enviar configuración <span>→</span>";
  }
});

document.querySelector("#machines-body").addEventListener("click", event => {
  const detailButton = event.target.closest("button[data-vm-detail]");
  if (detailButton) {
    const machine = machines.find(item => item.uuid === detailButton.dataset.vmDetail && item.agent_id === detailButton.dataset.agent);
    if (machine) {
      selectedAgentId = machine.agent_id;
      sessionStorage.setItem("vm_selected_agent", selectedAgentId);
      const destination = `#vm/${encodeURIComponent(machine.agent_id)}/${encodeURIComponent(machine.uuid)}`;
      if (window.location.hash === destination) updateView();
      else window.location.hash = destination;
    }
    return;
  }
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const machine = machines.find(item => item.uuid === button.dataset.vm && item.agent_id === button.dataset.agent);
  if (machine) openAction(machine, button.dataset.action);
});

document.querySelector("#vm-page-actions").addEventListener("click", event => {
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

document.querySelector("#settings-button").addEventListener("click", async () => {
  try { await api("/api/v1/auth/logout", { method: "POST" }); } catch { /* La sesión puede haber caducado. */ }
  authenticated = false;
  currentUsername = "";
  currentRole = "";
  updateUserBadge();
  commands = [];
  previousCommandStates = new Map();
  if (!loginDialog.open) loginDialog.showModal();
});
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
loginForm.addEventListener("submit", async event => {
  event.preventDefault();
  const errorLabel = document.querySelector("#login-error");
  const submitButton = loginForm.querySelector("button[type=submit]");
  errorLabel.textContent = "";
  submitButton.disabled = true;
  try {
    const session = await api("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({
        username: document.querySelector("#username-input").value,
        password: document.querySelector("#password-input").value,
      }),
    });
    authenticated = true;
    currentUsername = session.username;
    currentRole = session.role;
    updateUserBadge();
    loginForm.reset();
    loginDialog.close();
    lastError = "";
    updateView();
    await refresh();
  } catch (error) {
    errorLabel.textContent = error.status === 401 ? "Usuario o contraseña incorrectos." : error.message;
  } finally {
    submitButton.disabled = false;
  }
});

try {
  const saved = JSON.parse(sessionStorage.getItem("vm_machine_filters") || "{}");
  filterControls[0].value = saved.query || "";
  filterControls[1].value = ["all", "running", "paused", "poweroff", "other"].includes(saved.state) ? saved.state : "all";
  filterControls[2].value = ["name", "state"].includes(saved.sort) ? saved.sort : "name";
} catch { sessionStorage.removeItem("vm_machine_filters"); }
updateView();
restoreSession();
setInterval(refresh, REFRESH_MS);
