export async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  if (response.status === 401) {
    window.dispatchEvent(new CustomEvent("virtualmanager:unauthorized"));
    const error = new Error("La sesión ha caducado. Inicia sesión de nuevo.");
    error.status = 401;
    throw error;
  }
  if (!response.ok) {
    let detail = `Error ${response.status}`;
    try { detail = (await response.json()).detail || detail; } catch { /* Respuesta sin JSON. */ }
    const error = new Error(detail);
    error.status = response.status;
    throw error;
  }
  return response.json();
}
