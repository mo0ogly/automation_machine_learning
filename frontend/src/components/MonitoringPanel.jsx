import React, { useState } from 'react';
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

function DriftTable({ features }) {
  if (!features || !features.length) return null;
  const top = features.slice(0, 12);
  return (
    <table className="diag-table mon-table">
      <thead><tr><th>Variable</th><th>PSI</th><th>KS (p)</th><th>Niveau</th></tr></thead>
      <tbody>
        {top.map((f) => (
          <tr key={f.feature}>
            <td>{f.feature}</td>
            <td>{f.psi}</td>
            <td>{f.ks_p}</td>
            <td><span className={'mon-lvl mon-lvl-' + f.level}>{LEVEL_LABEL[f.level] || f.level}</span></td>
          </tr>
        ))}
      </tbody>
    </table>
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
                (jit.tolerance * 100) + '%) dès un bruit de ' + (jit.breaking_epsilon * 100) +
                '% de l\'écart-type.'
              : 'Aucune rupture : les verdicts tiennent jusqu\'à ' +
                (jit.curve && jit.curve.length
                  ? (jit.curve[jit.curve.length - 1].epsilon * 100) + '% de l\'écart-type de bruit.'
                  : 'l\'amplitude maximale testée.')}
          </p>
          <table className="diag-table mon-table">
            <thead><tr><th>Bruit (% écart-type)</th><th>Bascule moyenne</th><th>Min–max</th></tr></thead>
            <tbody>
              {(jit.curve || []).map((c) => (
                <tr key={c.epsilon}>
                  <td>{c.epsilon * 100}%</td>
                  <td>{pct(c.flip_rate)}</td>
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

  const upload = (e) => {
    const file = e.target.files && e.target.files[0];
    if (!file || !sessionId) return;
    const fd = new FormData();
    fd.append('file', file);
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

  return (
    <div className="mon-panel">
      <p className="mon-intro">
        Chargez un nouveau lot de données (mêmes colonnes que l'entraînement) pour mesurer la
        dérive vs le jeu d'entraînement : le vrai risque d'un détecteur en production n'est pas
        matériel mais la <strong>dérive</strong> (données et concept).
      </p>
      <label className="btn btn-secondary mon-upload">
        {busy ? 'Analyse…' : 'Charger un lot à surveiller (CSV)'}
        <input type="file" accept=".csv,text/csv" hidden onChange={upload} disabled={busy} />
      </label>
      {err ? <div className="warn-text">{err}</div> : null}

      {report && report.available ? (
        <div className="mon-report">
          <div className="mon-head">
            <span className={'mon-badge mon-badge-' + report.overall}>{overallLabel(report.overall)}</span>
            <span className="mon-sub">{report.n_batch} lignes vs {report.n_reference} de référence</span>
          </div>

          <h6>Dérive des données (PSI + Kolmogorov-Smirnov)</h6>
          <p className="mon-note">
            {dd.n_major} variable(s) en dérive majeure, {dd.n_moderate} modérée(s) sur {dd.n_features}.
          </p>
          <DriftTable features={dd.features} />

          <h6>Dérive de concept (distribution des prédictions)</h6>
          {pd && pd.kind === 'categorical' ? (
            <p className="mon-note">
              Distance de variation totale = {pd.total_variation} (niveau {LEVEL_LABEL[pd.level] || pd.level}).
              Un saut du taux de la classe positive = le « normal » du détecteur a bougé.
            </p>
          ) : pd && pd.kind === 'regression' ? (
            <p className="mon-note">PSI des prédictions = {pd.psi} · moyenne {pd.ref_mean} → {pd.cur_mean}.</p>
          ) : <p className="mon-note">Indisponible.</p>}

          <h6>Reproductibilité de l'inférence</h6>
          {rp && rp.available ? (
            <p className="mon-note">
              Déterminisme : <strong>{rp.deterministic ? 'OK' : 'ÉCHEC'}</strong>
              {rp.consistent !== undefined
                ? ' · cohérence avec l\'évaluation : ' + (rp.consistent ? 'OK' : 'divergence')
                : ''}
              {rp.recorded_metric !== undefined
                ? ' (' + rp.recorded_metric + ' → ' + rp.recomputed_metric + ')' : ''}.
              {' '}C'est la version mesurable du « jitter » : un écart ici = corruption silencieuse du pipeline.
            </p>
          ) : <p className="mon-note">{(rp && rp.reason) || 'Indisponible.'}</p>}

          <h6>Re-calibration du seuil</h6>
          {rc && rc.available ? (
            <p className="mon-note">
              Sur ce lot, seuil coût-minimal recommandé = <strong>{rc.recommended_threshold}</strong>
              {' '}(rappel {pct(rc.recall)}, précision {pct(rc.precision)}, FPR {pct(rc.fpr)}).
              Comparez au seuil déployé : s'il a bougé, re-calibrez.
            </p>
          ) : <p className="mon-note">{(rc && rc.reason) || 'Lot non labellisé.'}</p>}

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
    </div>
  );
}
