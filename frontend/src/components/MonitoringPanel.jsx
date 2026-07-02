import React, { useState } from 'react';
import StabilityPanel from './StabilityPanel';
import './monitoring.css';

// Post-deployment drift & stability monitoring. The analyst uploads a NEW batch
// of raw rows; the server compares it to the training reference and returns a
// report: data drift (PSI/KS per feature), concept drift (prediction
// distribution), reproducibility, and a re-calibrated operating point. Figures
// render inline; the surrounding AI button (StagePanel) explains the whole panel.

const LEVEL_LABEL = { major: 'majeure', moderate: 'modérée', none: 'stable', stable: 'stable' };
const overallLabel = (v) => (v === 'major' ? 'DÉRIVE MAJEURE' : v === 'moderate' ? 'Dérive modérée' : 'Stable');
const JITTER_LABEL = { stable: 'Stable', sensible: 'Sensible au bruit', instable: 'INSTABLE' };
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
  if (!features || !features.length) return null;
  const top = features.slice(0, 12);
  return (
    <table className="diag-table mon-table mon-drift-table">
      <thead><tr><th>Variable</th><th>PSI</th><th>KS (p)</th><th>Niveau</th></tr></thead>
      <tbody>
        {top.map((f) => (
          <tr key={f.feature}>
            <td className="mon-feat">{f.feature}</td>
            <td className="mon-psi-cell"><PsiBar value={f.psi} level={f.level} /></td>
            <td>{f.ks_p}</td>
            <td><span className={'mon-lvl mon-lvl-' + f.level}>{LEVEL_LABEL[f.level] || f.level}</span></td>
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
  if (!cause || !cause.available) return null;
  if (!cause.primary) {
    return (
      <div className="mon-cause">
        <h6>Cause probable</h6>
        <p className="mon-note">{cause.summary}</p>
      </div>
    );
  }
  const p = cause.primary;
  const others = (cause.causes || []).slice(1);
  return (
    <div className="mon-cause">
      <h6>Cause probable</h6>
      <div className="mon-head">
        <span className={'mon-badge mon-badge-' + (CAUSE_BADGE[p.severity] || 'moderate')}>{p.label}</span>
        <span className="mon-sub">confiance {p.confidence}</span>
      </div>
      {p.evidence && p.evidence.length ? (
        <ul className="mon-evidence">
          {p.evidence.map((e, i) => <li key={i}>{e}</li>)}
        </ul>
      ) : null}
      <p className="mon-note"><strong>Action :</strong> {p.action}</p>
      {others.length ? (
        <details className="mon-other-causes">
          <summary>{others.length} autre(s) cause(s) possible(s)</summary>
          {others.map((c, i) => (
            <div key={i} className="mon-other-cause">
              <span className={'mon-lvl mon-lvl-' + (CAUSE_BADGE[c.severity] || 'moderate')}>{c.label}</span>
              <span className="mon-sub"> — confiance {c.confidence}</span>
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
  if (!environment) return null;
  const cmp = environment.comparison || {};
  const op = environment.operational;
  if (!cmp.available && !op) {
    return (
      <p className="mon-note">Empreinte d'entraînement indisponible (modèle antérieur à cette version).</p>
    );
  }
  return (
    <>
      {cmp.changed ? (
        <>
          <p className="mon-note">
            L'environnement diffère de celui de l'entraînement — à écarter avant de conclure à une dérive :
          </p>
          <table className="diag-table mon-table">
            <thead><tr><th>Champ</th><th>Entraînement</th><th>Maintenant</th></tr></thead>
            <tbody>
              {(cmp.diffs || []).map((d, i) => (
                <tr key={i}><td>{d.field}</td><td>{String(d.from)}</td><td>{String(d.to)}</td></tr>
              ))}
            </tbody>
          </table>
        </>
      ) : (
        <p className="mon-ok-line"><span className="mon-ok-dot" />Conforme à l'entraînement (versions et plateforme identiques).</p>
      )}
      {op ? (
        <p className="mon-note">Métadonnées opérationnelles fournies : {JSON.stringify(op)}.</p>
      ) : null}
    </>
  );
}

function JitterSection({ apiBase, sessionId }) {
  const [jit, setJit] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  const run = () => {
    if (!sessionId || busy) return;
    setBusy(true); setErr(null);
    fetch(apiBase + '/api/session/' + sessionId + '/jitter', { method: 'POST' })
      .then((r) => (r.ok ? r.json() : r.json().then((d) => Promise.reject(d.detail || r.status))))
      .then((d) => setJit(d))
      .catch((c) => setErr(typeof c === 'string' ? c : 'Protocole jitter indisponible.'))
      .finally(() => setBusy(false));
  };

  return (
    <div className="mon-jitter">
      <h6>Stabilité sous perturbation (protocole jitter)</h6>
      <p className="mon-intro">
        Le protocole injecte un bruit gaussien croissant (fractions de l'écart-type de chaque
        variable) dans le jeu de référence, re-score, et mesure le <strong>taux de bascule</strong> des
        verdicts. Un détecteur qui bascule à 0,1&nbsp;% de bruit est instable en environnement
        critique — quel que soit le matériel qui l'exécute.
      </p>
      <button className="btn btn-secondary" onClick={run} disabled={busy || !sessionId}>
        {busy ? 'Mesure en cours…' : 'Mesurer la stabilité (jitter)'}
      </button>
      {err ? <div className="warn-text">{err}</div> : null}
      {jit && jit.available ? (
        <div className="mon-report">
          <div className="mon-head">
            <span className={'mon-badge mon-badge-' + (JITTER_BADGE[jit.verdict] || 'stable')}>
              {JITTER_LABEL[jit.verdict] || jit.verdict}
            </span>
            <span className="mon-sub">
              {jit.n_rows} lignes de référence · {jit.repeats} répétitions par amplitude
            </span>
          </div>
          <p className="mon-note">
            {jit.breaking_epsilon !== null && jit.breaking_epsilon !== undefined
              ? 'Point de rupture : les verdicts basculent au-delà de la tolérance (' +
                pctEps(jit.tolerance) + ') dès un bruit de ' + pctEps(jit.breaking_epsilon) +
                ' de l\'écart-type.'
              : 'Aucune rupture : les verdicts tiennent jusqu\'à ' +
                (jit.curve && jit.curve.length
                  ? pctEps(jit.curve[jit.curve.length - 1].epsilon) + ' de l\'écart-type de bruit.'
                  : 'l\'amplitude maximale testée.')}
          </p>
          <table className="diag-table mon-table mon-jit-table">
            <thead><tr><th>Bruit (% écart-type)</th><th>Bascule moyenne</th><th>Min–max</th></tr></thead>
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
          {jit.plots && jit.plots.length ? (
            <div className="plots-grid mon-plots">
              {jit.plots.map((p, i) => (
                <figure key={i} className="plot-fig">
                  <img src={typeof p === 'string' ? p : p.img} alt="stabilité jitter"
                       className="plot-img" decoding="async" />
                </figure>
              ))}
            </div>
          ) : null}
        </div>
      ) : jit && !jit.available ? (
        <div className="mon-note">{jit.reason || 'Protocole non applicable.'}</div>
      ) : null}
    </div>
  );
}

export default function MonitoringPanel({ apiBase, sessionId }) {
  const [report, setReport] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [meta, setMeta] = useState('');

  const upload = (e) => {
    const file = e.target.files && e.target.files[0];
    if (!file || !sessionId) return;
    const fd = new FormData();
    fd.append('file', file);
    if (meta && meta.trim()) fd.append('metadata', meta.trim());
    setBusy(true); setErr(null); setReport(null);
    fetch(apiBase + '/api/session/' + sessionId + '/monitor', { method: 'POST', body: fd })
      .then((r) => (r.ok ? r.json() : r.json().then((d) => Promise.reject(d.detail || r.status))))
      .then((d) => setReport(d))
      .catch((c) => setErr(typeof c === 'string' ? c : 'Surveillance indisponible.'))
      .finally(() => { setBusy(false); e.target.value = ''; });
  };

  const dd = report && report.data_drift;
  const pd = report && report.prediction_drift;
  const rp = report && report.reproducibility;
  const rc = report && report.recalibration;
  const sc = report && report.schema;

  return (
    <div className="mon-panel">
      <p className="mon-intro">
        Chargez un nouveau lot de données (mêmes colonnes que l'entraînement) pour mesurer la
        dérive vs le jeu d'entraînement : le vrai risque d'un détecteur en production n'est pas
        matériel mais la <strong>dérive</strong> (données et concept).
      </p>
      <div className="mon-toolbar">
        <label className={'btn btn-secondary mon-upload' + (busy ? ' mon-upload-busy' : '')}>
          {busy ? 'Analyse…' : 'Charger un lot à surveiller (CSV)'}
          <input type="file" accept=".csv,text/csv" hidden onChange={upload} disabled={busy} />
        </label>
      </div>
      <details className="mon-meta">
        <summary>Contexte d'exécution (optionnel)</summary>
        <p className="mon-note">
          Métadonnées opérationnelles du lot en JSON — utilisées pour distinguer un changement
          d'environnement d'un changement de comportement du modèle. Ex.&nbsp;:
          <code>{' {"node": "gpu-03", "throttling": true, "temp_c": 82}'}</code>
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
              <span className="mon-sub">{report.n_batch} lignes vs {report.n_reference} de référence</span>
            </div>
            {dd ? (
              <div className="mon-tiles">
                <StatTile value={dd.n_features} label="variables suivies" />
                <StatTile value={dd.n_major} label="dérives majeures" tone={dd.n_major > 0 ? 'major' : 'stable'} />
                <StatTile value={dd.n_moderate} label="dérives modérées" tone={dd.n_moderate > 0 ? 'moderate' : 'stable'} />
                <StatTile value={report.n_batch} label="lignes du lot" />
              </div>
            ) : null}
          </div>

          {sc && sc.changed ? (
            <div className="mon-schema-warn">
              <strong>Schéma différent de l'entraînement.</strong>
              {sc.missing && sc.missing.length
                ? ' ' + sc.missing.length + ' colonne(s) manquante(s) (imputées) : ' +
                  sc.missing.slice(0, 6).join(', ') + (sc.missing.length > 6 ? '…' : '') + '.'
                : ''}
              {sc.extra && sc.extra.length
                ? ' ' + sc.extra.length + ' colonne(s) en trop (ignorées) : ' +
                  sc.extra.slice(0, 6).join(', ') + (sc.extra.length > 6 ? '…' : '') + '.'
                : ''}
              {' '}Les chiffres de dérive ci-dessous sont en partie des artefacts de cette réconciliation.
            </div>
          ) : null}

          <CauseSection cause={report.cause} />

          <Section n="1" title="Dérive des données (PSI + Kolmogorov-Smirnov)">
            <p className="mon-note">
              {dd.n_major} variable(s) en dérive majeure, {dd.n_moderate} modérée(s) sur {dd.n_features}.
            </p>
            <DriftTable features={dd.features} />
          </Section>

          <Section n="2" title="Dérive de concept (distribution des prédictions)">
            {pd && pd.kind === 'categorical' ? (
              <p className="mon-note">
                Distance de variation totale = <strong>{pd.total_variation}</strong> (niveau {LEVEL_LABEL[pd.level] || pd.level}).
                Un saut du taux de la classe positive = le « normal » du détecteur a bougé.
              </p>
            ) : pd && pd.kind === 'regression' ? (
              <p className="mon-note">PSI des prédictions = <strong>{pd.psi}</strong> · moyenne {pd.ref_mean} → {pd.cur_mean}.</p>
            ) : <p className="mon-note">Indisponible.</p>}
          </Section>

          <Section n="3" title="Reproductibilité de l'inférence">
            {rp && rp.available ? (
              <>
                <div className="mon-chips">
                  <span className={'mon-chip ' + (rp.deterministic ? 'mon-chip-ok' : 'mon-chip-bad')}>
                    Déterminisme : {rp.deterministic ? 'OK' : 'ÉCHEC'}
                  </span>
                  {rp.consistent !== undefined ? (
                    <span className={'mon-chip ' + (rp.consistent ? 'mon-chip-ok' : 'mon-chip-bad')}>
                      Cohérence éval : {rp.consistent ? 'OK' : 'divergence'}
                    </span>
                  ) : null}
                  {rp.recorded_metric !== undefined ? (
                    <span className="mon-chip mon-chip-neutral">{rp.recorded_metric} → {rp.recomputed_metric}</span>
                  ) : null}
                </div>
                <p className="mon-note">
                  C'est la version mesurable du « jitter » : un écart ici = corruption silencieuse du pipeline.
                </p>
              </>
            ) : <p className="mon-note">{(rp && rp.reason) || 'Indisponible.'}</p>}
          </Section>

          <Section n="4" title="Re-calibration du seuil">
            {rc && rc.available ? (
              <>
                <div className="mon-chips">
                  <span className="mon-chip mon-chip-accent">seuil {rc.recommended_threshold}</span>
                  <span className="mon-chip mon-chip-neutral">rappel {pct(rc.recall)}</span>
                  <span className="mon-chip mon-chip-neutral">précision {pct(rc.precision)}</span>
                  <span className="mon-chip mon-chip-neutral">FPR {pct(rc.fpr)}</span>
                </div>
                <p className="mon-note">
                  Seuil coût-minimal recommandé sur ce lot. Comparez au seuil déployé : s'il a bougé, re-calibrez.
                </p>
              </>
            ) : <p className="mon-note">{(rc && rc.reason) || 'Lot non labellisé.'}</p>}
          </Section>

          <Section n="5" title="Environnement d'exécution">
            <EnvironmentSection environment={report.environment} />
          </Section>

          {report.plots && report.plots.length ? (
            <div className="plots-grid mon-plots">
              {report.plots.map((p, i) => {
                const src = typeof p === 'string' ? p : p.img;
                const cap = typeof p === 'string' ? '' : (p.caption || '');
                return (
                  <figure key={i} className="plot-fig">
                    <img src={src} alt={cap || 'figure'} className="plot-img" decoding="async" />
                    {cap ? <figcaption className="plot-cap"><span className="plot-cap-txt">{cap}</span></figcaption> : null}
                  </figure>
                );
              })}
            </div>
          ) : null}
        </div>
      ) : report && !report.available ? (
        <div className="mon-note">{report.reason || 'Surveillance non applicable.'}</div>
      ) : null}

      <JitterSection apiBase={apiBase} sessionId={sessionId} />
      <StabilityPanel apiBase={apiBase} sessionId={sessionId} />
    </div>
  );
}
