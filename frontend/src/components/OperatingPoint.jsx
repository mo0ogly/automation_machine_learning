import React, { useEffect, useMemo, useState } from 'react';
import './operating-point.css';

// OperatingPoint — the operational (SOC / threat-intel) evaluation panel.
// Adaptive to the problem type: binary/multiclass detection get the full arsenal
// (threshold slider, cost of errors, business confusion matrix, calibration,
// alert budget, SOC playbook); anomaly gets an alert-budget table; regression
// gets tolerance bands; clustering is not applicable.
//
// The threshold slider recomputes the confusion matrix CLIENT-SIDE from the
// pre-computed sweep (instant, no round-trip). Changing the error costs or the
// focus class refetches /operating-point for an authoritative playbook.

function pct(v) {
  if (v === null || v === undefined || isNaN(v)) return '—';
  return (v * 100).toFixed(1) + '%';
}
function num(v) {
  if (v === null || v === undefined || isNaN(v)) return '—';
  return String(v);
}

function nearestRow(sweep, t) {
  if (!sweep || !sweep.length) return null;
  let best = sweep[0];
  let bestD = Infinity;
  for (const r of sweep) {
    const d = Math.abs(r.threshold - t);
    if (d < bestD) { bestD = d; best = r; }
  }
  return best;
}

// Business-labelled 2x2 confusion matrix (attack vs normal).
function ConfusionGrid({ row }) {
  if (!row) return null;
  const cells = [
    { k: 'tp', label: 'Détection correcte', v: row.tp, cls: 'op-cell-good' },
    { k: 'fn', label: 'Attaque manquée', v: row.fn, cls: 'op-cell-bad' },
    { k: 'fp', label: 'Fausse alerte', v: row.fp, cls: 'op-cell-warn' },
    { k: 'tn', label: 'Trafic normal', v: row.tn, cls: 'op-cell-good' },
  ];
  return (
    <div className="op-confusion">
      {cells.map((c) => (
        <div key={c.k} className={'op-cell ' + c.cls}>
          <div className="op-cell-v">{num(c.v)}</div>
          <div className="op-cell-l">{c.label}</div>
        </div>
      ))}
    </div>
  );
}

function MetricCards({ row }) {
  if (!row) return null;
  const items = [
    ['Rappel (détection)', pct(row.recall)],
    ['Précision', pct(row.precision)],
    ['Spécificité', pct(row.specificity)],
    ['Taux de fausses alertes', pct(row.fpr)],
    ['F2 (rappel prioritaire)', num(row.fbeta)],
    ['Alertes', num(row.alerts) + ' (' + pct(row.alert_rate) + ')'],
    ['Coût attendu', num(row.cost)],
  ];
  return (
    <div className="op-metrics">
      {items.map(([k, v]) => (
        <div key={k} className="op-metric"><span className="op-metric-k">{k}</span><span className="op-metric-v">{v}</span></div>
      ))}
    </div>
  );
}

function RecoChips({ reco, onPick }) {
  if (!reco) return null;
  const labels = {
    min_cost: 'Coût minimal', max_fbeta: 'F2 max', youden: 'Youden J', fpr_1pct: 'Budget FPR 1%',
  };
  return (
    <div className="op-reco">
      <span className="op-reco-lbl">Points recommandés :</span>
      {Object.entries(labels).map(([k, lbl]) => (
        reco[k] !== undefined ? (
          <button key={k} type="button" className="op-chip" onClick={() => onPick(reco[k])}
            title={'Appliquer le seuil ' + reco[k]}>
            {lbl} · {reco[k]}
          </button>
        ) : null
      ))}
    </div>
  );
}

function Calibration({ calib }) {
  if (!calib) return null;
  return (
    <div className="op-block">
      <h6>Calibration des probabilités</h6>
      <div className="op-inline">
        <span>ECE : <strong>{num(calib.ece)}</strong></span>
        <span>Brier : <strong>{num(calib.brier)}</strong></span>
      </div>
      <p className="op-note">Un score de 0.8 devrait correspondre à ~80% de vrais positifs (ECE proche de 0 = fiable pour trier par score).</p>
    </div>
  );
}

