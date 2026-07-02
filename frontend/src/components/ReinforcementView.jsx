import React, { useEffect, useMemo, useRef, useState } from 'react';
import PlotModal from './PlotModal';
import AssistButton from './AssistButton';
import AssistAnswer from './AssistAnswer';
import './components.css';
import './reinforcement.css';

// API base: configurable at build time (Docker passes VITE_API_URL), defaults to
// the local dev backend so `npm run dev` keeps working unchanged.
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// Q-learning hyperparameters exposed to the expert (bounds mirror the backend),
// grouped by what they control: the world vs the algorithm.
const ENV_FIELDS = [
  { key: 'size', label: 'Taille de la grille', min: 3, max: 10, step: 1,
    hint: 'Côté du labyrinthe N×N — plus grand = plus d’états à explorer.' },
  { key: 'n_goals', label: 'Nombre de buts', min: 1, max: 3, step: 1,
    hint: 'Cases-objectif (les buts au-delà du coin bas-droit sont placés au hasard).' },
  { key: 'n_traps', label: 'Pièges aléatoires', min: 0, max: 5, step: 1,
    hint: 'Pièges ajoutés au hasard, en plus de ceux placés à la main.' },
];
const ALGO_FIELDS = [
  { key: 'episodes', label: "Nombre d'épisodes", min: 20, max: 2000, step: 20,
    hint: 'Parties d’entraînement : plus il y en a, mieux la table Q converge.' },
  { key: 'alpha', label: "Taux d'apprentissage (α)", min: 0.01, max: 1, step: 0.01,
    hint: 'Vitesse de mise à jour de Q : haut = rapide mais instable.' },
  { key: 'gamma', label: "Facteur d'actualisation (γ)", min: 0.5, max: 0.999, step: 0.001,
    hint: 'Poids du futur : proche de 1 = stratégie long terme.' },
  { key: 'epsilon', label: 'Exploration initiale (ε)', min: 0, max: 1, step: 0.05,
    hint: 'Part d’actions aléatoires au départ, qui décroît au fil des épisodes.' },
];
const DEFAULTS = {
  size: 5, episodes: 300, alpha: 0.1, gamma: 0.95, epsilon: 1.0,
  n_goals: 1, n_traps: 0, obstacles: [], traps: [],
};

// One-click pedagogical scenarios, from gentle to hostile.
const PRESETS = [
  { name: 'Découverte', desc: 'Petit monde vide : la convergence idéale.',
    cfg: { ...DEFAULTS } },
  { name: 'Labyrinthe', desc: 'Des murs à contourner pour trouver la sortie.',
    cfg: { ...DEFAULTS, size: 7, episodes: 600,
      obstacles: [[1, 1], [2, 1], [3, 1], [4, 1], [1, 3], [2, 3], [3, 3], [5, 3], [6, 3], [1, 5], [3, 5], [4, 5], [5, 5]] } },
  { name: 'Champ de mines', desc: 'Des pièges qui punissent l’imprudence.',
    cfg: { ...DEFAULTS, size: 6, episodes: 800, n_traps: 4 } },
  { name: 'Grand monde', desc: '10×10, plusieurs buts : le vrai défi.',
    cfg: { ...DEFAULTS, size: 10, episodes: 1500, gamma: 0.99, n_goals: 2, n_traps: 2 } },
];

const sameCell = (a, b) => a[0] === b[0] && a[1] === b[1];
const inList = (list, cell) => list.some((x) => sameCell(x, cell));
// Arrow-key deltas for the roving-tabindex grid navigation.
const ARROW_DELTA = {
  ArrowUp: [-1, 0], ArrowDown: [1, 0], ArrowLeft: [0, -1], ArrowRight: [0, 1],
};
// Action deltas, index-aligned with the backend (GridWorld.ACTIONS: up/right/down/left).
const ACTION_DELTA = [[-1, 0], [0, 1], [1, 0], [0, -1]];
// Default reward constants, superseded by config.rewards from the API response.
const DEFAULT_REWARDS = { step: -1, goal: 10, trap: -10 };
const fmtReward = (v) => (v > 0 ? '+' + v : String(v).replace('-', '−'));

