import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import PlotsGrid from './PlotsGrid';
import './monitoring.css';

// Advanced stability analyses (POST /stability/{analysis}) — five deterministic
// protocols beyond the jitter curve. The backend returns a uniform display
// contract (verdict + summary rows + notes + one figure), so a single generic
// card renders all of them.

const VERDICT_BADGE = { stable: 'stable', sensible: 'moderate', instable: 'major', info: 'stable' };

const ANALYSIS_IDS = ['numerical', 'margin', 'churn', 'conformal', 'smoothing'];

function AnalysisCard({ apiBase, sessionId, id }) {
  const { t } = useTranslation('stability');
  const [rep, setRep] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  const run = () => {
    if (!sessionId || busy) return;
    setBusy(true); setErr(null);
    fetch(apiBase + '/api/session/' + sessionId + '/stability/' + id, { method: 'POST' })
      .then((r) => (r.ok ? r.json() : r.json().then((d) => Promise.reject(d.detail || r.status))))
      .then((d) => setRep(d))
      .catch((c) => setErr(typeof c === 'string' ? c : t('card.unavailable')))
      .finally(() => setBusy(false));
  };

  const verdictLabel = (v) => t('verdict.' + v, v);

  return (
    <div className="stab-card">
      <div className="stab-head">
        <h6>{t('analysis.' + id + '.title')}</h6>
        <button className="btn btn-secondary stab-run" onClick={run} disabled={busy || !sessionId}>
          {busy ? t('card.running') : t('card.run')}
        </button>
      </div>
      <p className="mon-intro">{t('analysis.' + id + '.desc')}</p>
      {err ? <div className="warn-text">{err}</div> : null}
      {rep && rep.available ? (
        <div className="mon-report">
          <div className="mon-head">
            <span className={'mon-badge mon-badge-' + (VERDICT_BADGE[rep.verdict] || 'stable')}>
              {verdictLabel(rep.verdict)}
            </span>
          </div>
          <table className="diag-table mon-table">
            <tbody>
              {(rep.summary || []).map((row) => (
                <tr key={row.label}><td>{row.label}</td><td>{row.value}</td></tr>
              ))}
            </tbody>
          </table>
          {(rep.notes || []).map((n, i) => (
            <p key={i} className="mon-note">{n}</p>
          ))}
          <PlotsGrid plots={rep.plots} alt={t('analysis.' + id + '.title')} />
        </div>
      ) : rep && !rep.available ? (
        <div className="mon-note">{rep.reason || t('card.notApplicable')}</div>
      ) : null}
    </div>
  );
}

export default function StabilityPanel({ apiBase, sessionId }) {
  const { t } = useTranslation('stability');
  return (
    <div className="stab-panel">
      <h6>{t('panel.title')}</h6>
      <p className="mon-intro">{t('panel.intro')}</p>
      {ANALYSIS_IDS.map((id) => (
        <AnalysisCard key={id} apiBase={apiBase} sessionId={sessionId} id={id} />
      ))}
    </div>
  );
}
