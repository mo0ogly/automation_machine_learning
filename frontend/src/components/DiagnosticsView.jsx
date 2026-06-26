import React from 'react';

const LABELS = {
  overview: "Vue d'ensemble",
  overview_after: "Vue d'ensemble (après)",
  missing_by_column: 'Valeurs manquantes par colonne',
  constant_columns: 'Colonnes constantes',
  outliers_iqr: 'Valeurs aberrantes (IQR)',
  skewness: 'Asymétrie',
  cardinality: 'Cardinalité catégorielle',
  high_correlation_pairs: 'Paires très corrélées',
  target_correlation: 'Corrélation avec la cible',
  leakage_candidates: 'Suspects de fuite',
  target_distribution: 'Distribution de la cible',
  metrics: 'Métriques',
  valeurs_categorielles: 'Valeurs distinctes (catégorielles)',
  lignes_extremes: 'Lignes extrêmes (cible élevée)',
  analyse_descriptive: 'Analyse descriptive (par type)',
};

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
  const label = LABELS[name] || name;
  if (value === null || value === undefined) return null;
  if (Array.isArray(value) && value.length === 0) {
    return (
      <div className="diag-block">
        <h5>{label}</h5><p className="muted">aucun</p>
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
  if (!diagnostics || Object.keys(diagnostics).length === 0) {
    return <p className="muted">Pas de diagnostics disponibles.</p>;
  }
  if (diagnostics.ready === false) {
    return <p className="warn-text">{diagnostics.reason || 'Étape amont requise.'}</p>;
  }
  return (
    <div className="diag-grid">
      {Object.entries(diagnostics)
        .filter(([k]) => !SKIP.has(k))
        .map(([k, v]) => <Block key={k} name={k} value={v} />)}
    </div>
  );
}
