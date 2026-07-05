import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import PlotModal from './PlotModal';
import AssistButton from './AssistButton';
import AssistAnswer from './AssistAnswer';
import MyAgentsPanel from './deeprl/MyAgentsPanel';
import ImportPanel from './deeprl/ImportPanel';
import {
  getCatalog, getRegistry, getJob, postTrain, postEvaluate, postContinue,
  postSave, cancelJob, deleteAgent, deleteEnv, postExplain, jobDownloadUrl,
} from './deeprl/api';
import './components.css';
import './reinforcement.css';

const POLL_MS = 1200;
const TERMINAL = ['done', 'error', 'cancelled'];

// An algorithm fits an environment when the action spaces match and — for a
// mask-only algorithm (MaskablePPO) — the env exposes an action mask.
function fits(algo, env) {
  if (!algo || !env) return false;
  if (!algo.action_kinds.includes(env.action_kind)) return false;
  return algo.requires_mask ? Boolean(env.maskable) : true;
}

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
  const [registry, setRegistry] = useState([]);
  const [envId, setEnvId] = useState(null);
  const [algoName, setAlgoName] = useState('PPO');
  const [cfg, setCfg] = useState({});
  const [job, setJob] = useState(null);        // { status, progress, result, error }
  const [jobId, setJobId] = useState(null);
  const [error, setError] = useState(null);
  const [zoom, setZoom] = useState(null);
  const [answers, setAnswers] = useState({});
  const [explainBusy, setExplainBusy] = useState(false);
  const [saveName, setSaveName] = useState('');
  const [savedNote, setSavedNote] = useState(null);
  const [actionBusy, setActionBusy] = useState(false);
  const pollRef = useRef(null);

  const envs = catalog ? catalog.envs : [];
  const algos = catalog ? catalog.algos : [];
  const presets = catalog ? (catalog.presets || []) : [];
  const env = useMemo(() => envs.find((e) => e.id === envId) || null, [envs, envId]);
  const algo = useMemo(() => algos.find((a) => a.id === algoName) || null, [algos, algoName]);
  const running = job && job.status === 'running';
  const result = job && job.status !== 'running' ? job.result : null;

  const refreshRegistry = useCallback(() => {
    getRegistry().then((d) => setRegistry(d.agents || [])).catch(() => {});
  }, []);

  const loadCatalog = useCallback((selectFirst) => {
    return getCatalog().then((data) => {
      setCatalog(data);
      setRegistry(data.agents || []);
      if (selectFirst && data.envs && data.envs.length) setEnvId(data.envs[0].id);
      return data;
    });
  }, []);

  // Load the environment / algorithm / preset / agent catalogue once.
  useEffect(() => {
    let alive = true;
    getCatalog()
      .then((data) => {
        if (!alive) return;
        setCatalog(data);
        setRegistry(data.agents || []);
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

  // Keep the algorithm compatible with the selected environment (action space +
  // action-mask requirement).
  useEffect(() => {
    if (!env || !algos.length) return;
    const current = algos.find((a) => a.id === algoName);
    if (!fits(current, env)) {
      const compat = algos.find((a) => fits(a, env));
      if (compat) setAlgoName(compat.id);
    }
  }, [env, algos, algoName]);

  const supports = useCallback((a) => fits(a, env), [env]);

  const stopPolling = () => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  };

  // Poll the current job until it reaches a terminal state.
  useEffect(() => {
    if (!jobId) return undefined;
    const tick = () => {
      getJob(jobId)
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

  const clearRun = () => {
    stopPolling(); setJob(null); setJobId(null); setError(null);
    setAnswers({}); setSavedNote(null); setSaveName('');
  };

  const applyPreset = (p) => {
    clearRun();
    setEnvId(p.env_id);
    setAlgoName(p.algo);
    setCfg({ ...p.config });   // the algo-change effect fills any missing field
  };

  // Start a job from a promise that resolves to { job_id }, and begin polling.
  const beginJob = async (promise) => {
    setError(null); setAnswers({}); setSavedNote(null); setSaveName('');
    setJob({ status: 'running', progress: 0 });
    try {
      const data = await promise;
      setJobId(data.job_id);
    } catch (e) {
      setError(e.message || t('deep.error'));
      setJob(null);
    }
  };

  const train = () => {
    if (!envId || !algoName) return;
    beginJob(postTrain({ env_id: envId, algo: algoName, config: cfg }));
  };

  const evaluateAgent = (a) => beginJob(postEvaluate(a.id, a.env_id));
  const continueAgent = (a) => beginJob(postContinue(a.id, a.env_id, cfg));

  const removeAgent = async (a) => {
    setActionBusy(true);
    try { await deleteAgent(a.id); refreshRegistry(); } catch { /* non-blocking */ }
    setActionBusy(false);
  };

  const removeEnv = async (e) => {
    setActionBusy(true);
    try {
      await deleteEnv(e.id);
      const data = await loadCatalog(false);
      if (envId === e.id && data.envs && data.envs.length) setEnvId(data.envs[0].id);
    } catch { /* non-blocking */ }
    setActionBusy(false);
  };

  const saveTrained = async () => {
    if (!jobId) return;
    setActionBusy(true);
    try {
      const entry = await postSave(jobId, saveName);
      setSavedNote(t('deep.registry.saved', { name: entry.name }));
      setSaveName('');
      refreshRegistry();
    } catch (e) { setError(e.message); }
    setActionBusy(false);
  };

  const cancel = () => { if (jobId) cancelJob(jobId); };
  const reset = () => { clearRun(); if (algo) setCfg(defaultsFor(algo)); };

  // Per-element AI helper (reuses the session-free assist agent). Handles a
  // hyperparameter slider (param = field name), the whole results table
  // (param = "resultats"), and a result graph (param = "graphe: <caption>").
  const askExplain = async (param) => {
    setExplainBusy(true);
    try {
      const body = { param, level: 'novice', config: cfg };
      if (result && param === 'resultats') {
        body.caption = t('deep.metricsTitle');
        body.metrics = result.metrics;
        body.group = result.group;
        body.random_reward = result.random_reward;
        body.threshold = result.threshold;
        body.beats_random = result.beats_random;
      } else if (param.indexOf('graphe:') === 0 && result) {
        body.caption = param.replace(/^graphe:\s*/, '');
        body.metrics = result.metrics;
      }
      const data = await postExplain(body);
      setAnswers((p) => ({ ...p, [param]: data }));
    } catch { /* explanation is non-blocking */ }
    setExplainBusy(false);
  };
  const applySuggestion = (sc) => setCfg((p) => ({ ...p, ...sc }));

  const pct = Math.round((job && job.progress ? job.progress : 0) * 100);
  const isEval = result && result.kind === 'eval';

  // "solved" verdict, read from the trained env's threshold (from the catalogue).
  const verdict = useMemo(() => {
    if (!result) return null;
    const trainedEnv = envs.find((e) => e.id === result.env_id);
    const hasThreshold = trainedEnv && trainedEnv.reward_threshold != null;
    if (!hasThreshold) {
      // No official threshold (e.g. bespoke cyber env): judge against the random baseline.
      if (result.beats_random) return { tone: 'success', title: t('deep.verdict.beatsRandomTitle'), text: t('deep.verdict.beatsRandomText') };
      return { tone: 'warning', title: t('deep.verdict.notBetterTitle'), text: t('deep.verdict.notBetterText') };
    }
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
              <span className="rl-preset-meta">{p.algo} · {t('deep.envs.' + p.env_id + '.label')}{p.recommended ? ' ★' : ''}</span>
            </button>
          ))}
        </div>
      </section>

      <MyAgentsPanel agents={registry} onEvaluate={evaluateAgent} onContinue={continueAgent}
        onDelete={removeAgent} busy={actionBusy || running} />

      <ImportPanel envs={envs} algos={algos}
        onAgentImported={refreshRegistry} onEnvImported={() => loadCatalog(false)} />

      <div className="rl-workbench">
        <section className="rl-panel glass-panel" aria-label={t('deep.step1')}>
          <header className="rl-step-head">
            <span className="rl-step-no">1</span>
            <div><h3>{t('deep.step1')}</h3><p>{t('deep.step1Hint')}</p></div>
          </header>
          <div className="rl-env-grid">
            {envs.map((e) => (
              <div key={e.id}
                className={'rl-env-card' + (e.id === envId ? ' active' : '')}>
                <button type="button" className="rl-env-select"
                  aria-pressed={e.id === envId} onClick={() => setEnvId(e.id)}>
                  <span className={'rl-tag rl-tag-group rl-tag-' + e.group}>{t('deep.groups.' + e.group)}</span>
                  <strong>{e.custom ? e.label : t('deep.envs.' + e.id + '.label')}</strong>
                  <small>{e.custom ? t('deep.envs.customDesc', { n: e.n_rows }) : t('deep.envs.' + e.id + '.desc')}</small>
                  <span className="rl-env-tags">
                    <span className={'rl-tag rl-tag-' + e.action_kind}>
                      {t('deep.actionKind.' + e.action_kind)}
                    </span>
                    <span className="rl-tag">{t('deep.obsDim', { n: e.obs_dim })}</span>
                    {e.maskable ? <span className="rl-tag rl-tag-mask">{t('deep.maskable')}</span> : null}
                  </span>
                </button>
                {e.custom ? (
                  <button type="button" className="btn btn-ghost btn-sm rl-env-del"
                    disabled={actionBusy} onClick={() => removeEnv(e)}>{t('deep.registry.delete')}</button>
                ) : null}
              </div>
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
              <AssistButton topic="resultats" label={t('deep.diagnose')} text={t('deep.ai')}
                onAssist={askExplain} busy={explainBusy} />
              {result.can_download ? (
                <a className="btn btn-secondary rl-download" download
                  href={jobDownloadUrl(jobId)}>{t('deep.download')}</a>
              ) : null}
            </span>
          ) : null}
        </header>
        {result ? (
          <div className="rl-result">
            {result.cancelled ? (
              <div className="rl-stale" role="status">{t('deep.cancelled')}</div>
            ) : null}
            {isEval ? (
              <div className="rl-verdict rl-verdict-info" role="status">
                <strong>{t('deep.evalTitle')}</strong><span>{t('deep.evalText')}</span>
              </div>
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
            {result.can_download ? (
              <div className="rl-save" role="group" aria-label={t('deep.registry.saveTitle')}>
                <input type="text" value={saveName} onChange={(e) => setSaveName(e.target.value)}
                  placeholder={t('deep.registry.namePlaceholder')} aria-label={t('deep.registry.saveTitle')} />
                <button type="button" className="btn btn-primary" onClick={saveTrained}
                  disabled={actionBusy}>{t('deep.registry.save')}</button>
              </div>
            ) : null}
            {savedNote ? (
              <div className="rl-verdict rl-verdict-success" role="status"><span>{savedNote}</span></div>
            ) : null}
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
