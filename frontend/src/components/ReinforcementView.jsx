import React, { useState } from 'react';
import PlotModal from './PlotModal';
import AssistButton from './AssistButton';
import AssistAnswer from './AssistAnswer';
import './components.css';

// API base: configurable at build time (Docker passes VITE_API_URL), defaults to
// the local dev backend so `npm run dev` keeps working unchanged.
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// Q-learning hyperparameters exposed to the expert (bounds mirror the backend).
const FIELDS = [
  { key: 'size', label: 'Taille de la grille', min: 3, max: 10, step: 1 },
  { key: 'episodes', label: "Nombre d'épisodes", min: 20, max: 2000, step: 20 },
  { key: 'alpha', label: "Taux d'apprentissage (alpha)", min: 0.01, max: 1, step: 0.01 },
  { key: 'gamma', label: "Facteur d'actualisation (gamma)", min: 0.5, max: 0.999, step: 0.001 },
  { key: 'epsilon', label: 'Exploration initiale (epsilon)', min: 0, max: 1, step: 0.05 },
  { key: 'n_goals', label: 'Nombre de buts', min: 1, max: 3, step: 1 },
  { key: 'n_traps', label: 'Nombre de pièges', min: 0, max: 5, step: 1 },
];
const DEFAULTS = { size: 5, episodes: 300, alpha: 0.1, gamma: 0.95, epsilon: 1.0, n_goals: 1, n_traps: 0 };

export default function ReinforcementView() {
  const [cfg, setCfg] = useState(DEFAULTS);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [zoom, setZoom] = useState(null);
  const [answers, setAnswers] = useState({});
  const [explainBusy, setExplainBusy] = useState(false);

  const setField = (k, v) => setCfg((p) => ({ ...p, [k]: v }));

  // Per-hyperparameter AI helper: explains one slider (reuses the session-free
  // assist agent via /api/rl/explain); a suggested value is one-click applicable.
  const askExplain = async (param, label) => {
    setExplainBusy(true);
    try {
      const res = await fetch(API_URL + '/api/rl/explain', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ param, label, level: 'novice', config: cfg }),
      });
      const data = await res.json();
      if (res.ok) setAnswers((p) => ({ ...p, [param]: data }));
    } catch (e) { /* explanation is non-blocking */ }
    setExplainBusy(false);
  };
  const applyRlSuggestion = (sc) => setCfg((p) => ({ ...p, ...sc }));

  const train = async () => {
    setBusy(true); setError(null);
    try {
      const res = await fetch(API_URL + '/api/rl/train', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(cfg),
      });
      const data = await res.json();
      if (!res.ok) { setError(data.detail || "Échec de l'entraînement"); setBusy(false); return; }
      setResult(data);
    } catch (e) {
      setError("Échec de l'entraînement — le backend est-il démarré ?");
    }
    setBusy(false);
  };

  return (
    <div className="lab">
      <div className="rl-intro glass-panel">
        <h2>Apprentissage par renforcement</h2>
        <p>
          Troisième paradigme : pas de jeu de données figé. Un <strong>agent</strong> apprend
          par essais-erreurs en interagissant avec un <strong>environnement</strong> (ici un
          labyrinthe <em>GridWorld</em>). À chaque pas il choisit une action, reçoit une
          <strong> récompense</strong>, et ajuste sa stratégie (algorithme <em>Q-learning</em>)
          pour maximiser la récompense cumulée. L'agent part de la case S (haut-gauche) et doit
          rejoindre un but par le chemin le plus court, en évitant les pièges.
        </p>
        <p className="rl-legend">
          Légende : <strong>S</strong> départ · <strong>BUT</strong> objectif (récompense) ·
          <strong> X</strong> piège (pénalité, fin d'épisode) · cases grises = obstacles.
        </p>
      </div>

      <div className="rl-panel glass-panel">
        <div className="rl-controls">
          {FIELDS.map((f) => (
            <div key={f.key} className="rl-field">
              <span className="rl-field-head">
                <span>{f.label} : <strong>{cfg[f.key]}</strong></span>
                <AssistButton topic={f.key} label={f.label} text="IA"
                  onAssist={askExplain} busy={explainBusy} />
              </span>
              <input type="range" min={f.min} max={f.max} step={f.step}
                value={cfg[f.key]} onChange={(e) => setField(f.key, Number(e.target.value))} />
              <AssistAnswer topic={f.key} answers={answers} onApply={applyRlSuggestion} />
            </div>
          ))}
          <button className="btn btn-primary rl-train" onClick={train} disabled={busy}>
            {busy ? 'Entraînement en cours…' : "Entraîner l'agent"}
          </button>
        </div>

        {error ? <div className="banner banner-block">{error}</div> : null}

        {result ? (
          <div className="rl-result">
            <div className="report-cards">
              {Object.entries(result.metrics).map(([k, v]) => (
                <div key={k} className="report-card">
                  <div className="report-k">{k}</div>
                  <div className="report-v">{String(v)}</div>
                </div>
              ))}
            </div>
            <div className="plots-grid">
              {result.plots.map((p, i) => (
                <figure key={i} className="plot-fig">
                  <button type="button" className="plot-thumb" title="Agrandir"
                    onClick={() => setZoom({ src: p.img, caption: p.caption })}>
                    <img src={p.img} alt={p.caption} className="plot-img" decoding="async" loading="lazy" />
                    <span className="plot-zoom-hint" aria-hidden="true">⤢</span>
                  </button>
                  <figcaption className="plot-cap"><span className="plot-cap-txt">{p.caption}</span></figcaption>
                </figure>
              ))}
            </div>
          </div>
        ) : (
          <p className="rl-hint">Choisissez les paramètres puis lancez l'entraînement pour voir
            la courbe de récompense, la politique apprise et la fonction valeur.</p>
        )}
      </div>

      {zoom ? <PlotModal src={zoom.src} caption={zoom.caption} onClose={() => setZoom(null)} /> : null}
    </div>
  );
}
