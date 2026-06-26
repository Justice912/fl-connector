export function normalizeApiBase(value) {
  return (value ?? '').trim().replace(/\/+$/, '');
}

const API_BASE = normalizeApiBase(import.meta.env.VITE_API_BASE);

async function request(path, options = {}) {
  const headers = { ...(options.headers ?? {}) };
  if (options.body && !(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed: ${response.status}`);
  }

  if (response.status === 204) return null;
  return response.json();
}

async function download(path, fallbackName) {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed: ${response.status}`);
  }
  const blob = await response.blob();
  const disposition = response.headers.get('Content-Disposition') ?? '';
  const fileName = disposition.match(/filename="?([^";]+)"?/i)?.[1] ?? fallbackName;
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = fileName;
  anchor.click();
  URL.revokeObjectURL(url);
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
  bridgeSetTempo: (bpm) => request('/api/bridge/tempo', { method: 'POST', body: JSON.stringify({ bpm }) }),
  bridgeSetMixerTrack: (index, body) => request(`/api/bridge/mixer/${index}`, { method: 'POST', body: JSON.stringify(body) }),
  bridgeSelectTrack: (index) => request(`/api/bridge/mixer/${index}/select`, { method: 'POST' }),
  bridgeMuteTrack: (index) => request(`/api/bridge/mixer/${index}/mute`, { method: 'POST' }),
  bridgeSoloTrack: (index) => request(`/api/bridge/mixer/${index}/solo`, { method: 'POST' }),
  bridgeSetChannel: (index, body) => request(`/api/bridge/channel/${index}`, { method: 'POST', body: JSON.stringify(body) }),
  bridgeSelectChannel: (index) => request(`/api/bridge/channel/${index}/select`, { method: 'POST' }),
  bridgeMuteChannel: (index) => request(`/api/bridge/channel/${index}/mute`, { method: 'POST' }),
  bridgeSoloChannel: (index) => request(`/api/bridge/channel/${index}/solo`, { method: 'POST' }),
  events: () => request('/api/events'),
  exportSongMidi: (id) => download(`/api/songs/${id}/export-midi`, `song-${id}.mid`),
  exportPayloadMidi: (id) => download(`/api/payloads/${id}/export-midi`, `part-${id}.mid`),
  analysisSetup: () => request('/api/analysis/setup'),
  installAnalysisWorker: (approved) => request('/api/analysis/setup/install', { method: 'POST', body: JSON.stringify({ approved }) }),
  listReconstructions: () => request('/api/reconstructions'),
  getReconstruction: (id) => request(`/api/reconstructions/${id}`),
  createReconstruction: (body) => request('/api/reconstructions', { method: 'POST', body: JSON.stringify(body) }),
  updateReconstruction: (id, body) => request(`/api/reconstructions/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteReconstruction: (id) => request(`/api/reconstructions/${id}`, { method: 'DELETE' }),
  uploadReconstructionStems: (id, files) => {
    const body = new FormData();
    files.forEach((file) => body.append('files', file));
    return request(`/api/reconstructions/${id}/stems`, { method: 'POST', body });
  },
  analyzeReconstruction: (id) => request(`/api/reconstructions/${id}/analyze`, { method: 'POST' }),
  retryReconstruction: (id) => request(`/api/reconstructions/${id}/retry`, { method: 'POST' }),
  updateReconstructionPart: (projectId, partId, body) => request(`/api/reconstructions/${projectId}/parts/${partId}`, { method: 'PATCH', body: JSON.stringify(body) }),
  updateReconstructionPattern: (projectId, partId, patternId, body) => request(`/api/reconstructions/${projectId}/parts/${partId}/patterns/${patternId}`, { method: 'PATCH', body: JSON.stringify(body) }),
  approveReconstructionPattern: (projectId, partId, patternId) => request(`/api/reconstructions/${projectId}/parts/${partId}/patterns/${patternId}/approve`, { method: 'POST' }),
  approveReconstructionAudio: (projectId, partId) => request(`/api/reconstructions/${projectId}/parts/${partId}/approve-audio`, { method: 'POST' }),
  updateGuideStep: (projectId, stepId, completed) => request(`/api/reconstructions/${projectId}/guide/${stepId}`, { method: 'PATCH', body: JSON.stringify({ completed }) }),
  inventory: () => request('/api/inventory'),
  refreshInventory: (extraRoots = []) => request('/api/inventory/refresh', { method: 'POST', body: JSON.stringify({ extraRoots }) }),
  exportReconstruction: (id) => download(`/api/reconstructions/${id}/export`, `reconstruction-${id}.zip`),
  stemContentUrl: (projectId, stemId) => `${API_BASE}/api/reconstructions/${projectId}/stems/${stemId}/content`,
};
