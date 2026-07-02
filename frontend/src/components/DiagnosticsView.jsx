import React from 'react';
import { useTranslation } from 'react-i18next';

function isListOfObjects(v) {
  return Array.isArray(v) && v.length > 0 && typeof v[0] === 'object' && v[0] !== null;
}

function MiniTable({ rows }) {
  const cols = Object.keys(rows[0]);
  return (
    <table className="diag-table">
      <thead><tr>{cols.map((c) => <th key={c}>{c}</th>)}</tr></thead>
      <tbody>
        {rows.slice(0, 8).map((r, i) => (
          <tr key={i}>{cols.map((c) => <td key={c}>{String(r[c])}</td>)}</tr>
        ))}
      </tbody>
    </table>
  );
}

function KeyVals({ obj }) {
  return (
    <div className="diag-kv">
      {Object.entries(obj).map(([k, v]) => (
        <div key={k} className="diag-kv-item">
          <span>{k}</span><strong>{v === null ? '—' : String(v)}</strong>
        </div>
      ))}
    </div>
  );
}

function Block({ name, value }) {
  const { t } = useTranslation('diagnostics');
  const label = t('labels.' + name, name);
  if (value === null || value === undefined) return null;
  if (Array.isArray(value) && value.length === 0) {
    return (
      <div className="diag-block">
        <h5>{label}</h5><p className="muted">{t('none')}</p>
      </div>
    );
  }
  let body;
  if (isListOfObjects(value)) body = <MiniTable rows={value} />;
  else if (Array.isArray(value)) body = <p>{value.join(', ')}</p>;
  else if (typeof value === 'object') body = <KeyVals obj={value} />;
  else body = <strong>{String(value)}</strong>;
  return <div className="diag-block"><h5>{label}</h5>{body}</div>;
}

// Keys rendered by dedicated components (ModelLeaderboard), not the generic grid.
const SKIP = new Set(['leaderboard', 'recommended_model', 'primary_metric']);

// Generic renderer for a stage's structured diagnostics dict.
export default function DiagnosticsView({ diagnostics }) {
  const { t } = useTranslation('diagnostics');
  if (!diagnostics || Object.keys(diagnostics).length === 0) {
    return <p className="muted">{t('empty')}</p>;
  }
  if (diagnostics.ready === false) {
    return <p className="warn-text">{diagnostics.reason || t('upstreamRequired')}</p>;
  }
  return (
    <div className="diag-grid">
      {Object.entries(diagnostics)
        .filter(([k]) => !SKIP.has(k))
        .map(([k, v]) => <Block key={k} name={k} value={v} />)}
    </div>
  );
}
