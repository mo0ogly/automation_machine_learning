// Shared API surface for the Deep RL workbench (catalogue, training jobs, the
// persistent "My agents" registry, and import/export). Centralised here so the
// view and its panels never duplicate the base URL or endpoint paths.

// Configurable at build time (Docker passes VITE_API_URL); defaults to the local
// dev backend so `npm run dev` keeps working unchanged.
export const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const BASE = API_URL + '/api/rl/deep';

async function jsonOrThrow(res) {
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || 'Erreur backend');
  return data;
}

export const getCatalog = () => fetch(BASE + '/catalog').then(jsonOrThrow);
export const getRegistry = () => fetch(BASE + '/registry').then(jsonOrThrow);
export const getJob = (id) => fetch(BASE + '/job/' + id).then(jsonOrThrow);

export const postTrain = (body) =>
  fetch(BASE + '/train', post(body)).then(jsonOrThrow);
export const postEvaluate = (agentId, envId) =>
  fetch(BASE + '/evaluate', post({ agent_id: agentId, env_id: envId || '' })).then(jsonOrThrow);
export const postContinue = (agentId, envId, config) =>
  fetch(BASE + '/continue', post({ agent_id: agentId, env_id: envId || '', config: config || {} })).then(jsonOrThrow);
export const postSave = (jobId, name) =>
  fetch(BASE + '/save', post({ job_id: jobId, name: name || '' })).then(jsonOrThrow);
export const cancelJob = (id) =>
  fetch(BASE + '/job/' + id + '/cancel', { method: 'POST' }).catch(() => {});

export const deleteAgent = (id) =>
  fetch(BASE + '/registry/' + id, { method: 'DELETE' }).then(jsonOrThrow);
export const deleteEnv = (id) =>
  fetch(BASE + '/env/' + encodeURIComponent(id), { method: 'DELETE' }).then(jsonOrThrow);

export const postExplain = (body) =>
  fetch(BASE + '/explain', post(body)).then(jsonOrThrow);

// Multipart uploads (an SB3 .zip agent, or a CSV alert dataset).
export const importAgent = (file, name, envId, algo) => {
  const fd = new FormData();
  fd.append('file', file); fd.append('name', name || '');
  fd.append('env_id', envId); fd.append('algo', algo);
  return fetch(BASE + '/import', { method: 'POST', body: fd }).then(jsonOrThrow);
};
export const importEnv = (file, name) => {
  const fd = new FormData();
  fd.append('file', file); fd.append('name', name || '');
  return fetch(BASE + '/import-env', { method: 'POST', body: fd }).then(jsonOrThrow);
};

// Download URLs (used as <a href> so the browser streams the file).
export const jobDownloadUrl = (jobId) => BASE + '/job/' + jobId + '/download';
export const agentDownloadUrl = (agentId) => BASE + '/registry/' + agentId + '/download';
export const agentExportUrl = (agentId) => BASE + '/registry/' + agentId + '/export';

function post(body) {
  return { method: 'POST', headers: { 'Content-Type': 'application/json' },
           body: JSON.stringify(body) };
}
