import React, { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { isCyber } from './cyber';
import './models-menu.css';

// Trained-models browser (top-right header). A model lives inside the session
// that produced it, so this is a focused, cross-session view of every session
// that carries a fitted model: download its .pkl, or open the session to
// inspect / re-run it. Data comes from /api/sessions (summary.model) — no extra
// endpoint. Reuses the .ai-modal / .ai-table styling for coherence.

function fmtDate(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' });
  } catch (e) {
    return String(iso).slice(0, 16).replace('T', ' ');
  }
}

export default function ModelsMenu({ apiBase, onClose }) {
  const { t } = useTranslation('models');
  const [models, setModels] = useState(null);
  const [error, setError] = useState(null);

  const PTYPE_LABELS = {
    regression: t('problemType.regression'), classification: t('problemType.classification'),
    clustering: t('problemType.clustering'), anomaly: t('problemType.anomaly'),
  };

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const r = await fetch(apiBase + '/api/sessions');
      const d = await r.json();
      if (!r.ok) { setError(d.detail || t('loadError')); return; }
      // Keep only sessions that carry a trained model.
      setModels((d.sessions || []).filter((s) => s.summary && s.summary.model));
    } catch (e) {
      setError(t('apiUnreachable'));
    }
  }, [apiBase, t]);

  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  // Re-open the session that owns the model: persist the pointer, then reload so
  // the Pipeline view rehydrates it (same path as the localStorage restore).
  const openSession = (id) => {
    try { localStorage.setItem('ml_session', id); } catch (e) { /* ignore */ }
    window.location.reload();
  };

  // Plain-language "what does this model do?" line. A cyber dataset gets its
  // domain phrasing (detected by filename keyword); anything else falls back to
  // a generic sentence built from the problem type + target column.
  const DOMAIN_KEYS = [
    ['promptInjection', ['prompt', 'injection']],
    ['fraud', ['fraud', 'transaction']],
    ['phishing', ['phishing']],
    ['spam', ['spam']],
    ['malware', ['malware']],
    ['intrusion', ['intrusion', 'attack', 'threat']],
    ['vuln', ['cve', 'kev', 'vuln', 'exploit']],
  ];
  const modelUse = (s) => {
    const name = (s.filename || '').toLowerCase();
    const hit = DOMAIN_KEYS.find(([, words]) => words.some((w) => name.includes(w)));
    if (hit) return t('use.' + hit[0]);
    const sm = s.summary || {};
    const pt = sm.problem_type;
    if (pt === 'classification') {
      return sm.target ? t('use.classification', { target: sm.target }) : t('use.classificationNoTarget');
    }
    if (pt === 'regression') {
      return sm.target ? t('use.regression', { target: sm.target }) : t('use.regressionNoTarget');
    }
    if (pt === 'anomaly') return t('use.anomaly');
    if (pt === 'clustering') return t('use.clustering');
    return '—';
  };

  // Re-training the same algorithm on the same dataset creates one session per
  // run — shown raw, the table drowns in duplicates. Group by dataset + algo,
  // keep the most recent session, and carry a counter of the grouped runs.
  const groupModels = (list) => {
    const byKey = new Map();
    for (const s of list) {
      const key = (s.filename || '') + '|' + ((s.summary && s.summary.model) || '');
      const cur = byKey.get(key);
      if (!cur) {
        byKey.set(key, { ...s, runs: 1 });
      } else {
        const newer = (s.updated_at || '') > (cur.updated_at || '');
        byKey.set(key, newer ? { ...s, runs: cur.runs + 1 } : { ...cur, runs: cur.runs + 1 });
      }
    }
    return [...byKey.values()].sort((a, b) => (b.updated_at || '').localeCompare(a.updated_at || ''));
  };

  // Cyber models are the heart of the thesis — surface them in a pinned section.
  // Detection by dataset-name keywords (adjustable here).
  const cyber = groupModels((models || []).filter((s) => isCyber(s.filename)));
  const others = groupModels((models || []).filter((s) => !isCyber(s.filename)));

  const renderTable = (list, cyberFlag) => (
    <table className="ai-table">
      <thead>
        <tr>
          <th>{t('columns.dataset')}</th><th>{t('columns.what')}</th>
          <th>{t('columns.algorithm')}</th><th>{t('columns.type')}</th>
          <th>{t('columns.size')}</th><th>{t('columns.modified')}</th><th>{t('columns.actions')}</th>
        </tr>
      </thead>
      <tbody>
        {list.map((s) => {
          const sm = s.summary || {};
          return (
            <tr key={s.id} className={cyberFlag ? 'cyber-row' : ''}>
              <td>
                <strong>{s.filename || t('unnamed')}</strong>
                {cyberFlag ? <span className="badge-cyber">CYBER</span> : null}
                {s.runs > 1 ? (
                  <span className="muted" title={t('runsTitle', { n: s.runs })}>
                    {' ' + t('runs', { n: s.runs })}
                  </span>
                ) : null}
              </td>
              <td>{modelUse(s)}</td>
              <td><span className="ai-key-ok">{sm.model}</span></td>
              <td>{PTYPE_LABELS[sm.problem_type] || '—'}</td>
              <td>{sm.n_rows != null ? sm.n_rows + ' × ' + sm.n_cols : '—'}</td>
              <td>{fmtDate(s.updated_at)}</td>
              <td>
                <span className="ai-test-row">
                  <a className="ai-btn ai-btn-primary" href={apiBase + '/api/session/' + s.id + '/export-bundle'}
                    target="_blank" rel="noreferrer" title={t('bundleTitle')}>{t('bundleLabel')}</a>
                  <a className="ai-btn" href={apiBase + '/api/session/' + s.id + '/download-model'}
                    target="_blank" rel="noreferrer" title={t('pklTitle')}>.pkl</a>
                  <button type="button" className="ai-btn" onClick={() => openSession(s.id)}>{t('open')}</button>
                </span>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );

  return (
    <div className="ai-modal-overlay" onClick={onClose}>
      <div className="ai-modal glass-panel models-modal" onClick={(e) => e.stopPropagation()}>
        <div className="ai-modal-head">
          <h2>{t('title')}</h2>
          <button type="button" className="ai-modal-close" onClick={onClose} title={t('close')}>×</button>
        </div>
        <p className="ai-modal-note">
          {t('note')}
        </p>
        {error ? <div className="banner banner-block mb-2">{error}</div> : null}

        {models === null ? (
          <p className="ai-empty">{t('loading')}</p>
        ) : models.length === 0 ? (
          <p className="ai-empty">
            {t('empty')}
          </p>
        ) : (
          <>
            {cyber.length ? (
              <div className="cyber-block">
                <h3 className="cyber-head">
                  <span className="badge-cyber">CYBER</span>
                  {t('cyberModels')} <span className="muted">({cyber.length})</span>
                </h3>
                {renderTable(cyber, true)}
              </div>
            ) : null}
            {others.length ? (
              <>
                <h3 className="other-head">{t('otherModels')} <span className="muted">({others.length})</span></h3>
                {renderTable(others, false)}
              </>
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}
