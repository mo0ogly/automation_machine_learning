import React, { useState, useEffect, useCallback } from 'react';
import { useTranslation, Trans } from 'react-i18next';
import InferenceSettings from './InferenceSettings';
import AiBackendForm from './AiBackendForm';
import './ai-cockpit.css';

// Settings window for multi-provider AI backends (mirrors recette_IA_agents):
// list / activate / key (write-only) / test / delete + a guided create form
// (AiBackendForm) whose dropdowns are built from the server-side provider catalog
// (single source of truth). A health indicator probes the active backend live.
function TestResult({ state }) {
  const { t } = useTranslation('aiBackends');
  if (!state) return null;
  if (state.phase === 'testing') return <span className="ai-test-pending">{t('testPending')}</span>;
  if (state.phase === 'ok') return <span className="ai-test-ok">{t('testOk', { ms: state.ms, text: state.text })}</span>;
  return <span className="ai-test-err">{t('testErr', { ms: state.ms, error: state.error })}</span>;
}

function HealthBadge({ state }) {
  const { t } = useTranslation('aiBackends');
  if (!state) return null;
  if (state.phase === 'checking') return <span className="ai-health-dot checking" title={t('checking')} />;
  if (!state.configured) return <span className="ai-health-txt muted">{t('noActiveBackend')}</span>;
  if (state.ok) {
    return <span className="ai-health-txt ok"><span className="ai-health-dot ok" />
      {t('healthResponds', { provider: state.provider, model: state.model, ms: state.latency_ms })}</span>;
  }
  return <span className="ai-health-txt bad"><span className="ai-health-dot bad" />
    {t('healthNoResponse', { provider: state.provider || t('backendFallback'), error: state.error || t('errorFallback') })}</span>;
}

