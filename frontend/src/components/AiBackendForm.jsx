import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

// Guided "add a backend" form: provider + model + optional base URL + API key,
// all in one submission (create -> store key -> activate). The id is auto-derived
// from provider+model but stays editable, and a "Tester la connexion" button
// validates provider+model+key against the live endpoint BEFORE anything is
// persisted (POST /api/ai/test-config, key sent transiently, never stored).
const CUSTOM_MODEL = '__custom__';

const slugify = (s) => String(s).toLowerCase().replace(/[^a-z0-9]+/g, '-')
  .replace(/^-+|-+$/g, '').slice(0, 40);

function TestResult({ state }) {
  const { t } = useTranslation('aiBackendForm');
  if (!state) return null;
  if (state.phase === 'testing') return <span className="ai-test-pending">{t('testPending')}</span>;
  if (state.phase === 'ok') return <span className="ai-test-ok">{t('testOk', { ms: state.ms, text: state.text })}</span>;
  return <span className="ai-test-err">{t('testErr', { ms: state.ms, error: state.error })}</span>;
}

export default function AiBackendForm({ apiBase, providers, onCreated }) {
  const { t } = useTranslation('aiBackendForm');
  const [form, setForm] = useState({ id: '', provider: 'groq', model: '', base_url: '', key: '' });
  const [idTouched, setIdTouched] = useState(false);
  const [testState, setTestState] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  // Prefill the model with the provider's default once the catalog is loaded,
  // so the form opens on a ready-to-test config rather than an empty "custom".
  useEffect(() => {
    if (form.model || !providers.length) return;
    const info = providers.find((p) => p.id === form.provider);
    if (info && info.default_model) {
      setForm((p) => ({ ...p, model: info.default_model,
        id: idTouched ? p.id : slugify(p.provider + '-' + info.default_model) }));
    }
  }, [providers]);   // eslint-disable-line react-hooks/exhaustive-deps

  const selProv = providers.find((p) => p.id === form.provider);
  const baseUrlMode = selProv ? selProv.base_url : null;
  const provModels = selProv ? selProv.models : [];
  const modelIsCustom = provModels.length > 0 && !provModels.includes(form.model);

  // Keep the id in sync with provider+model until the operator edits it by hand.
  const autoId = (provider, model) => (idTouched ? form.id : slugify(provider + '-' + (model || '')));

  const pickProvider = (pid) => {
    const info = providers.find((p) => p.id === pid);
    const model = info && info.default_model ? info.default_model : '';
    setForm((p) => ({ ...p, provider: pid, model, id: idTouched ? p.id : slugify(pid + '-' + model) }));
    setTestState(null);
  };
  const setModel = (model) => setForm((p) => ({ ...p, model, id: autoId(p.provider, model) }));

  const bodyConfig = () => {
    const body = { provider: form.provider, model: form.model.trim() };
    if (baseUrlMode === 'required' || (baseUrlMode === 'optional' && form.base_url.trim())) {
      body.base_url = form.base_url.trim();
    }
    if (form.key.trim()) body.key = form.key.trim();
    return body;
  };

  const testConnection = async () => {
    if (!form.model.trim()) { setTestState({ phase: 'error', ms: 0, error: t('modelRequired') }); return; }
    setTestState({ phase: 'testing' });
    try {
      const res = await fetch(apiBase + '/api/ai/test-config', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(bodyConfig()),
      });
      const d = await res.json();
      setTestState(d.ok ? { phase: 'ok', ms: d.latency_ms, text: d.text }
        : { phase: 'error', ms: d.latency_ms || 0, error: d.error || d.detail || t('failed') });
    } catch (e) {
      setTestState({ phase: 'error', ms: 0, error: t('unreachable') });
    }
  };

  const submit = async (e) => {
    e.preventDefault();
    const id = (idTouched ? form.id : autoId(form.provider, form.model)).trim();
    if (!id) { setErr(t('idRequired')); return; }
    if (!form.model.trim()) { setErr(t('modelRequired')); return; }
    setBusy(true);
    setErr(null);
    try {
      const create = { id, ...bodyConfig() };
      const key = create.key;
      delete create.key;   // the key goes through the dedicated write-only endpoint
      const res = await fetch(apiBase + '/api/ai/backends', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(create),
      });
      const data = await res.json();
      if (!res.ok) { setErr(data.detail || t('createRefused')); setBusy(false); return; }
      if (key) {
        await fetch(apiBase + '/api/ai/backends/' + id + '/secret', {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ key }),
        });
      }
      // Activate the freshly created backend so it is usable immediately.
      await fetch(apiBase + '/api/ai/active', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id }),
      });
      setForm({ id: '', provider: 'groq', model: (providers.find((p) => p.id === 'groq') || {}).default_model || '', base_url: '', key: '' });
      setIdTouched(false);
      setTestState(null);
      if (onCreated) await onCreated();
    } catch (e2) {
      setErr(t('createFailed'));
    } finally {
      setBusy(false);
    }
  };

  const keyHint = selProv && selProv.env_key
    ? (selProv.env_present ? t('keyHintPresent', { env: selProv.env_key }) : t('keyHintAbsent', { env: selProv.env_key }))
    : t('keyHintNone');

  return (
    <form className="ai-form" onSubmit={submit}>
      <h3>{t('title')}</h3>
      {err ? <div className="banner banner-block">{err}</div> : null}
      {providers.length ? (
        <div className="ai-catalog-chips">
          {providers.map((p) => (
            <button type="button" key={p.id}
              className={'ai-chip' + (p.id === form.provider ? ' active' : '') + (p.env_present ? ' has-key' : '')}
              onClick={() => pickProvider(p.id)}
              title={p.env_present ? t('chipKeyPresent', { env: p.env_key || 'env' }) : t('chipKeyNeeded')}>
              {p.label}{p.env_present ? ' ✓' : ''}
            </button>
          ))}
        </div>
      ) : null}
      <div className="ai-form-grid">
        <label>{t('providerLabel')}
          <select value={form.provider} onChange={(e) => pickProvider(e.target.value)}>
            {providers.map((p) => (
              <option key={p.id} value={p.id}>{p.label}{p.env_present ? ' ✓' : ''}</option>
            ))}
          </select>
        </label>
        <label>{t('modelLabel')}
          {provModels.length > 0 ? (
            <select value={modelIsCustom ? CUSTOM_MODEL : form.model}
              onChange={(e) => setModel(e.target.value === CUSTOM_MODEL ? '' : e.target.value)}>
              {provModels.map((m) => <option key={m} value={m}>{m}</option>)}
              <option value={CUSTOM_MODEL}>{t('customOption')}</option>
            </select>
          ) : (
            <input type="text" placeholder={t('modelIdPlaceholder')} value={form.model}
              onChange={(e) => setModel(e.target.value)} />
          )}
        </label>
        {modelIsCustom ? (
          <label>{t('modelCustom')}
            <input type="text" value={form.model} onChange={(e) => setModel(e.target.value)} />
          </label>
        ) : null}
        {baseUrlMode !== null ? (
          <label>{t('baseUrlLabel')}{baseUrlMode === 'optional' ? t('optionalSuffix') : ''}
            <input type="text" placeholder={t('baseUrlPlaceholder')} value={form.base_url}
              onChange={(e) => setForm((p) => ({ ...p, base_url: e.target.value }))}
              required={baseUrlMode === 'required'} />
          </label>
        ) : null}
        <label>{t('apiKeyLabel')}{selProv && selProv.env_present ? t('optionalSuffix') : ''}
          <input type="password" placeholder={t('keyPlaceholder')} value={form.key}
            onChange={(e) => setForm((p) => ({ ...p, key: e.target.value }))} />
        </label>
        <label>{t('idAutoLabel')}
          <input type="text" value={idTouched ? form.id : autoId(form.provider, form.model)}
            onChange={(e) => { setIdTouched(true); setForm((p) => ({ ...p, id: e.target.value })); }} />
        </label>
      </div>
      <div className="ai-key-hint">{keyHint}</div>
      <div className="ai-form-actions">
        <button type="button" className="ai-btn" disabled={testState && testState.phase === 'testing'}
          onClick={testConnection}>{t('testConnection')}</button>
        <button type="submit" className="ai-btn ai-btn-primary" disabled={busy}>
          {busy ? t('creating') : t('createActivate')}
        </button>
        <TestResult state={testState} />
      </div>
    </form>
  );
}
