import React, { useState, useEffect, useRef } from 'react';
import { useTranslation, Trans } from 'react-i18next';
import StabilityPanel from './StabilityPanel';
import PlotsGrid from './PlotsGrid';
import './monitoring.css';

// Post-deployment drift & stability monitoring. The analyst uploads a NEW batch
// of raw rows; the server compares it to the training reference and returns a
// report: data drift (PSI/KS per feature), concept drift (prediction
// distribution), reproducibility, and a re-calibrated operating point. Figures
// render inline; the surrounding AI button (StagePanel) explains the whole panel.

const JITTER_BADGE = { stable: 'stable', sensible: 'moderate', instable: 'major' };

function pct(v) {
  if (v === null || v === undefined || isNaN(v)) return '—';
  return (v * 100).toFixed(1) + '%';
}

// A fraction (of a std) rendered as a percent WITHOUT trailing binary noise:
// 0.05 * 100 === 5.000000000000001 in JS, so route it through the same rounding.
function pctEps(v) {
  if (v === null || v === undefined || isNaN(v)) return '—';
  return parseFloat((v * 100).toFixed(2)) + '%';
}

// A numbered, card-wrapped section — gives the report a visual hierarchy instead
// of a flat run of <h6> + <p>. Purely presentational; children carry the data.
function Section({ n, title, children }) {
  return (
    <section className="mon-section">
      <header className="mon-section-h">
        <span className="mon-section-n">{n}</span>
        <h6>{title}</h6>
      </header>
      {children}
    </section>
  );
}

// A compact stat tile (big number + label). `tone` tints it by severity so the
// eye lands on the drifting counts first — same visual language as the exploit
// confusion-matrix cells.
function StatTile({ value, label, tone }) {
  return (
    <div className={'mon-tile' + (tone ? ' mon-tile-' + tone : '')}>
      <span className="mon-tile-v">{value}</span>
      <span className="mon-tile-l">{label}</span>
    </div>
  );
}

// PSI thresholds are the industry convention (Populational Stability Index):
// < 0.1 stable, 0.1–0.25 moderate, > 0.25 major. The bar width saturates at 0.5
// so a wildly drifted feature doesn't blow out the column.
function PsiBar({ value, level }) {
  const num = typeof value === 'number' ? value : parseFloat(value);
  const w = isNaN(num) ? 0 : Math.max(4, Math.min(100, (num / 0.5) * 100));
  return (
    <div className="mon-psi">
      <div className={'mon-psi-bar mon-psi-' + (level || 'stable')} style={{ width: w + '%' }} />
      <span className="mon-psi-v">{value}</span>
    </div>
  );
}

