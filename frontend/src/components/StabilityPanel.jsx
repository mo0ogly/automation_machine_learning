import React, { useState } from 'react';

// Advanced stability analyses (POST /stability/{analysis}) — five deterministic
// protocols beyond the jitter curve. The backend returns a uniform display
// contract (verdict + summary rows + notes + one figure), so a single generic
// card renders all of them.

const VERDICT_LABEL = { stable: 'Stable', sensible: 'Sensible', instable: 'INSTABLE', info: 'Diagnostic' };
const VERDICT_BADGE = { stable: 'stable', sensible: 'moderate', instable: 'major', info: 'stable' };

const ANALYSES = [
  {
    id: 'numerical',
    title: 'Jitter numérique (float32 vs float64, threads)',
    desc: "La seule forme logicielle mesurable du « jitter matériel » : re-scorer en float32 vs "
      + "float64 et sous un seul thread BLAS, compter les verdicts qui basculent.",
  },
  {
    id: 'margin',
    title: 'Analyse de marge (population à risque)',
    desc: "Distance de chaque verdict au seuil de décision : quelle part de la population une "
      + "perturbation quelconque ferait basculer en premier. Déterministe, sans échantillonnage.",
  },
  {
    id: 'churn',
    title: 'Churn de ré-entraînement (instabilité structurelle)',
    desc: "Ré-apprendre le même modèle avec des seeds différentes et mesurer le désaccord des "
      + "verdicts : l'instabilité du modèle lui-même, pas de l'inférence.",
  },
  {
    id: 'conformal',
    title: 'Prédiction conforme (couverture garantie)',
    desc: "Ensembles/intervalles de prédiction avec garantie de couverture finite-sample (sous "
      + "échangeabilité) : isole les verdicts statistiquement ambigus à router vers un analyste.",
  },
  {
    id: 'smoothing',
    title: 'Robustesse certifiée (randomized smoothing)',
    desc: "Certificat de Cohen et al. (ICML 2019) : rayon L2 dans lequel le verdict du "
      + "classifieur lissé ne peut pas changer, avec borne de confiance Clopper-Pearson.",
  },
];

function AnalysisCard({ apiBase, sessionId, meta }) {
  const [rep, setRep] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  const run = () => {
    if (!sessionId || busy) return;
    setBusy(true); setErr(null);
    fetch(apiBase + '/api/session/' + sessionId + '/stability/' + meta.id, { method: 'POST' })
      .then((r) => (r.ok ? r.json() : r.json().then((d) => Promise.reject(d.detail || r.status))))
      .then((d) => setRep(d))
      .catch((c) => setErr(typeof c === 'string' ? c : 'Analyse indisponible.'))
      .finally(() => setBusy(false));
  };

  return (
    <div className="stab-card">
      <div className="stab-head">
        <h6>{meta.title}</h6>
        <button className="btn btn-secondary stab-run" onClick={run} disabled={busy || !sessionId}>
          {busy ? 'Analyse…' : 'Lancer'}
        </button>
      </div>
      <p className="mon-intro">{meta.desc}</p>
      {err ? <div className="warn-text">{err}</div> : null}
      {rep && rep.available ? (
        <div className="mon-report">
          <div className="mon-head">
            <span className={'mon-badge mon-badge-' + (VERDICT_BADGE[rep.verdict] || 'stable')}>
              {VERDICT_LABEL[rep.verdict] || rep.verdict}
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
          {rep.plots && rep.plots.length ? (
            <div className="plots-grid mon-plots">
              {rep.plots.map((p, i) => {
                const src = typeof p === 'string' ? p : p.img;
                const cap = typeof p === 'string' ? '' : (p.caption || '');
                return (
                  <figure key={i} className="plot-fig">
                    <img src={src} alt={cap || meta.title} className="plot-img" decoding="async" />
                    {cap ? <figcaption className="plot-cap"><span className="plot-cap-txt">{cap}</span></figcaption> : null}
                  </figure>
                );
              })}
            </div>
          ) : null}
        </div>
      ) : rep && !rep.available ? (
        <div className="mon-note">{rep.reason || 'Analyse non applicable.'}</div>
      ) : null}
    </div>
  );
}

export default function StabilityPanel({ apiBase, sessionId }) {
  return (
    <div className="stab-panel">
      <h6>Analyses de stabilité avancées</h6>
      <p className="mon-intro">
        Cinq protocoles déterministes au-delà de la courbe de jitter : précision numérique,
        marges au seuil, churn de ré-entraînement, couverture conforme, rayon certifié.
        Chacun tourne sur le jeu de référence, sans upload ni ré-entraînement du modèle déployé.
      </p>
      {ANALYSES.map((meta) => (
        <AnalysisCard key={meta.id} apiBase={apiBase} sessionId={sessionId} meta={meta} />
      ))}
    </div>
  );
}