// Greedy rollout of the learned policy on the trained environment. Returns the
// visited cells plus how the episode ended (goal / trap / stuck / loop guard).
function greedyPath(env, policy) {
  const n = env.size;
  let cur = [env.start[0], env.start[1]];
  const path = [cur];
  let outcome = 'loop';
  for (let i = 0; i < n * n * 2; i++) {
    if (inList(env.goals, cur)) { outcome = 'goal'; break; }
    if (inList(env.traps, cur)) { outcome = 'trap'; break; }
    const a = policy[cur[0] * n + cur[1]];
    const d = ACTION_DELTA[a] || [0, 0];
    let nr = cur[0] + d[0], nc = cur[1] + d[1];
    if (nr < 0 || nr >= n || nc < 0 || nc >= n || inList(env.obstacles, [nr, nc])) {
      nr = cur[0]; nc = cur[1];
    }
    if (nr === cur[0] && nc === cur[1]) { outcome = 'stuck'; break; }
    cur = [nr, nc];
    path.push(cur);
  }
  return { path, outcome };
}
const OUTCOME_TEXT = {
  goal: 'but atteint.', trap: 'tombé dans un piège.',
  stuck: 'bloqué (la politique pousse contre un mur).',
  loop: 'boucle sans fin — la politique n’a pas convergé ici.',
};

// The agent <-> environment interaction loop, the founding diagram of RL.
function LoopDiagram() {
  return (
    <svg className="rl-diagram" viewBox="0 0 340 110" role="img"
      aria-label="Boucle agent-environnement : l'agent agit, l'environnement répond par un état et une récompense">
      <defs>
        <marker id="rl-arr" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto">
          <path d="M0 0L8 4L0 8z" fill="var(--accent-primary)" />
        </marker>
        <marker id="rl-arr2" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto">
          <path d="M0 0L8 4L0 8z" fill="var(--status-success)" />
        </marker>
      </defs>
      <rect x="8" y="35" width="92" height="40" rx="10" className="rl-diagram-box" />
      <text x="54" y="60" textAnchor="middle" className="rl-diagram-label">Agent</text>
      <rect x="240" y="35" width="92" height="40" rx="10" className="rl-diagram-box rl-diagram-box-env" />
      <text x="286" y="60" textAnchor="middle" className="rl-diagram-label">Environnement</text>
      <path d="M104 42 C 150 12, 190 12, 236 42" fill="none" stroke="var(--accent-primary)"
        strokeWidth="1.6" markerEnd="url(#rl-arr)" />
      <text x="170" y="16" textAnchor="middle" className="rl-diagram-cap">action aₜ</text>
      <path d="M236 70 C 190 100, 150 100, 104 70" fill="none" stroke="var(--status-success)"
        strokeWidth="1.6" markerEnd="url(#rl-arr2)" />
      <text x="170" y="106" textAnchor="middle" className="rl-diagram-cap rl-diagram-cap-r">
        récompense rₜ₊₁ · état sₜ₊₁</text>
    </svg>
  );
}

