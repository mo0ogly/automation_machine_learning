import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import PlotModal from './PlotModal';
import AssistButton from './AssistButton';
import AssistAnswer from './AssistAnswer';
import './components.css';
import './reinforcement.css';

// API base: configurable at build time (Docker passes VITE_API_URL), defaults to
// the local dev backend so `npm run dev` keeps working unchanged.
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const POLL_MS = 1200;
const TERMINAL = ['done', 'error', 'cancelled'];

// Build the default config for an algorithm from its field schema (defaults live
// in the backend catalogue, so the two never drift).
function defaultsFor(algo) {
  const out = {};
  (algo ? algo.fields : []).forEach((f) => { out[f.name] = f.default; });
  return out;
}

export default function DeepRLView() {
  const { t } = useTranslation('reinforcement');
  const [catalog, setCatalog] = useState(null);
  const [envId, setEnvId] = useState(null);
  const [algoName, setAlgoName] = useState('PPO');
  const [cfg, setCfg] = useState({});
  const [job, setJob] = useState(null);        // { status, progress, result, error }
  const [jobId, setJobId] = useState(null);
  const [error, setError] = useState(null);
  const [zoom, setZoom] = useState(null);
  const [answers, setAnswers] = useState({});
  const [explainBusy, setExplainBusy] = useState(false);
  const pollRef = useRef(null);

  const envs = catalog ? catalog.envs : [];
  const algos = catalog ? catalog.algos : [];
  const presets = catalog ? (catalog.presets || []) : [];
  const env = useMemo(() => envs.find((e) => e.id === envId) || null, [envs, envId]);
  const algo = useMemo(() => algos.find((a) => a.id === algoName) || null, [algos, algoName]);
  const running = job && job.status === 'running';
  const result = job && job.status !== 'running' ? job.result : null;

  // Load the environment / algorithm / preset catalogue once.
  useEffect(() => {
    let alive = true;
    fetch(API_URL + '/api/rl/deep/catalog')
      .then((r) => r.json())
      .then((data) => {
        if (!alive) return;
        setCatalog(data);
        if (data.envs && data.envs.length) setEnvId(data.envs[0].id);
      })
      .catch(() => { if (alive) setError(t('deep.error')); });
    return () => { alive = false; };
  }, [t]);

  // On algorithm change, keep shared hyperparameter values (total_timesteps,
  // learning_rate, gamma) and fill only the algo-specific ones with defaults —
  // so switching algorithm, or loading a preset, never wipes the config.
  useEffect(() => {
    if (!algo) return;
    setCfg((prev) => {
      const names = new Set(algo.fields.map((f) => f.name));
      const kept = {};
      Object.keys(prev || {}).forEach((k) => { if (names.has(k)) kept[k] = prev[k]; });
      return { ...defaultsFor(algo), ...kept };
    });
  }, [algo]);

  // Keep the algorithm compatible with the selected environment's action space.
  useEffect(() => {
    if (!env || !algos.length) return;
    const current = algos.find((a) => a.id === algoName);
    if (!current || !current.action_kinds.includes(env.action_kind)) {
      const compat = algos.find((a) => a.action_kinds.includes(env.action_kind));
      if (compat) setAlgoName(compat.id);
    }
  }, [env, algos, algoName]);

  const supports = useCallback(
    (a) => Boolean(env && a.action_kinds.includes(env.action_kind)),
    [env],
  );

  const stopPolling = () => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  };

  // Poll the training job until it reaches a terminal state.
  useEffect(() => {
    if (!jobId) return undefined;
    const tick = () => {
      fetch(API_URL + '/api/rl/deep/job/' + jobId)
        .then((r) => r.json())
        .then((data) => {
          setJob(data);
          if (TERMINAL.includes(data.status)) stopPolling();
        })
        .catch(() => { /* transient poll error, retried on next tick */ });
    };
    tick();
    pollRef.current = setInterval(tick, POLL_MS);
    return stopPolling;
  }, [jobId]);

  const setField = (name, value) => setCfg((p) => ({ ...p, [name]: value }));

  const clearRun = () => { stopPolling(); setJob(null); setJobId(null); setError(null); setAnswers({}); };

  const applyPreset = (p) => {
    clearRun();
    setEnvId(p.env_id);
    setAlgoName(p.algo);
    setCfg({ ...p.config });   // the algo-change effect fills any missing field
  };

  const train = async () => {
    if (!envId || !algoName) return;
    setError(null); setAnswers({});
    setJob({ status: 'running', progress: 0 });
    try {
      const res = await fetch(API_URL + '/api/rl/deep/train', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ env_id: envId, algo: algoName, config: cfg }),
      });
      const data = await res.json();
      if (!res.ok) { setError(data.detail || t('deep.error')); setJob(null); return; }
      setJobId(data.job_id);
    } catch {
      setError(t('deep.error'));
      setJob(null);
    }
  };

  const cancel = () => {
    if (!jobId) return;
    fetch(API_URL + '/api/rl/deep/job/' + jobId + '/cancel', { method: 'POST' }).catch(() => {});
  };

  const reset = () => { clearRun(); if (algo) setCfg(defaultsFor(algo)); };

  // Per-element AI helper (reuses the session-free assist agent). Handles both a
  // hyperparameter slider (param = field name) and a result graph (param =
  // "graphe: <caption>", enriched with the run's metrics as context).
  const askExplain = async (param) => {
    setExplainBusy(true);
    try {
      const body = { param, level: 'novice', config: cfg };
      if (result && param === 'resultats') {           // explain the whole results table
        body.caption = t('deep.metricsTitle');
        body.metrics = result.metrics;
      } else if (param.indexOf('graphe:') === 0 && result) {
        body.caption = param.replace(/^graphe:\s*/, '');
        body.metrics = result.metrics;
      }
      const res = await fetch(API_URL + '/api/rl/deep/explain', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (res.ok) setAnswers((p) => ({ ...p, [param]: data }));
    } catch { /* explanation is non-blocking */ }
    setExplainBusy(false);
  };
  const applySuggestion = (sc) => setCfg((p) => ({ ...p, ...sc }));

  const pct = Math.round((job && job.progress ? job.progress : 0) * 100);

  // "solved" verdict, read from the trained env's threshold (from the catalogue).
  const verdict = useMemo(() => {
    if (!result) return null;
    const trainedEnv = envs.find((e) => e.id === result.env_id);
    const hasThreshold = trainedEnv && trainedEnv.reward_threshold != null;
    if (!hasThreshold) return { tone: 'success', title: t('deep.verdict.doneTitle'), text: t('deep.verdict.doneText') };
    if (result.solved) return { tone: 'success', title: t('deep.verdict.solvedTitle'), text: t('deep.verdict.solvedText') };
    return { tone: 'warning', title: t('deep.verdict.unsolvedTitle'), text: t('deep.verdict.unsolvedText') };
  }, [result, envs, t]);

  const renderField = (f) => (
    <div key={f.name} className="rl-field">
      <span className="rl-field-head">
        <span>{t('deep.fields.' + f.name + '.label')} : <strong>{cfg[f.name]}</strong></span>
        <AssistButton topic={f.name} label={t('deep.fields.' + f.name + '.label')} text={t('deep.ai')}
          onAssist={askExplain} busy={explainBusy} />
      </span>
      <input type="range" min={f.min} max={f.max} step={f.step}
        value={cfg[f.name] == null ? f.default : cfg[f.name]}
        onChange={(e) => setField(f.name, Number(e.target.value))}
        aria-label={t('deep.fields.' + f.name + '.label')} />
      <span className="rl-minmax"><em>{f.min}</em><em>{f.max}</em></span>
      <p className="rl-field-hint">{t('deep.fields.' + f.name + '.hint')}</p>
      <AssistAnswer topic={f.name} answers={answers} onApply={applySuggestion} />
    </div>
  );

  return (
    <div className="rl-deep">
      <div className="rl-intro glass-panel">
        <div className="rl-intro-text">
          <span className="rl-kicker">{t('deep.kicker')}</span>
          <h2>{t('deep.title')}</h2>
          <p>{t('deep.intro')}</p>
        </div>
      </div>

      <section className="rl-panel glass-panel" aria-label={t('deep.presetsTitle')}>
        <header className="rl-step-head">
          <span className="rl-step-no">0</span>
          <div><h3>{t('deep.presetsTitle')}</h3><p>{t('deep.presetsHint')}</p></div>
        </header>
        <div className="rl-preset-grid">
          {presets.map((p) => (
            <button key={p.id} type="button" className="rl-preset-card glass-panel"
              onClick={() => applyPreset(p)}>
              <span className={'rl-tag rl-tag-group rl-tag-' + p.group}>{t('deep.groups.' + p.group)}</span>
              <strong>{t('deep.presets.' + p.id + '.name')}</strong>
              <small>{t('deep.presets.' + p.id + '.desc')}</small>
              <span className="rl-preset-meta">{p.algo} · {p.env_id}{p.recommended ? ' ★' : ''}</span>
            </button>
          ))}
        </div>
      </section>

      <div className="rl-workbench">
        <section className="rl-panel glass-panel" aria-label={t('deep.step1')}>
          <header className="rl-step-head">
            <span className="rl-step-no">1</span>
            <div><h3>{t('deep.step1')}</h3><p>{t('deep.step1Hint')}</p></div>
          </header>
          <div className="rl-env-grid">
            {envs.map((e) => (
              <button key={e.id} type="button"
                className={'rl-env-card' + (e.id === envId ? ' active' : '')}
                aria-pressed={e.id === envId} onClick={() => setEnvId(e.id)}>
                <span className={'rl-tag rl-tag-group rl-tag-' + e.group}>{t('deep.groups.' + e.group)}</span>
                <strong>{t('deep.envs.' + e.id + '.label')}</strong>
                <small>{t('deep.envs.' + e.id + '.desc')}</small>
                <span className="rl-env-tags">
                  <span className={'rl-tag rl-tag-' + e.action_kind}>
                    {t('deep.actionKind.' + e.action_kind)}
                  </span>
                  <span className="rl-tag">{t('deep.obsDim', { n: e.obs_dim })}</span>
                </span>
              </button>
            ))}
          </div>
        </section>

        <section className="rl-panel glass-panel" aria-label={t('deep.step2')}>
          <header className="rl-step-head">
            <span className="rl-step-no">2</span>
            <div><h3>{t('deep.step2')}</h3><p>{t('deep.step2Hint')}</p></div>
          </header>
          <div className="rl-algo-row" role="radiogroup" aria-label={t('deep.step2')}>
            {algos.map((a) => {
              const ok = supports(a);
              return (
                <button key={a.id} type="button" role="radio" aria-checked={a.id === algoName}
                  disabled={!ok}
                  className={'rl-algo' + (a.id === algoName ? ' active' : '') + (ok ? '' : ' disabled')}
                  title={ok ? a.family : t('deep.algoIncompatible', { algo: a.id, kind: env ? t('deep.actionKind.' + env.action_kind) : '' })}
                  onClick={() => ok && setAlgoName(a.id)}>
                  <span className="rl-algo-name">
                    <strong>{a.id}</strong>
                    {a.contrib ? <span className="rl-tag rl-tag-contrib">{t('deep.contribBadge')}</span> : null}
                  </span>
                  <small>{t('deep.algos.' + a.id + '.desc')}</small>
                </button>
              );
            })}
          </div>
        </section>
      </div>

      <section className="rl-panel glass-panel" aria-label={t('deep.step3')}>
        <header className="rl-step-head">
          <span className="rl-step-no">3</span>
          <div><h3>{t('deep.step3')}</h3><p>{t('deep.step3Hint')}</p></div>
        </header>
        <div className="rl-controls">{algo ? algo.fields.map(renderField) : null}</div>
        <div className="rl-actions">
          {running ? (
            <button type="button" className="btn btn-secondary" onClick={cancel}>{t('deep.cancel')}</button>
          ) : (
            <button type="button" className="btn btn-primary" onClick={train} disabled={!env || !algo}>
              {t('deep.train')}
            </button>
          )}
          <button type="button" className="btn btn-secondary" onClick={reset} disabled={running}>
            {t('deep.reset')}
          </button>
        </div>
        {running ? (
          <div className="rl-progress" role="status" aria-live="polite">
            <div className="rl-progress-bar"><span style={{ width: pct + '%' }} /></div>
            <span className="rl-progress-txt">{t('deep.progress', { pct })}</span>
          </div>
        ) : null}
      </section>

      {error ? <div className="banner banner-block">{error}</div> : null}

      <section className="rl-results glass-panel" aria-label={t('deep.step4')}>
        <header className="rl-step-head">
          <span className="rl-step-no">4</span>
          <div><h3>{t('deep.step4')}</h3><p>{t('deep.step4Hint')}</p></div>
          {result ? (
            <span className="rl-results-actions">
              <AssistButton topic="resultats" label={t('deep.explainResults')} text={t('deep.ai')}
                onAssist={askExplain} busy={explainBusy} />
              {result.can_download ? (
                <a className="btn btn-secondary rl-download" download
                  href={API_URL + '/api/rl/deep/job/' + jobId + '/download'}>{t('deep.download')}</a>
              ) : null}
            </span>
          ) : null}
        </header>
        {result ? (
          <div className="rl-result">
            {result.cancelled ? (
              <div className="rl-stale" role="status">{t('deep.cancelled')}</div>
            ) : null}
            {verdict ? (
              <div className={'rl-verdict rl-verdict-' + verdict.tone} role="status">
                <strong>{verdict.title}</strong><span>{verdict.text}</span>
              </div>
            ) : null}
            <AssistAnswer topic="resultats" answers={answers} onApply={applySuggestion} />
            <div className="report-cards">
              {Object.entries(result.metrics).map(([k, v]) => (
                <div key={k} className="report-card">
                  <div className="report-k">{k}</div>
                  <div className="report-v">{String(v)}</div>
                </div>
              ))}
            </div>
            <div className="plots-grid">
              {result.plots.map((p, i) => {
                const topic = 'graphe: ' + (p.caption || i);
                return (
                  <figure key={i} className="plot-fig">
                    <button type="button" className="plot-thumb" title="Agrandir"
                      onClick={() => setZoom({ src: p.img, caption: p.caption })}>
                      <img src={p.img} alt={p.caption} className="plot-img" decoding="async" />
                      <span className="plot-zoom-hint" aria-hidden="true">⤢</span>
                    </button>
                    <figcaption className="plot-cap">
                      <span className="plot-cap-txt">{p.caption}</span>
                      <AssistButton topic={topic} label={p.caption} text={t('deep.ai')}
                        onAssist={askExplain} busy={explainBusy} />
                    </figcaption>
                    <AssistAnswer topic={topic} answers={answers} onApply={applySuggestion} />
                  </figure>
                );
              })}
            </div>
          </div>
        ) : (
          <div className="rl-empty"><p className="rl-hint">{t('deep.empty')}</p></div>
        )}
      </section>

      {zoom ? <PlotModal src={zoom.src} caption={zoom.caption} onClose={() => setZoom(null)} /> : null}
    </div>
  );
}
