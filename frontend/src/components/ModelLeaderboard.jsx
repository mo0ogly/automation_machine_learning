import React, { useMemo, useState } from 'react';
import AssistButton from './AssistButton';
import AssistAnswer from './AssistAnswer';
import './leaderboard-extra.css';

// Model comparison leaderboard (Modelling stage) — ranked by k-fold
// cross-validation ON THE TRAIN SET (the held-out test set stays virgin until
// Evaluation). Sortable columns, mean ± std rendering, inline score bars and an
// overfit badge; the expert picks a family with "Choisir" before fine-tuning.

const LB_LABELS = {
  rmse_cv: 'RMSE (CV)', r2_cv: 'R² (CV)', r2_train: 'R² (train)',
  accuracy_cv: 'Accuracy (CV)', f1_cv: 'F1 (CV)', accuracy_train: 'Accuracy (train)',
  overfit: 'Surapprentissage',
  // Legacy sessions (pre-CV leaderboard) may still carry test-based keys.
  rmse_test: 'RMSE (test)', r2_test: 'R² (test)', accuracy_test: 'Accuracy (test)',
  f1_test: 'F1 (test)',
};

// Columns folded into another column's "± std" display rather than shown alone.
const STD_OF = { rmse_cv: 'rmse_cv_std', accuracy_cv: 'accuracy_cv_std' };
const HIDDEN = new Set(['model', 'recommended', 'rmse_cv_std', 'accuracy_cv_std', 'help']);
// 0..1 metrics that get an inline score bar.
const BAR_KEYS = new Set(['r2_cv', 'accuracy_cv', 'f1_cv', 'r2_test', 'accuracy_test', 'f1_test']);

function fmt(v) {
  if (v === null || v === undefined) return '—';
  return String(v);
}

function ScoreBar({ value }) {
  const v = Number(value);
  if (!isFinite(v)) return null;
  const pct = Math.max(0, Math.min(1, v)) * 100;
  return (
    <span className="lb-bar" aria-hidden="true">
      <span className="lb-bar-fill" style={{ width: pct + '%' }} />
    </span>
  );
}

function OverfitBadge({ value }) {
  const v = Number(value);
  if (!isFinite(v)) return <span>{fmt(value)}</span>;
  let cls = 'lb-fit lb-fit-ok';
  let label = 'sain';
  if (v > 0.1) { cls = 'lb-fit lb-fit-bad'; label = 'élevé'; }
  else if (v > 0.05) { cls = 'lb-fit lb-fit-warn'; label = 'modéré'; }
  return (
    <span>
      {v.toFixed(4)} <span className={cls}>{label}</span>
    </span>
  );
}

export default function ModelLeaderboard(props) {
  const {
    rows, metric, cvFolds, leakageFree, selected, onChoose,
    onAssist, assistBusy, assistAnswers, onApplyAssist,
  } = props;
  const [sortKey, setSortKey] = useState(null);   // null = backend ranking
  const [sortDir, setSortDir] = useState(1);

  const cols = useMemo(() => {
    if (!rows || !rows.length) return [];
    return Object.keys(rows[0]).filter((c) => !HIDDEN.has(c));
  }, [rows]);

  const sorted = useMemo(() => {
    if (!rows) return [];
    if (!sortKey) return rows;
    const copy = rows.slice();
    copy.sort((a, b) => {
      const av = Number(a[sortKey]);
      const bv = Number(b[sortKey]);
      if (!isFinite(av) || !isFinite(bv)) return 0;
      return (av - bv) * sortDir;
    });
    return copy;
  }, [rows, sortKey, sortDir]);

  if (!rows || !rows.length) return null;

  const clickSort = (c) => {
    if (sortKey === c) {
      if (sortDir === 1) { setSortDir(-1); return; }
      setSortKey(null); setSortDir(1); return;   // 3rd click: back to ranking
    }
    setSortKey(c); setSortDir(1);
  };
  const arrow = (c) => (sortKey !== c ? '' : (sortDir === 1 ? ' ▲' : ' ▼'));

  return (
    <div className="leaderboard">
      <div className="substep-bar">
        <h5>Comparaison des modèles{metric ? ' — classé par ' + metric : ''}</h5>
        {onAssist ? <AssistButton topic="leaderboard" label="Explique le classement"
          onAssist={onAssist} busy={assistBusy} /> : null}
      </div>
      <AssistAnswer topic="leaderboard" answers={assistAnswers} onApply={onApplyAssist} />
      <div className="lb-chips">
        {cvFolds ? (
          <span className="lb-chip lb-chip-cv" title="Chaque candidat est évalué par validation croisée sur le train uniquement.">
            {'CV ' + cvFolds + ' plis — jeu de test vierge'}
          </span>
        ) : null}
        {leakageFree ? (
          <span className="lb-chip lb-chip-clean" title="Encodeurs, échelles et PCA ajustés sur le train seul (préprocesseur anti-fuite).">
            prétraitement anti-fuite
          </span>
        ) : null}
      </div>
      <p className="cfg-help">
        Moyenne ± écart-type sur les plis, hyperparamètres par défaut. Cliquez un en-tête pour
        trier ; choisissez une famille — le fine-tuning affinera ses hyperparamètres ensuite.
      </p>
      <div className="coltable-scroll">
        <table className="diag-table leaderboard-table">
          <thead>
            <tr>
              <th>Modèle</th>
              {cols.map((c) => (
                <th key={c} className="lb-sortable" onClick={() => clickSort(c)}
                  title="Trier par cette colonne">
                  {(LB_LABELS[c] || c) + arrow(c)}
                </th>
              ))}
              <th />
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => {
              const isSel = selected === r.model;
              return (
                <tr key={r.model} className={r.recommended ? 'lb-best' : ''}>
                  <td className="lb-model" title={r.help || ''}>
                    {r.model}
                    {r.recommended ? <span className="lb-badge">recommandé</span> : null}
                    {r.help ? <span className="lb-model-help">{r.help}</span> : null}
                  </td>
                  {cols.map((c) => {
                    if (c === 'overfit') {
                      return <td key={c}><OverfitBadge value={r[c]} /></td>;
                    }
                    const stdKey = STD_OF[c];
                    const std = stdKey && r[stdKey] !== undefined ? r[stdKey] : null;
                    return (
                      <td key={c}>
                        <span className="lb-val">
                          {fmt(r[c])}
                          {std !== null ? <span className="lb-std">{' ± ' + std}</span> : null}
                        </span>
                        {BAR_KEYS.has(c) ? <ScoreBar value={r[c]} /> : null}
                      </td>
                    );
                  })}
                  <td>
                    {isSel ? (
                      <span className="reco-applied">choisi</span>
                    ) : (
                      <button type="button" className="coltable-btn" onClick={() => onChoose(r.model)}>Choisir</button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
