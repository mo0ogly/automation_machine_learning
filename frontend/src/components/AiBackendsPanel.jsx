import React, { useState, useEffect, useCallback } from 'react';

// Settings window for multi-provider AI backends (mirrors recette_IA_agents):
// list / activate / key (write-only) / test / delete + a create form whose
// dropdowns are built from the server-side provider catalog (single source of
// truth — adding a provider server-side surfaces here with no change).
const CUSTOM_MODEL = '__custom__';

function TestResult({ state }) {
  if (!state) return null;
  if (state.phase === 'testing') return <span className="ai-test-pending">test…</span>;
  if (state.phase === 'ok') return <span className="ai-test-ok">OK {state.ms} ms — « {state.text} »</span>;
  return <span className="ai-test-err">échec {state.ms} ms : {state.error}</span>;
}

export default function AiBackendsPanel({ apiBase, onClose, onChanged }) {
  const [providers, setProviders] = useState([]);
  const [backends, setBackends] = useState([]);
  const [err, setErr] = useState(null);
  const [form, setForm] = useState({ id: '', provider: 'groq', model: '', base_url: '' });
  const [keyDrafts, setKeyDrafts] = useState({});
  const [askDrafts, setAskDrafts] = useState({});
  const [tests, setTests] = useState({});

  const refresh = useCallback(async () => {
    try {
      const b = await fetch(apiBase + '/api/ai/backends').then((r) => r.json());
      setBackends(b.backends || []);
    } catch (e) { setErr('Backends injoignables.'); }
  }, [apiBase]);

  const loadProviders = useCallback(async () => {
    try {
      const d = await fetch(apiBase + '/api/ai/providers').then((r) => r.json());
      const list = d.providers || [];
      setProviders(list);
      setErr(null);
      setForm((p) => {
        if (p.model) return p;
        const info = list.find((x) => x.id === p.provider);
        return info && info.default_model ? { ...p, model: info.default_model } : p;
      });
    } catch (e) {
      setProviders([]);
      setErr('Catalogue providers injoignable — le backend tourne-t-il sur :8000 ?');
    }
  }, [apiBase]);

  useEffect(() => { loadProviders(); refresh(); }, [loadProviders, refresh]);

  const selProv = providers.find((p) => p.id === form.provider);
  const baseUrlMode = selProv ? selProv.base_url : null;
  const provModels = selProv ? selProv.models : [];
  const modelIsCustom = provModels.length > 0 && !provModels.includes(form.model);

  const changed = async () => { await refresh(); if (onChanged) await onChanged(); };

  const selectProvider = (pid) => {
    const info = providers.find((p) => p.id === pid);
    setForm((p) => ({ ...p, provider: pid, model: info && info.default_model ? info.default_model : '' }));
  };

  const create = async (e) => {
    e.preventDefault();
    const id = form.id.trim();
    if (!id) { setErr('Identifiant requis.'); return; }
    const body = { id, provider: form.provider, model: form.model.trim() };
    if (baseUrlMode === 'required' || (baseUrlMode === 'optional' && form.base_url.trim())) {
      body.base_url = form.base_url.trim();
    }
    try {
      const res = await fetch(apiBase + '/api/ai/backends',
        { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      const data = await res.json();
      if (!res.ok) { setErr(data.detail || 'Création refusée.'); return; }
      const def = providers.find((p) => p.id === 'groq');
      setForm({ id: '', provider: 'groq', model: def ? def.default_model : '', base_url: '' });
      setErr(null);
      await changed();
    } catch (e2) { setErr('Création échouée.'); }
  };

  const del = async (id) => {
    if (!window.confirm('Supprimer le backend « ' + id + ' » ?')) return;
    await fetch(apiBase + '/api/ai/backends/' + id, { method: 'DELETE' });
    await changed();
  };
  const saveKey = async (id) => {
    const key = keyDrafts[id] || '';
    if (!key) return;
    await fetch(apiBase + '/api/ai/backends/' + id + '/secret',
      { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ key }) });
    setKeyDrafts((p) => { const n = { ...p }; delete n[id]; return n; });
    await changed();
  };
  const removeKey = async (id) => {
    if (!window.confirm('Retirer la clé stockée pour « ' + id + ' » ?')) return;
    await fetch(apiBase + '/api/ai/backends/' + id + '/secret', { method: 'DELETE' });
    await changed();
  };
  const activate = async (id) => {
    await fetch(apiBase + '/api/ai/active',
      { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id }) });
    await changed();
  };
  const test = async (id) => {
    setTests((p) => ({ ...p, [id]: { phase: 'testing' } }));
    try {
      const prompt = (askDrafts[id] || '').trim();
      const res = await fetch(apiBase + '/api/ai/backends/' + id + '/test',
        { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(prompt ? { prompt } : {}) });
      const d = await res.json();
      setTests((p) => ({ ...p, [id]: d.ok
        ? { phase: 'ok', ms: d.latency_ms, text: d.text }
        : { phase: 'error', ms: d.latency_ms, error: d.error } }));
    } catch (e) {
      setTests((p) => ({ ...p, [id]: { phase: 'error', ms: 0, error: 'injoignable' } }));
    }
  };

  const keyHint = selProv && selProv.env_key
    ? ('Clé via ' + selProv.env_key + (selProv.env_present ? ' (présente)' : ' (absente)') + ', ou stockée par backend')
    : 'Pas de clé requise (serveur local)';

  return (
    <div className="ai-modal-overlay" onClick={onClose}>
      <div className="ai-modal glass-panel" onClick={(e) => e.stopPropagation()}>
        <div className="ai-modal-head">
          <h2>Backends IA</h2>
          <button type="button" className="ai-modal-close" onClick={onClose} aria-label="Fermer">×</button>
        </div>
        <p className="ai-modal-note">
          Chaque backend fixe un provider + un modèle. La clé est write-only (envoyée, jamais
          relue) ; sinon repli sur la variable d'environnement du provider. Le bouton radio choisit
          le backend actif de l'agent.
        </p>
        {err ? <div className="banner banner-block">{err}</div> : null}

        <table className="ai-table">
          <thead>
            <tr><th>Actif</th><th>Id</th><th>Provider</th><th>Modèle</th><th>Clé</th><th>Test</th><th></th></tr>
          </thead>
          <tbody>
            {backends.length === 0 ? (
              <tr><td colSpan={7} className="ai-empty">Aucun backend configuré.</td></tr>
            ) : backends.map((b) => (
              <tr key={b.id} className={b.active ? 'ai-row-active' : ''}>
                <td><input type="radio" name="ai-active" checked={b.active}
                  onChange={() => activate(b.id)} title="Activer ce backend" /></td>
                <td>{b.id}</td>
                <td>{b.provider}</td>
                <td>{b.model}</td>
                <td className="ai-key-cell">
                  {b.key_configured ? (
                    <span className="ai-key-ok">clé ✓ <button type="button" className="ai-link"
                      onClick={() => removeKey(b.id)}>retirer</button></span>
                  ) : (
                    <span className="ai-key-set">
                      <input type="password" placeholder="clé API" value={keyDrafts[b.id] || ''}
                        onChange={(e) => setKeyDrafts((p) => ({ ...p, [b.id]: e.target.value }))} />
                      <button type="button" className="ai-btn" onClick={() => saveKey(b.id)}>Enregistrer</button>
                    </span>
                  )}
                </td>
                <td className="ai-test-cell">
                  <div className="ai-test-row">
                    <input type="text" placeholder="prompt (ou ping)" value={askDrafts[b.id] || ''}
                      onChange={(e) => setAskDrafts((p) => ({ ...p, [b.id]: e.target.value }))} />
                    <button type="button" className="ai-btn"
                      disabled={tests[b.id] && tests[b.id].phase === 'testing'}
                      onClick={() => test(b.id)}>Test</button>
                  </div>
                  <TestResult state={tests[b.id]} />
                </td>
                <td><button type="button" className="ai-btn ai-btn-danger"
                  onClick={() => del(b.id)}>Suppr.</button></td>
              </tr>
            ))}
          </tbody>
        </table>

        <div className="ai-catalog">
          <h3>Providers disponibles <span className="ai-catalog-count">{providers.length}</span></h3>
          {providers.length === 0 ? (
            <div className="ai-catalog-hint" style={{ display: 'flex', alignItems: 'center', gap: '0.7rem', flexWrap: 'wrap', color: 'var(--status-warning)' }}>
              <span>Liste vide — le catalogue n'a pas pu être chargé (backend injoignable ?).</span>
              <button type="button" className="ai-btn" onClick={loadProviders}>Réessayer</button>
            </div>
          ) : (
            <>
              <p className="ai-catalog-hint">
                Clique un provider pour le pré-remplir dans le formulaire ci-dessous. ✓ = clé déjà
                détectée (variable d'environnement) ; sinon, colle la clé après avoir créé le backend.
              </p>
              <div className="ai-catalog-chips">
                {providers.map((p) => (
                  <button type="button" key={p.id}
                    className={'ai-chip' + (p.id === form.provider ? ' active' : '') + (p.env_present ? ' has-key' : '')}
                    onClick={() => selectProvider(p.id)}
                    title={p.env_present ? ('Clé via ' + (p.env_key || 'env') + ' présente') : 'Clé à fournir'}>
                    {p.label}{p.env_present ? ' ✓' : ''}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>

        <form className="ai-form" onSubmit={create}>
          <h3>Ajouter un backend</h3>
          <div className="ai-form-grid">
            <label>Id
              <input type="text" value={form.id}
                onChange={(e) => setForm((p) => ({ ...p, id: e.target.value }))} required />
            </label>
            <label>Provider
              <select value={form.provider} onChange={(e) => selectProvider(e.target.value)}>
                {providers.map((p) => (
                  <option key={p.id} value={p.id}>{p.label}{p.env_present ? ' ✓' : ''}</option>
                ))}
              </select>
            </label>
            {baseUrlMode !== null ? (
              <label>Base URL{baseUrlMode === 'optional' ? ' (option.)' : ''}
                <input type="text" placeholder="http://localhost:11434/v1" value={form.base_url}
                  onChange={(e) => setForm((p) => ({ ...p, base_url: e.target.value }))}
                  required={baseUrlMode === 'required'} />
              </label>
            ) : null}
            <label>Modèle
              {provModels.length > 0 ? (
                <select value={modelIsCustom ? CUSTOM_MODEL : form.model}
                  onChange={(e) => setForm((p) => ({ ...p, model: e.target.value === CUSTOM_MODEL ? '' : e.target.value }))}>
                  {provModels.map((m) => <option key={m} value={m}>{m}</option>)}
                  <option value={CUSTOM_MODEL}>— custom… —</option>
                </select>
              ) : (
                <input type="text" placeholder="id du modèle" value={form.model}
                  onChange={(e) => setForm((p) => ({ ...p, model: e.target.value }))} />
              )}
            </label>
            {modelIsCustom ? (
              <label>Modèle (custom)
                <input type="text" value={form.model}
                  onChange={(e) => setForm((p) => ({ ...p, model: e.target.value }))} />
              </label>
            ) : null}
          </div>
          <div className="ai-key-hint">{keyHint}</div>
          <button type="submit" className="ai-btn ai-btn-primary">Créer le backend</button>
        </form>
      </div>
    </div>
  );
}