export default function ReinforcementView() {
  const [cfg, setCfg] = useState(DEFAULTS);
  const [tool, setTool] = useState('obstacle');
  const [result, setResult] = useState(null);
  // Config as actually sent to the last successful training run: drives both the
  // "stale result" banner and the auto-placed markers overlay.
  const [lastCfg, setLastCfg] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [zoom, setZoom] = useState(null);
  const [answers, setAnswers] = useState({});
  const [explainBusy, setExplainBusy] = useState(false);
  // Roving tabindex: a single grid cell is tabbable, arrows move the focus.
  const [focus, setFocus] = useState([0, 0]);
  const gridRef = useRef(null);
  // Trajectory replay: greedy rollout animated cell by cell on the grid.
  const [trail, setTrail] = useState(null);
  const [stepIdx, setStepIdx] = useState(0);
  const [playing, setPlaying] = useState(false);

  const start = [0, 0];
  const goal = [cfg.size - 1, cfg.size - 1];

  const setField = (k, v) => {
    setCfg((p) => {
      const next = { ...p, [k]: v };
      if (k === 'size') {
        const fits = ([r, c]) => r < v - 1 || c < v - 1; // also drops cells on the new goal
        next.obstacles = p.obstacles.filter(([r, c]) => r < v && c < v).filter(fits);
        next.traps = p.traps.filter(([r, c]) => r < v && c < v).filter(fits);
      }
      return next;
    });
    if (k === 'size') setFocus((f) => [Math.min(f[0], v - 1), Math.min(f[1], v - 1)]);
  };

  // Paint tool: place/erase obstacles and traps directly on the grid.
  const paintCell = (r, c) => {
    if (sameCell([r, c], start) || sameCell([r, c], goal)) return;
    setCfg((p) => {
      const without = (list) => list.filter((x) => !sameCell(x, [r, c]));
      let obstacles = without(p.obstacles);
      let traps = without(p.traps);
      if (tool === 'obstacle' && !inList(p.obstacles, [r, c])) obstacles = [...obstacles, [r, c]];
      if (tool === 'trap' && !inList(p.traps, [r, c])) traps = [...traps, [r, c]];
      return { ...p, obstacles, traps };
    });
  };

  const moveFocus = (e) => {
    const delta = ARROW_DELTA[e.key];
    if (!delta) return;
    e.preventDefault();
    const nr = Math.min(cfg.size - 1, Math.max(0, focus[0] + delta[0]));
    const nc = Math.min(cfg.size - 1, Math.max(0, focus[1] + delta[1]));
    setFocus([nr, nc]);
    const el = gridRef.current && gridRef.current.querySelector('[data-cell="' + nr + '-' + nc + '"]');
    if (el) el.focus();
  };

  // The displayed results describe the run trained with lastCfg; any config
  // edit since then makes them stale (banner + dimming, markers hidden).
  const stale = useMemo(
    () => Boolean(result && lastCfg && JSON.stringify(cfg) !== JSON.stringify(lastCfg)),
    [result, lastCfg, cfg],
  );

  // Random goals/traps only exist server-side; overlay them as read-only "auto"
  // markers, diffed against the config that was actually trained (not the
  // current one — erasing an explicit trap must not resurrect it as "auto").
  const autoMarks = useMemo(() => {
    const env = result && result.env;
    if (!env || !lastCfg || stale) return { goals: [], traps: [] };
    const corner = [env.size - 1, env.size - 1];
    return {
      goals: env.goals.filter((g) => !sameCell(g, corner)),
      traps: env.traps.filter((t) => !inList(lastCfg.traps, t)),
    };
  }, [result, lastCfg, stale]);

  const cellKind = (r, c) => {
    if (sameCell([r, c], start)) return 'start';
    if (sameCell([r, c], goal)) return 'goal';
    if (inList(cfg.obstacles, [r, c])) return 'obstacle';
    if (inList(cfg.traps, [r, c])) return 'trap';
    if (inList(autoMarks.goals, [r, c])) return 'goal-auto';
    if (inList(autoMarks.traps, [r, c])) return 'trap-auto';
    return 'free';
  };
  // Reward values come from the trained response when available, so the legend
  // and tooltips never drift from the backend constants.
  const rewards = (result && result.config && result.config.rewards) || DEFAULT_REWARDS;
  // Same visual language as the backend plots: S / BUT / X.
  const CELL_GLYPH = {
    start: 'S', goal: 'BUT', 'goal-auto': 'BUT', obstacle: '', trap: 'X', 'trap-auto': 'X', free: '',
  };
  const CELL_TITLE = {
    start: 'Départ de l’agent', goal: 'But (récompense ' + fmtReward(rewards.goal) + ')',
    'goal-auto': 'But placé automatiquement', obstacle: 'Obstacle (infranchissable)',
    trap: 'Piège (pénalité ' + fmtReward(rewards.trap) + ', fin d’épisode)',
    'trap-auto': 'Piège placé automatiquement',
    free: 'Case libre',
  };

  const applyPreset = (p) => { setCfg({ ...p.cfg }); setError(null); setFocus([0, 0]); };
  const clearBoard = () => setCfg((p) => ({ ...p, obstacles: [], traps: [] }));

  // Replay overlay is only meaningful for the trained (non-stale) environment.
  const replayInfo = useMemo(() => {
    if (!result || !result.policy || !result.env || stale || !trail) return null;
    return { agent: trail.path[Math.min(stepIdx, trail.path.length - 1)], step: stepIdx };
  }, [result, stale, trail, stepIdx]);

  const replay = () => {
    if (!result || !result.policy || !result.env) return;
    setTrail(greedyPath(result.env, result.policy));
    setStepIdx(0);
    setPlaying(true);
  };

  useEffect(() => {
    if (!playing || !trail) return undefined;
    const id = setInterval(() => {
      setStepIdx((i) => {
        if (i + 1 >= trail.path.length) { setPlaying(false); return i; }
        return i + 1;
      });
    }, 280);
    return () => clearInterval(id);
  }, [playing, trail]);

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
    } catch { /* explanation is non-blocking */ }
    setExplainBusy(false);
  };
  const applyRlSuggestion = (sc) => setCfg((p) => ({ ...p, ...sc }));

  const train = async () => {
    const sent = cfg;
    setBusy(true); setError(null);
    try {
      const res = await fetch(API_URL + '/api/rl/train', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(sent),
      });
      const data = await res.json();
      if (!res.ok) { setError(data.detail || "Échec de l'entraînement"); setBusy(false); return; }
      setResult(data);
      setLastCfg(sent);
      setTrail(null);
      setPlaying(false);
    } catch {
      setError("Échec de l'entraînement — le backend est-il démarré ?");
    }
    setBusy(false);
  };

  // Learning verdict, read from the backend's headline metrics.
  const verdict = useMemo(() => {
    if (!result) return null;
    const rate = parseFloat(String(result.metrics['Taux de réussite final'] ?? '').replace('%', ''));
    const gain = Number(result.metrics["Gain d'apprentissage"] ?? 0);
    if (Number.isNaN(rate)) return null;
    if (rate >= 80 && gain > 0) return {
      tone: 'success', title: 'L’agent a appris',
      text: 'Il atteint un but dans ' + rate + '% des derniers épisodes : la politique a convergé.',
    };
    if (rate >= 40) return {
      tone: 'warning', title: 'Apprentissage partiel',
      text: 'La politique progresse mais reste fragile — essayez plus d’épisodes, ou un α plus faible pour stabiliser.',
    };
    return {
      tone: 'error', title: 'L’agent n’a pas convergé',
      text: 'Trop peu d’épisodes, un monde trop hostile ou une exploration mal réglée : ajustez et relancez.',
    };
  }, [result]);

  const renderField = (f) => (
    <div key={f.key} className="rl-field">
      <span className="rl-field-head">
        <span>{f.label} : <strong>{cfg[f.key]}</strong></span>
        <AssistButton topic={f.key} label={f.label} text="IA"
          onAssist={askExplain} busy={explainBusy} />
      </span>
      <input type="range" min={f.min} max={f.max} step={f.step}
        value={cfg[f.key]} onChange={(e) => setField(f.key, Number(e.target.value))}
        aria-label={f.label} />
      <span className="rl-minmax"><em>{f.min}</em><em>{f.max}</em></span>
      <p className="rl-field-hint">{f.hint}</p>
      <AssistAnswer topic={f.key} answers={answers} onApply={applyRlSuggestion} />
    </div>
  );

  return (
    <div className="lab rl-lab">
      <div className="rl-intro glass-panel">
        <div className="rl-intro-text">
          <span className="rl-kicker">Troisième paradigme</span>
          <h2>Apprentissage par renforcement</h2>
          <p>
            Pas de jeu de données figé : un <strong>agent</strong> apprend par essais-erreurs en
            interagissant avec un <strong>environnement</strong> — ici un labyrinthe
            <em> GridWorld</em>. À chaque pas il choisit une action, reçoit une
            <strong> récompense</strong>, et ajuste sa stratégie (<em>Q-learning</em>) pour
            maximiser la récompense cumulée. Il part de la case <strong>S</strong> et doit
            rejoindre un but par le chemin le plus court, en évitant les pièges.
          </p>
        </div>
        <LoopDiagram />
      </div>

      <div className="rl-presets" role="group" aria-label="Scénarios prédéfinis">
        {PRESETS.map((p) => (
          <button key={p.name} type="button" className="rl-preset glass-panel"
            onClick={() => applyPreset(p)} title={p.desc}>
            <span className="rl-preset-body">
              <strong>{p.name}</strong>
              <small>{p.desc}</small>
            </span>
          </button>
        ))}
      </div>

      <div className="rl-workbench">
        <section className="rl-board-panel glass-panel" aria-label="Éditeur d'environnement">
          <header className="rl-step-head">
            <span className="rl-step-no">1</span>
            <div>
              <h3>Concevoir l’environnement</h3>
              <p>Choisissez un outil puis cliquez sur la grille pour construire le monde.</p>
            </div>
          </header>
          <div className="rl-tools">
            <div className="rl-tool-group" role="radiogroup" aria-label="Outil de placement">
              {[['obstacle', 'Obstacle', 'rl-cell-obstacle', ''],
                ['trap', 'Piège', 'rl-cell-trap', 'X'],
                ['erase', 'Gomme', 'rl-cell-free', '']].map(([k, lbl, chip, glyph]) => (
                  <button key={k} type="button" role="radio" aria-checked={tool === k}
                    className={'rl-tool' + (tool === k ? ' active' : '')}
                    onClick={() => setTool(k)}>
                    <span className={'rl-chip ' + chip} aria-hidden="true">{glyph}</span>{lbl}
                  </button>
                ))}
            </div>
            <button type="button" className="rl-tool rl-tool-clear" onClick={clearBoard}
              disabled={!cfg.obstacles.length && !cfg.traps.length}>Vider</button>
          </div>
          <div className="rl-grid" role="grid" ref={gridRef} onKeyDown={moveFocus}
            aria-label={'Labyrinthe ' + cfg.size + ' par ' + cfg.size}
            style={{ '--rl-n': cfg.size }}>
            {Array.from({ length: cfg.size }, (_, r) => (
              <div key={r} role="row" className="rl-row">
                {Array.from({ length: cfg.size }, (_, c) => {
                  const kind = cellKind(r, c);
                  const fixed = kind === 'start' || kind === 'goal';
                  const onAgent = replayInfo && sameCell(replayInfo.agent, [r, c]);
                  const visited = replayInfo && !onAgent
                    && inList(trail.path.slice(0, replayInfo.step), [r, c]);
                  return (
                    <button key={r + '-' + c} type="button" role="gridcell"
                      className={'rl-cell rl-cell-' + kind
                        + (onAgent ? ' rl-cell-agent' : '') + (visited ? ' rl-cell-visited' : '')}
                      title={CELL_TITLE[kind]} aria-disabled={fixed}
                      data-cell={r + '-' + c}
                      tabIndex={focus[0] === r && focus[1] === c ? 0 : -1}
                      onFocus={() => setFocus([r, c])}
                      aria-label={'Case ' + (r + 1) + ',' + (c + 1) + ' : ' + CELL_TITLE[kind]}
                      onClick={() => paintCell(r, c)}>
                      {onAgent && kind === 'free' ? '●' : CELL_GLYPH[kind]}
                    </button>
                  );
                })}
              </div>
            ))}
          </div>
          {/* Reward values come from config.rewards (API) after a run, with the
              backend defaults (rl/gridworld.py) as pre-training fallback. */}
          <ul className="rl-legend-chips" aria-label="Légende">
            <li><span className="rl-chip rl-cell-start">S</span> départ</li>
            <li><span className="rl-chip rl-chip-goal rl-cell-goal">BUT</span> but
              ({fmtReward(rewards.goal)})</li>
            <li><span className="rl-chip rl-cell-trap">X</span> piège
              ({fmtReward(rewards.trap)})</li>
            <li><span className="rl-chip rl-cell-obstacle" /> obstacle</li>
            <li><span className="rl-chip rl-cell-free" /> libre
              ({fmtReward(rewards.step)} / pas)</li>
          </ul>
          {result && result.policy && !stale ? (
            <div className="rl-replay">
              <button type="button" className="btn btn-secondary rl-replay-btn"
                onClick={replay} disabled={playing}>
                {playing ? 'Rejeu en cours…' : 'Rejouer la trajectoire'}
              </button>
              {trail ? (
                <span className="rl-replay-status" role="status">
                  Trajectoire gloutonne : {trail.path.length - 1} pas — {OUTCOME_TEXT[trail.outcome]}
                </span>
              ) : null}
            </div>
          ) : null}
          {(cfg.n_goals > 1 || cfg.n_traps > 0) ? (
            <p className="rl-auto-note">
              {cfg.n_goals > 1 ? '+' + (cfg.n_goals - 1) + ' but(s) ' : ''}
              {cfg.n_goals > 1 && cfg.n_traps > 0 ? 'et ' : ''}
              {cfg.n_traps > 0 ? '+' + cfg.n_traps + ' piège(s) ' : ''}
              placé(s) automatiquement à l’entraînement — visibles sur la grille après coup.
            </p>
          ) : null}
        </section>

        <section className="rl-panel glass-panel" aria-label="Hyperparamètres">
          <header className="rl-step-head">
            <span className="rl-step-no">2</span>
            <div>
              <h3>Régler l’algorithme</h3>
              <p>Chaque curseur a son bouton IA pour comprendre — et appliquer — un bon réglage.</p>
            </div>
          </header>
          <div className="rl-group">
            <h4 className="rl-group-title">Environnement</h4>
            <div className="rl-controls">{ENV_FIELDS.map(renderField)}</div>
          </div>
          <div className="rl-group">
            <h4 className="rl-group-title">Q-learning</h4>
            <div className="rl-controls">{ALGO_FIELDS.map(renderField)}</div>
          </div>
          <div className="rl-actions">
            <button className="btn btn-primary" onClick={train} disabled={busy}>
              {busy ? <span className="rl-spinner" aria-hidden="true" /> : null}
              {busy ? 'Entraînement en cours…' : "Entraîner l'agent"}
            </button>
            <button type="button" className="btn btn-secondary" onClick={() => applyPreset(PRESETS[0])}
              disabled={busy}>Réinitialiser</button>
          </div>
        </section>
      </div>

      {error ? <div className="banner banner-block">{error}</div> : null}

      <section className={'rl-results glass-panel' + (busy ? ' rl-busy' : '')}
        aria-label="Résultats de l'entraînement" aria-busy={busy}>
        <header className="rl-step-head">
          <span className="rl-step-no">3</span>
          <div>
            <h3>Analyser l’apprentissage</h3>
            <p>Courbe de récompense, politique apprise et fonction valeur.</p>
          </div>
        </header>

        {result ? (
          <div className={'rl-result' + (stale ? ' rl-result-stale' : '')}>
            {stale ? (
              <div className="rl-stale" role="status">
                Configuration modifiée depuis cet entraînement — ces résultats décrivent
                l’exécution précédente. Relancez l’entraînement pour les mettre à jour.
              </div>
            ) : null}
            {verdict ? (
              <div className={'rl-verdict rl-verdict-' + verdict.tone} role="status">
                <strong>{verdict.title}</strong>
                <span>{verdict.text}</span>
              </div>
            ) : null}
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
                    <img src={p.img} alt={p.caption} className="plot-img" decoding="async" />
                    <span className="plot-zoom-hint" aria-hidden="true">⤢</span>
                  </button>
                  <figcaption className="plot-cap"><span className="plot-cap-txt">{p.caption}</span></figcaption>
                </figure>
              ))}
            </div>
          </div>
        ) : (
          <div className="rl-empty">
            <p className="rl-hint">
              Construisez le monde (étape 1), réglez l’algorithme (étape 2), puis lancez
              l’entraînement pour voir si l’agent apprend à rejoindre le but.
            </p>
          </div>
        )}
      </section>

      {zoom ? <PlotModal src={zoom.src} caption={zoom.caption} onClose={() => setZoom(null)} /> : null}
    </div>
  );
}
