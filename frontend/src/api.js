const API_BASE = import.meta.env.VITE_API_BASE ?? '';

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options.headers ?? {}) },
    ...options,
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed: ${response.status}`);
  }

  if (response.status === 204) return null;
  return response.json();
}

export const api = {
  health: () => request('/api/health'),
  install: () => request('/api/install', { method: 'POST' }),
  generate: (body) => request('/api/generate', { method: 'POST', body: JSON.stringify(body) }),
  generateSong: (body) => request('/api/songs/generate', { method: 'POST', body: JSON.stringify(body) }),
  generateMastering: (body) => request('/api/mastering/generate', { method: 'POST', body: JSON.stringify(body) }),
  approveMastering: (id) => request(`/api/mastering/${id}/approve`, { method: 'POST' }),
  approve: (id) => request(`/api/payloads/${id}/approve`, { method: 'POST' }),
  bridgeHealth: () => request('/api/bridge/health'),
  bridgeTransport: (action) => request('/api/bridge/transport', { method: 'POST', body: JSON.stringify({ action }) }),
  bridgeSetup: () => request('/api/bridge/setup'),
  installBridgeScripts: (body = {}) => request('/api/bridge/setup/install-scripts', { method: 'POST', body: JSON.stringify(body) }),
  events: () => request('/api/events'),
};