function RobustMetrics({ robust }) {
  if (!robust) return null;
  return (
    <div className="op-block">
      <h6>Métriques robustes au déséquilibre</h6>
      <div className="op-inline">
        <span>MCC : <strong>{num(robust.mcc)}</strong></span>
        <span>Balanced accuracy : <strong>{num(robust.balanced_accuracy)}</strong></span>
        <span>Cohen's kappa : <strong>{num(robust.cohen_kappa)}</strong></span>
      </div>
    </div>
  );
}

function AlertBudget({ rows }) {
  if (!rows || !rows.length) return null;
  return (
    <div className="op-block">
      <h6>Budget d'alertes (file triée par score)</h6>
      <table className="diag-table">
        <thead><tr><th>k alertes revues</th><th>Précision@k</th><th>Détection@k</th><th>Vrais positifs</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.k}><td>{r.k}</td><td>{pct(r.precision_at_k)}</td><td>{pct(r.detection_at_k)}</td><td>{r.caught}/{r.total_positives}</td></tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Playbook({ pb }) {
  if (!pb || !pb.sections) return null;
  return (
    <div className="op-playbook">
      <h6>Fiche SOC / threat intel — déploiement</h6>
      {pb.sections.map((s, i) => (
        <div key={i} className="op-pb-sec">
          <div className="op-pb-h">{s.heading}</div>
          {s.text ? <p className="op-pb-t">{s.text}</p> : null}
          {s.list ? <ul className="op-pb-l">{s.list.map((x, j) => <li key={j}>{x}</li>)}</ul> : null}
        </div>
      ))}
    </div>
  );
}

function AnomalyBudget({ rows }) {
  if (!rows || !rows.length) return null;
  return (
    <div className="op-block">
      <h6>Budget d'alertes selon le seuil d'anomalie</h6>
      <table className="diag-table">
        <thead><tr><th>Quantile</th><th>Seuil de score</th><th>Alertes</th><th>Alertes / 1000</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.quantile}><td>{r.quantile}</td><td>{num(r.score_threshold)}</td><td>{r.alerts}</td><td>{r.alerts_per_1000}</td></tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ToleranceBands({ bands, mae }) {
  if (!bands || !bands.length) return null;
  return (
    <div className="op-block">
      <h6>Bandes de tolérance (fiabilité opérationnelle)</h6>
      <p className="op-note">Erreur absolue moyenne (MAE) : <strong>{num(mae)}</strong>.</p>
      <table className="diag-table">
        <thead><tr><th>Tolérance (±)</th><th>Part des prédictions dans la bande</th></tr></thead>
        <tbody>
          {bands.map((b, i) => (
            <tr key={i}><td>{num(b.tolerance)} ({b.tolerance_sigma}σ)</td><td>{pct(b.within)}</td></tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function OperatingPoint({ operational, apiBase, sessionId }) {
  const initial = operational || {};
  const [op, setOp] = useState(initial);
  const [threshold, setThreshold] = useState(() => {
    const r = initial.recommended_thresholds;
    return r && r.min_cost !== undefined ? r.min_cost : 0.5;
  });
  const [costFn, setCostFn] = useState(() => (initial.cost && initial.cost.cost_fn) || 10);
  const [costFp, setCostFp] = useState(() => (initial.cost && initial.cost.cost_fp) || 1);
  const [focusIdx, setFocusIdx] = useState(() =>
    (initial.focus_index !== undefined ? initial.focus_index : null));
  const [loading, setLoading] = useState(false);

  const mode = op.mode;
  const isThresholdMode = mode === 'binary' || mode === 'multiclass_ovr';

  // Recompute cost per swept row with the CURRENT costs (client-side, instant).
  const sweep = useMemo(() => {
    if (!isThresholdMode || !op.threshold_sweep) return null;
    return op.threshold_sweep.map((r) => ({ ...r, cost: costFn * r.fn + costFp * r.fp }));
  }, [op, costFn, costFp, isThresholdMode]);

  const currentRow = useMemo(() => nearestRow(sweep, threshold), [sweep, threshold]);
  const minCostThreshold = useMemo(() => {
    if (!sweep) return null;
    let best = sweep[0];
    for (const r of sweep) if (r.cost < best.cost) best = r;
    return best.threshold;
  }, [sweep]);

  // Refetch the authoritative analysis when costs / focus change (debounced).
  useEffect(() => {
    if (!apiBase || !sessionId) return undefined;
    const id = setTimeout(async () => {
      setLoading(true);
      try {
        const body = { threshold, cost_fn: costFn, cost_fp: costFp };
        if (focusIdx !== null) body.focus_idx = focusIdx;
        const res = await fetch(apiBase + '/api/session/' + sessionId + '/operating-point', {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
        });
        if (res.ok) setOp(await res.json());
      } catch (e) {
        // network error -> keep the last good analysis, no crash
      } finally {
        setLoading(false);
      }
    }, 350);
    return () => clearTimeout(id);
    // threshold intentionally excluded: it is handled client-side for instant feedback
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [costFn, costFp, focusIdx]);

  if (!op || op.applicable === false) {
    return (
      <div className="op-panel">
        <div className="substep-bar"><h5>Point de fonctionnement opérationnel</h5></div>
        <p className="muted">{op && op.reason ? op.reason : 'Analyse opérationnelle non applicable à ce modèle.'}</p>
      </div>
    );
  }

  return (
    <div className="op-panel">
      <div className="substep-bar">
        <h5>Point de fonctionnement opérationnel (SOC / threat intel){loading ? ' …' : ''}</h5>
      </div>

      {mode === 'multiclass_ovr' && op.classes ? (
        <div className="op-focus">
          <label>Classe à escalader (une-contre-le-reste) :</label>
          <select value={focusIdx === null ? '' : focusIdx}
            onChange={(e) => setFocusIdx(parseInt(e.target.value, 10))}>
            {op.classes.map((c, i) => <option key={i} value={i}>{c}</option>)}
          </select>
        </div>
      ) : null}

      {isThresholdMode ? (
        <>
          <p className="op-context">
            {mode === 'multiclass_ovr'
              ? 'Escalade « ' + (op.focus_class || '?') + ' » vs le reste.'
              : 'Classe positive : ' + (op.positive_class || '1') + '.'}
          </p>

          <div className="op-controls">
            <div className="op-slider">
              <label>Seuil de décision : <strong>{Number(threshold).toFixed(3)}</strong></label>
              <input type="range" min={0} max={1} step={0.005} value={threshold}
                onChange={(e) => setThreshold(parseFloat(e.target.value))} />
              <div className="op-slider-ends"><span>tout est alerte</span><span>rien n'est alerte</span></div>
            </div>
            <div className="op-costs">
              <label>Coût attaque manquée (FN)
                <input type="number" min={0} value={costFn}
                  onChange={(e) => setCostFn(Math.max(0, parseFloat(e.target.value) || 0))} />
              </label>
              <label>Coût fausse alerte (FP)
                <input type="number" min={0} value={costFp}
                  onChange={(e) => setCostFp(Math.max(0, parseFloat(e.target.value) || 0))} />
              </label>
            </div>
          </div>

          <RecoChips
            reco={{ ...op.recommended_thresholds, min_cost: minCostThreshold ?? op.recommended_thresholds.min_cost }}
            onPick={setThreshold} />
          <ConfusionGrid row={currentRow} />
          <MetricCards row={currentRow} />
          <Calibration calib={op.calibration} />
          <RobustMetrics robust={op.robust_metrics} />
          <AlertBudget rows={op.alert_budget} />
        </>
      ) : null}

      {mode === 'anomaly' ? <AnomalyBudget rows={op.budget_curve} /> : null}
      {mode === 'regression' ? <ToleranceBands bands={op.tolerance_bands} mae={op.mae} /> : null}

      <Playbook pb={op.soc_playbook} />
    </div>
  );
}