function DriftTable({ features }) {
  const { t } = useTranslation('monitoring');
  if (!features || !features.length) return null;
  const top = features.slice(0, 12);
  return (
    <table className="diag-table mon-table mon-drift-table">
      <thead><tr><th>{t('th.variable')}</th><th>PSI</th><th>KS (p)</th><th>{t('th.level')}</th></tr></thead>
      <tbody>
        {top.map((f) => (
          <tr key={f.feature}>
            <td className="mon-feat">{f.feature}</td>
            <td className="mon-psi-cell"><PsiBar value={f.psi} level={f.level} /></td>
            <td>{f.ks_p}</td>
            <td><span className={'mon-lvl mon-lvl-' + f.level}>{t('level.' + f.level, f.level)}</span></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

const CAUSE_BADGE = { major: 'major', moderate: 'moderate', stable: 'stable' };

// Probable root cause of the divergence, derived server-side from the drift
// signals — separates infrastructure/environment causes from genuine data/model
// change so the analyst acts on the right layer (not "unstable → attack").
function CauseSection({ cause }) {
  const { t } = useTranslation('monitoring');
  if (!cause || !cause.available) return null;
  if (!cause.primary) {
    return (
      <div className="mon-cause">
        <h6>{t('cause.title')}</h6>
        <p className="mon-note">{cause.summary}</p>
      </div>
    );
  }
  const p = cause.primary;
  const others = (cause.causes || []).slice(1);
  return (
    <div className="mon-cause">
      <h6>{t('cause.title')}</h6>
      <div className="mon-head">
        <span className={'mon-badge mon-badge-' + (CAUSE_BADGE[p.severity] || 'moderate')}>{p.label}</span>
        <span className="mon-sub">{t('cause.confidence')} {p.confidence}</span>
      </div>
      {p.evidence && p.evidence.length ? (
        <ul className="mon-evidence">
          {p.evidence.map((e, i) => <li key={i}>{e}</li>)}
        </ul>
      ) : null}
      <p className="mon-note"><strong>{t('cause.actionLabel')}</strong> {p.action}</p>
      {others.length ? (
        <details className="mon-other-causes">
          <summary>{t('cause.others', { count: others.length })}</summary>
          {others.map((c, i) => (
            <div key={i} className="mon-other-cause">
              <span className={'mon-lvl mon-lvl-' + (CAUSE_BADGE[c.severity] || 'moderate')}>{c.label}</span>
              <span className="mon-sub"> — {t('cause.confidence')} {c.confidence}</span>
              <p className="mon-note">{c.action}</p>
            </div>
          ))}
        </details>
      ) : null}
    </div>
  );
}

// Execution environment: training-time fingerprint vs now. A version/platform
// change is an infrastructure cause to rule out before concluding data drift.
function EnvironmentSection({ environment }) {
  const { t } = useTranslation('monitoring');
  if (!environment) return null;
  const cmp = environment.comparison || {};
  const op = environment.operational;
  if (!cmp.available && !op) {
    return (
      <p className="mon-note">{t('env.noFingerprint')}</p>
    );
  }
  return (
    <>
      {cmp.changed ? (
        <>
          <p className="mon-note">{t('env.differs')}</p>
          <table className="diag-table mon-table">
            <thead><tr><th>{t('env.field')}</th><th>{t('env.training')}</th><th>{t('env.now')}</th></tr></thead>
            <tbody>
              {(cmp.diffs || []).map((d, i) => (
                <tr key={i}><td>{d.field}</td><td>{String(d.from)}</td><td>{String(d.to)}</td></tr>
              ))}
            </tbody>
          </table>
        </>
      ) : (
        <p className="mon-ok-line"><span className="mon-ok-dot" />{t('env.conform')}</p>
      )}
      {op ? (
        <p className="mon-note">{t('env.opMeta', { data: JSON.stringify(op) })}</p>
      ) : null}
    </>
  );
}

function JitterSection({ apiBase, sessionId }) {
  const { t } = useTranslation('monitoring');
  const [jit, setJit] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const alive = useRef(true);
  useEffect(() => () => { alive.current = false; }, []);

  const jitterLabel = (v) => t('jitterVerdict.' + v, v);

  const run = () => {
    if (!sessionId || busy) return;
    setBusy(true); setErr(null);
    fetch(apiBase + '/api/session/' + sessionId + '/jitter', { method: 'POST' })
      .then((r) => (r.ok ? r.json() : r.json().then((d) => Promise.reject(d.detail || r.status))))
      .then((d) => { if (alive.current) setJit(d); })
      .catch((c) => { if (alive.current) setErr(typeof c === 'string' ? c : t('jitter.unavailable')); })
      .finally(() => { if (alive.current) setBusy(false); });
  };

  let breakNote;
  if (jit && jit.breaking_epsilon !== null && jit.breaking_epsilon !== undefined) {
    breakNote = t('jitter.breakingPoint', { tol: pctEps(jit.tolerance), eps: pctEps(jit.breaking_epsilon) });
  } else if (jit) {
    const limit = jit.curve && jit.curve.length
      ? t('jitter.noiseStdSuffix', { eps: pctEps(jit.curve[jit.curve.length - 1].epsilon) })
      : t('jitter.maxAmplitude');
    breakNote = t('jitter.noBreak', { limit });
  }

  return (
    <div className="mon-jitter">
      <h6>{t('jitter.title')}</h6>
      <p className="mon-intro">
        <Trans i18nKey="jitter.intro" ns="monitoring" components={{ strong: <strong /> }} />
      </p>
      <button className="btn btn-secondary" onClick={run} disabled={busy || !sessionId}>
        {busy ? t('jitter.measuring') : t('jitter.measure')}
      </button>
      {err ? <div className="warn-text">{err}</div> : null}
      {jit && jit.available ? (
        <div className="mon-report">
          <div className="mon-head">
            <span className={'mon-badge mon-badge-' + (JITTER_BADGE[jit.verdict] || 'stable')}>
              {jitterLabel(jit.verdict)}
            </span>
            <span className="mon-sub">
              {t('jitter.refRows', { rows: jit.n_rows, repeats: jit.repeats })}
            </span>
          </div>
          <p className="mon-note">{breakNote}</p>
          <table className="diag-table mon-table mon-jit-table">
            <thead><tr><th>{t('jitter.th.noise')}</th><th>{t('jitter.th.flip')}</th><th>{t('jitter.th.minmax')}</th></tr></thead>
            <tbody>
              {(jit.curve || []).map((c) => (
                <tr key={c.epsilon}>
                  <td>{pctEps(c.epsilon)}</td>
                  <td className="mon-flip-cell">
                    <div className="mon-flip">
                      <div className="mon-flip-bar" style={{ width: Math.max(2, Math.min(100, (c.flip_rate || 0) * 100)) + '%' }} />
                      <span className="mon-flip-v">{pct(c.flip_rate)}</span>
                    </div>
                  </td>
                  <td>{pct(c.flip_min)} – {pct(c.flip_max)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <PlotsGrid plots={jit.plots} alt={t('jitter.plotAlt')} />
        </div>
      ) : jit && !jit.available ? (
        <div className="mon-note">{jit.reason || t('jitter.notApplicable')}</div>
      ) : null}
    </div>
  );
}

export default function MonitoringPanel({ apiBase, sessionId }) {
  const { t } = useTranslation('monitoring');
  const [report, setReport] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [meta, setMeta] = useState('');
  const alive = useRef(true);
  useEffect(() => () => { alive.current = false; }, []);

  const levelLabel = (lvl) => t('level.' + lvl, lvl);
  const overallLabel = (v) => (v === 'major' ? t('overall.major') : v === 'moderate' ? t('overall.moderate') : t('overall.stable'));

  const upload = (e) => {
    const file = e.target.files && e.target.files[0];
    if (!file || !sessionId) return;
    const fd = new FormData();
    fd.append('file', file);
    if (meta && meta.trim()) fd.append('metadata', meta.trim());
    setBusy(true); setErr(null); setReport(null);
    fetch(apiBase + '/api/session/' + sessionId + '/monitor', { method: 'POST', body: fd })
      .then((r) => (r.ok ? r.json() : r.json().then((d) => Promise.reject(d.detail || r.status))))
      .then((d) => { if (alive.current) setReport(d); })
      .catch((c) => { if (alive.current) setErr(typeof c === 'string' ? c : t('unavailable')); })
      .finally(() => { if (alive.current) { setBusy(false); } e.target.value = ''; });
  };

  const dd = report && report.data_drift;
  const pd = report && report.prediction_drift;
  const rp = report && report.reproducibility;
  const rc = report && report.recalibration;
  const sc = report && report.schema;

  return (
    <div className="mon-panel">
      <p className="mon-intro">
        <Trans i18nKey="intro" ns="monitoring" components={{ strong: <strong /> }} />
      </p>
      <div className="mon-toolbar">
        <label className={'btn btn-secondary mon-upload' + (busy ? ' mon-upload-busy' : '')}>
          {busy ? t('analysing') : t('uploadBatch')}
          <input type="file" accept=".csv,text/csv" hidden onChange={upload} disabled={busy} />
        </label>
      </div>
      <details className="mon-meta">
        <summary>{t('meta.summary')}</summary>
        <p className="mon-note">
          {t('meta.note')} <code>{' {"node": "gpu-03", "throttling": true, "temp_c": 82}'}</code>
        </p>
        <textarea className="mon-meta-input" rows={2} value={meta} disabled={busy}
                  onChange={(e) => setMeta(e.target.value)}
                  placeholder='{"node": "gpu-03", "throttling": true}' />
      </details>
      {err ? <div className="warn-text">{err}</div> : null}

      {report && report.available ? (
        <div className="mon-report">
          <div className={'mon-hero mon-hero-' + report.overall}>
            <div className="mon-hero-top">
              <span className={'mon-badge mon-badge-lg mon-badge-' + report.overall}>{overallLabel(report.overall)}</span>
              <span className="mon-sub">{t('heroSub', { batch: report.n_batch, ref: report.n_reference })}</span>
            </div>
            {dd ? (
              <div className="mon-tiles">
                <StatTile value={dd.n_features} label={t('tile.tracked')} />
                <StatTile value={dd.n_major} label={t('tile.majorDrift')} tone={dd.n_major > 0 ? 'major' : 'stable'} />
                <StatTile value={dd.n_moderate} label={t('tile.moderateDrift')} tone={dd.n_moderate > 0 ? 'moderate' : 'stable'} />
                <StatTile value={report.n_batch} label={t('tile.batchRows')} />
              </div>
            ) : null}
          </div>

          {sc && sc.changed ? (
            <div className="mon-schema-warn">
              <strong>{t('schema.changed')}</strong>
              {sc.missing && sc.missing.length
                ? ' ' + t('schema.missing', {
                    count: sc.missing.length,
                    list: sc.missing.slice(0, 6).join(', ') + (sc.missing.length > 6 ? '…' : ''),
                  })
                : ''}
              {sc.extra && sc.extra.length
                ? ' ' + t('schema.extra', {
                    count: sc.extra.length,
                    list: sc.extra.slice(0, 6).join(', ') + (sc.extra.length > 6 ? '…' : ''),
                  })
                : ''}
              {' '}{t('schema.artefact')}
            </div>
          ) : null}

          <CauseSection cause={report.cause} />

          <Section n="1" title={t('section.dataDrift')}>
            <p className="mon-note">
              {t('dataDrift.summary', { major: dd.n_major, moderate: dd.n_moderate, features: dd.n_features })}
            </p>
            {dd.ks_available === false ? (
              <p className="mon-note mon-warn-inline">{t('dataDrift.ksUnavailable')}</p>
            ) : null}
            <DriftTable features={dd.features} />
          </Section>

          <Section n="2" title={t('section.conceptDrift')}>
            {pd && pd.kind === 'categorical' ? (
              <p className="mon-note">
                <Trans i18nKey="concept.categorical" ns="monitoring" components={{ strong: <strong /> }}
                  values={{ tv: pd.total_variation, level: levelLabel(pd.level) }} />
              </p>
            ) : pd && pd.kind === 'regression' ? (
              <p className="mon-note">
                <Trans i18nKey="concept.regression" ns="monitoring" components={{ strong: <strong /> }}
                  values={{ psi: pd.psi, ref: pd.ref_mean, cur: pd.cur_mean }} />
              </p>
            ) : <p className="mon-note">{t('unavailableShort')}</p>}
          </Section>

          <Section n="3" title={t('section.reproducibility')}>
            {rp && rp.available ? (
              <>
                <div className="mon-chips">
                  <span className={'mon-chip ' + (rp.deterministic ? 'mon-chip-ok' : 'mon-chip-bad')}>
                    {t('repro.determinism')} : {rp.deterministic ? 'OK' : t('repro.fail')}
                  </span>
                  {rp.consistent !== undefined ? (
                    <span className={'mon-chip ' + (rp.consistent ? 'mon-chip-ok' : 'mon-chip-bad')}>
                      {t('repro.consistency')} : {rp.consistent ? 'OK' : t('repro.divergence')}
                    </span>
                  ) : null}
                  {rp.recorded_metric !== undefined ? (
                    <span className="mon-chip mon-chip-neutral">{rp.recorded_metric} → {rp.recomputed_metric}</span>
                  ) : null}
                </div>
                <p className="mon-note">{t('repro.note')}</p>
              </>
            ) : <p className="mon-note">{(rp && rp.reason) || t('unavailableShort')}</p>}
          </Section>

          <Section n="4" title={t('section.recalibration')}>
            {rc && rc.available ? (
              <>
                <div className="mon-chips">
                  <span className="mon-chip mon-chip-accent">{t('recal.threshold')} {rc.recommended_threshold}</span>
                  <span className="mon-chip mon-chip-neutral">{t('recal.recall')} {pct(rc.recall)}</span>
                  <span className="mon-chip mon-chip-neutral">{t('recal.precision')} {pct(rc.precision)}</span>
                  <span className="mon-chip mon-chip-neutral">FPR {pct(rc.fpr)}</span>
                </div>
                <p className="mon-note">{t('recal.note')}</p>
              </>
            ) : <p className="mon-note">{(rc && rc.reason) || t('recal.unlabelled')}</p>}
          </Section>

          <Section n="5" title={t('section.environment')}>
            <EnvironmentSection environment={report.environment} />
          </Section>

          <PlotsGrid plots={report.plots} alt={t('plotAlt')} />
        </div>
      ) : report && !report.available ? (
        <div className="mon-note">{report.reason || t('notApplicable')}</div>
      ) : null}

      <JitterSection apiBase={apiBase} sessionId={sessionId} />
      <StabilityPanel apiBase={apiBase} sessionId={sessionId} />
    </div>
  );
}