export default function AiBackendsPanel({ apiBase, onClose, onChanged }) {
  const { t } = useTranslation('aiBackends');
  const [providers, setProviders] = useState([]);
  const [backends, setBackends] = useState([]);
  const [err, setErr] = useState(null);
  const [keyDrafts, setKeyDrafts] = useState({});
  const [askDrafts, setAskDrafts] = useState({});
  const [tests, setTests] = useState({});
  const [openParams, setOpenParams] = useState(null);
  const [paramDrafts, setParamDrafts] = useState({});
  const [health, setHealth] = useState(null);

  const refresh = useCallback(async () => {
    try {
      const b = await fetch(apiBase + '/api/ai/backends').then((r) => r.json());
      setBackends(b.backends || []);
    } catch (e) { setErr(t('backendsUnreachable')); }
  }, [apiBase, t]);

  const loadProviders = useCallback(async () => {
    try {
      const d = await fetch(apiBase + '/api/ai/providers').then((r) => r.json());
      setProviders(d.providers || []);
      setErr(null);
    } catch (e) {
      setProviders([]);
      setErr(t('catalogUnreachable'));
    }
  }, [apiBase, t]);

  const checkHealth = useCallback(async () => {
    setHealth({ phase: 'checking' });
    try {
      const d = await fetch(apiBase + '/api/ai/health').then((r) => r.json());
      setHealth({ phase: 'done', ...d });
    } catch (e) {
      setHealth({ phase: 'done', configured: true, ok: false, error: t('unreachable') });
    }
  }, [apiBase, t]);

  useEffect(() => { loadProviders(); refresh(); }, [loadProviders, refresh]);
  // Probe the active backend once on open so the operator sees its status upfront.
  useEffect(() => { checkHealth(); }, [checkHealth]);

  const changed = async () => {
    await refresh();
    await checkHealth();
    if (onChanged) await onChanged();
  };

  const del = async (id) => {
    if (!window.confirm(t('confirmDelete', { id }))) return;
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
    if (!window.confirm(t('confirmRemoveKey', { id }))) return;
    await fetch(apiBase + '/api/ai/backends/' + id + '/secret', { method: 'DELETE' });
    await changed();
  };
  const activate = async (id) => {
    await fetch(apiBase + '/api/ai/active',
      { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id }) });
    await changed();
  };
  const toggleParams = (b) => {
    if (openParams === b.id) { setOpenParams(null); return; }
    setParamDrafts((p) => ({ ...p, [b.id]: { ...(b.params || {}) } }));
    setOpenParams(b.id);
  };
  const saveParams = async (id) => {
    await fetch(apiBase + '/api/ai/backends/' + id + '/params',
      { method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ params: paramDrafts[id] || {} }) });
    setOpenParams(null);
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
      setTests((p) => ({ ...p, [id]: { phase: 'error', ms: 0, error: t('unreachable') } }));
    }
  };

  return (
    <div className="ai-modal-overlay" onClick={onClose}>
      <div className="ai-modal glass-panel" onClick={(e) => e.stopPropagation()}>
        <div className="ai-modal-head">
          <h2>{t('modalTitle')}</h2>
          <button type="button" className="ai-modal-close" onClick={onClose} aria-label={t('close')}>×</button>
        </div>
        <p className="ai-modal-note">{t('modalNote')}</p>

        <div className="ai-health-bar">
          <span className="ai-health-label">{t('activeHealth')}</span>
          <HealthBadge state={health} />
          <button type="button" className="ai-btn ai-health-check"
            disabled={health && health.phase === 'checking'} onClick={checkHealth}>{t('check')}</button>
        </div>

        {err ? <div className="banner banner-block">{err}</div> : null}

        {backends.length === 0 ? (
          <div className="ai-onboard">
            <Trans i18nKey="onboard" ns="aiBackends" components={{ strong: <strong /> }} />
          </div>
        ) : (
          <table className="ai-table">
            <thead>
              <tr><th>{t('colActive')}</th><th>{t('colId')}</th><th>{t('colProvider')}</th><th>{t('colModel')}</th><th>{t('colKey')}</th><th>{t('colTest')}</th><th></th></tr>
            </thead>
            <tbody>
              {backends.map((b) => (
                <React.Fragment key={b.id}>
                <tr className={b.active ? 'ai-row-active' : ''}>
                  <td><input type="radio" name="ai-active" checked={b.active}
                    onChange={() => activate(b.id)} title={t('activateThis')} /></td>
                  <td>{b.id}</td>
                  <td>{b.provider}</td>
                  <td>{b.model}</td>
                  <td className="ai-key-cell">
                    {b.key_configured ? (
                      <span className="ai-key-ok">{t('keyOk')} <button type="button" className="ai-link"
                        onClick={() => removeKey(b.id)}>{t('remove')}</button></span>
                    ) : (
                      <span className="ai-key-set">
                        <input type="password" placeholder={t('apiKeyPlaceholder')} value={keyDrafts[b.id] || ''}
                          onChange={(e) => setKeyDrafts((p) => ({ ...p, [b.id]: e.target.value }))} />
                        <button type="button" className="ai-btn" onClick={() => saveKey(b.id)}>{t('save')}</button>
                      </span>
                    )}
                  </td>
                  <td className="ai-test-cell">
                    <div className="ai-test-row">
                      <input type="text" placeholder={t('promptPlaceholder')} value={askDrafts[b.id] || ''}
                        onChange={(e) => setAskDrafts((p) => ({ ...p, [b.id]: e.target.value }))} />
                      <button type="button" className="ai-btn"
                        disabled={tests[b.id] && tests[b.id].phase === 'testing'}
                        onClick={() => test(b.id)}>{t('test')}</button>
                    </div>
                    <TestResult state={tests[b.id]} />
                  </td>
                  <td className="ai-actions-cell">
                    <button type="button" className={'ai-btn' + (openParams === b.id ? ' ai-btn-on' : '')}
                      onClick={() => toggleParams(b)} title={t('defaultInferenceSettings')}>{t('settings')}</button>
                    <button type="button" className="ai-btn ai-btn-danger"
                      onClick={() => del(b.id)}>{t('deleteShort')}</button>
                  </td>
                </tr>
                {openParams === b.id ? (
                  <tr className="ai-params-row">
                    <td colSpan={7}>
                      <InferenceSettings apiBase={apiBase} value={paramDrafts[b.id] || {}}
                        onChange={(v) => setParamDrafts((p) => ({ ...p, [b.id]: v }))}
                        title={t('backendDefaultParams', { id: b.id })} />
                      <div className="ai-params-actions">
                        <button type="button" className="ai-btn ai-btn-primary"
                          onClick={() => saveParams(b.id)}>{t('saveSettings')}</button>
                        <button type="button" className="ai-btn" onClick={() => setOpenParams(null)}>{t('cancel')}</button>
                      </div>
                    </td>
                  </tr>
                ) : null}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        )}

        {providers.length === 0 ? (
          <div className="ai-catalog-hint ai-catalog-empty">
            <span>{t('catalogUnavailable')}</span>
            <button type="button" className="ai-btn" onClick={loadProviders}>{t('retry')}</button>
          </div>
        ) : (
          <AiBackendForm apiBase={apiBase} providers={providers} onCreated={changed} />
        )}
      </div>
    </div>
  );
}
