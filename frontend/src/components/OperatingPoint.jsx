import React, { useEffect, useMemo, useState } from 'react';
import { useTranslation, Trans } from 'react-i18next';
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
  const { t } = useTranslation('operating');
  if (!row) return null;
  const cells = [
    { k: 'tp', label: t('confusion.tp'), v: row.tp, cls: 'op-cell-good' },
    { k: 'fn', label: t('confusion.fn'), v: row.fn, cls: 'op-cell-bad' },
    { k: 'fp', label: t('confusion.fp'), v: row.fp, cls: 'op-cell-warn' },
    { k: 'tn', label: t('confusion.tn'), v: row.tn, cls: 'op-cell-good' },
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
  const { t } = useTranslation('operating');
  if (!row) return null;
  const items = [
    [t('metric.recall'), pct(row.recall)],
    [t('metric.precision'), pct(row.precision)],
    [t('metric.specificity'), pct(row.specificity)],
    [t('metric.fpr'), pct(row.fpr)],
    [t('metric.fbeta'), num(row.fbeta)],
    [t('metric.alerts'), num(row.alerts) + ' (' + pct(row.alert_rate) + ')'],
    [t('metric.cost'), num(row.cost)],
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
  const { t } = useTranslation('operating');
  if (!reco) return null;
  const labels = {
    min_cost: t('reco.minCost'), max_fbeta: t('reco.maxFbeta'), youden: t('reco.youden'), fpr_1pct: t('reco.fprBudget'),
  };
  return (
    <div className="op-reco">
      <span className="op-reco-lbl">{t('reco.label')}</span>
      {Object.entries(labels).map(([k, lbl]) => (
        reco[k] !== undefined ? (
          <button key={k} type="button" className="op-chip" onClick={() => onPick(reco[k])}
            title={t('reco.applyThreshold', { value: reco[k] })}>
            {lbl} · {reco[k]}
          </button>
        ) : null
      ))}
    </div>
  );
}

function Calibration({ calib }) {
  const { t } = useTranslation('operating');
  if (!calib) return null;
  return (
    <div className="op-block">
      <h6>{t('calibration.title')}</h6>
      <div className="op-inline">
        <span>ECE : <strong>{num(calib.ece)}</strong></span>
        <span>Brier : <strong>{num(calib.brier)}</strong></span>
      </div>
      <p className="op-note">{t('calibration.note')}</p>
    </div>
  );
}

function RobustMetrics({ robust }) {
  const { t } = useTranslation('operating');
  if (!robust) return null;
  return (
    <div className="op-block">
      <h6>{t('robust.title')}</h6>
      <div className="op-inline">
        <span>MCC : <strong>{num(robust.mcc)}</strong></span>
        <span>{t('robust.balancedAccuracy')} : <strong>{num(robust.balanced_accuracy)}</strong></span>
        <span>{t('robust.cohenKappa')} : <strong>{num(robust.cohen_kappa)}</strong></span>
      </div>
    </div>
  );
}

function AlertBudget({ rows }) {
  const { t } = useTranslation('operating');
  if (!rows || !rows.length) return null;
  return (
    <div className="op-block">
      <h6>{t('alertBudget.title')}</h6>
      <table className="diag-table">
        <thead><tr><th>{t('alertBudget.th.k')}</th><th>{t('alertBudget.th.precisionAtK')}</th><th>{t('alertBudget.th.detectionAtK')}</th><th>{t('alertBudget.th.truePositives')}</th></tr></thead>
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
  const { t } = useTranslation('operating');
  if (!pb || !pb.sections) return null;
  return (
    <div className="op-playbook">
      <h6>{t('playbook.title')}</h6>
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
  const { t } = useTranslation('operating');
  if (!rows || !rows.length) return null;
  return (
    <div className="op-block">
      <h6>{t('anomalyBudget.title')}</h6>
      <table className="diag-table">
        <thead><tr><th>{t('anomalyBudget.th.quantile')}</th><th>{t('anomalyBudget.th.scoreThreshold')}</th><th>{t('anomalyBudget.th.alerts')}</th><th>{t('anomalyBudget.th.alertsPer1000')}</th></tr></thead>
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
  const { t } = useTranslation('operating');
  if (!bands || !bands.length) return null;
  return (
    <div className="op-block">
      <h6>{t('tolerance.title')}</h6>
      <p className="op-note">
        <Trans i18nKey="tolerance.mae" ns="operating" components={{ strong: <strong /> }} values={{ mae: num(mae) }} />
      </p>
      <table className="diag-table">
        <thead><tr><th>{t('tolerance.th.tolerance')}</th><th>{t('tolerance.th.withinBand')}</th></tr></thead>
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
  const { t } = useTranslation('operating');
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
        <div className="substep-bar"><h5>{t('title')}</h5></div>
        <p className="muted">{op && op.reason ? op.reason : t('notApplicable')}</p>
      </div>
    );
  }

  return (
    <div className="op-panel">
      <div className="substep-bar">
        <h5>{t('titleSoc')}{loading ? ' …' : ''}</h5>
      </div>

      {mode === 'multiclass_ovr' && op.classes ? (
        <div className="op-focus">
          <label>{t('focusLabel')}</label>
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
              ? t('context.escalate', { cls: op.focus_class || '?' })
              : t('context.positiveClass', { cls: op.positive_class || '1' })}
          </p>

          <div className="op-controls">
            <div className="op-slider">
              <label>{t('slider.label')} <strong>{Number(threshold).toFixed(3)}</strong></label>
              <input type="range" min={0} max={1} step={0.005} value={threshold}
                onChange={(e) => setThreshold(parseFloat(e.target.value))} />
              <div className="op-slider-ends"><span>{t('slider.allAlert')}</span><span>{t('slider.noAlert')}</span></div>
            </div>
            <div className="op-costs">
              <label>{t('cost.fn')}
                <input type="number" min={0} value={costFn}
                  onChange={(e) => setCostFn(Math.max(0, parseFloat(e.target.value) || 0))} />
              </label>
              <label>{t('cost.fp')}
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
