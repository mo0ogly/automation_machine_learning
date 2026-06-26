import React, { useState, useRef, useEffect } from 'react';
import Copilot from './Copilot';
import StageStepper from './StageStepper';
import StagePanel from './StagePanel';
import ModelSelector from './ModelSelector';
import './components.css';

// API base: configurable at build time (Docker passes VITE_API_URL), defaults to
// the local dev backend so `npm run dev` keeps working unchanged.
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// Human-readable label for the detected problem type (badge in the session bar).
const PTYPE_LABELS = {
  regression: 'Régression', classification: 'Classification',
  clustering: 'Clustering', anomaly: "Détection d'anomalies",
};

const Dashboard = () => {
  const [session, setSession] = useState(null);
  const [activeStage, setActiveStage] = useState(null);
  const [stageData, setStageData] = useState(null);
  const [config, setConfig] = useState({});
  const [reco, setReco] = useState(null);
  const [recoLoading, setRecoLoading] = useState(false);
  const [interpretation, setInterpretation] = useState(null);
  const [interpretLoading, setInterpretLoading] = useState(false);
  const [insights, setInsights] = useState([]);
  const [level, setLevel] = useState('novice');
  const [assistLoading, setAssistLoading] = useState(false);
  const [assistAnswers, setAssistAnswers] = useState({});
  const [subPhase, setSubPhase] = useState('observe');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [demoDatasets, setDemoDatasets] = useState([]);
  const [agent, setAgent] = useState(null);
  const fileInputRef = useRef(null);

  useEffect(() => {
    fetch(API_URL + '/api/demo-datasets').then((r) => r.json())
      .then((d) => setDemoDatasets(d.datasets || [])).catch(() => {});
    fetch(API_URL + '/api/agent-status').then((r) => r.json())
      .then(setAgent).catch(() => {});
    // Restore the previous session after a reload (graphs/results survive).
    let saved = null;
    try { saved = localStorage.getItem('ml_session'); } catch (e) { saved = null; }
    if (saved) {
      fetch(API_URL + '/api/session/' + saved)
        .then((r) => (r.ok ? r.json() : Promise.reject(r)))
        .then((data) => openSession(data))
        .catch(() => { try { localStorage.removeItem('ml_session'); } catch (e) { /* ignore */ } });
    }
  }, []);

  const firstStageId = (s) => (s && s.stages && s.stages.length ? s.stages[0].stage_id : 'clean');

  const loadStage = async (sessionId, stageId) => {
    setError(null);
    setReco(null);
    setInterpretation(null);
    setAssistAnswers({});
    try {
      const res = await fetch(API_URL + '/api/session/' + sessionId + '/stage/' + stageId);
      const data = await res.json();
      if (!res.ok) { setError(data.detail || 'Erreur de chargement'); return; }
      setStageData(data);
      setActiveStage(stageId);
      setConfig(data.current_config || data.default_config || {});
      setSubPhase(data.result ? 'act' : 'observe');
    } catch (e) {
      setError('API injoignable — le backend tourne-t-il sur :8000 ?');
    }
  };

  const openSession = (data) => {
    setSession(data);
    setAgent(data.agent || agent);
    setInsights([]);
    try { localStorage.setItem('ml_session', data.session_id); } catch (e) { /* ignore */ }
    loadStage(data.session_id, firstStageId(data));
    refreshJournal(data.session_id);
  };

  const startUpload = async () => {
    const file = fileInputRef.current && fileInputRef.current.files[0];
    if (!file) return;
    setBusy(true); setError(null);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const res = await fetch(API_URL + '/api/session/start', { method: 'POST', body: fd });
      const data = await res.json();
      if (!res.ok) { setError(data.detail || 'Erreur'); } else { openSession(data); }
    } catch (e) {
      setError('API injoignable — démarrez le backend (uvicorn) sur :8000.');
    }
    setBusy(false);
  };

  const startDemo = async (name) => {
    setBusy(true); setError(null);
    try {
      const res = await fetch(API_URL + '/api/session/start-demo/' + name, { method: 'POST' });
      const data = await res.json();
      if (!res.ok) { setError(data.detail || 'Erreur'); } else { openSession(data); }
    } catch (e) {
      setError('API injoignable — démarrez le backend (uvicorn) sur :8000.');
    }
    setBusy(false);
  };

  const onConfigChange = (name, value) => {
    setConfig((prev) => ({ ...prev, [name]: value }));
    setSubPhase('decide');
  };

  const askAgent = async () => {
    setRecoLoading(true); setSubPhase('orient');
    try {
      const res = await fetch(API_URL + '/api/session/' + session.session_id + '/stage/' + activeStage + '/recommend',
        { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ config }) });
      const data = await res.json();
      if (!res.ok) { setError(data.detail || 'Agent indisponible'); }
      else { setReco(data); refreshJournal(session.session_id); }
    } catch (e) {
      setError('Agent injoignable.');
    }
    setRecoLoading(false);
  };

  const applyReco = () => {
    if (!reco || !reco.suggested_config) return;
    setConfig((prev) => ({ ...prev, ...reco.suggested_config }));
    setSubPhase('decide');
  };

  // Apply an actionable suggestion coming from a sub-step / per-graph AI answer.
  // Decision-table lists (e.g. dropped_columns) are UNIONed with what's already
  // chosen so applying "also drop these" never silently un-drops the rest.
  const applyAssistConfig = (cfg) => {
    if (!cfg || !Object.keys(cfg).length) return;
    setConfig((prev) => {
      const next = { ...prev };
      Object.entries(cfg).forEach(([k, v]) => {
        if (Array.isArray(v) && Array.isArray(prev[k])) {
          next[k] = Array.from(new Set([...prev[k], ...v]));
        } else {
          next[k] = v;
        }
      });
      return next;
    });
    setSubPhase('decide');
    // Trace the applied decision in the journal/memory.
    if (session) {
      const summary = Object.entries(cfg)
        .map(([k, v]) => k + ' = ' + (Array.isArray(v) ? v.length + ' var.' : v)).join(', ');
      fetch(API_URL + '/api/session/' + session.session_id + '/journal', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ stage: activeStage, topic: 'action', label: 'Action appliquée',
          text: 'Appliqué : ' + summary, source: 'user' }),
      }).then(() => refreshJournal(session.session_id)).catch(() => {});
    }
  };

  const askInterpret = async () => {
    setInterpretLoading(true);
    try {
      const res = await fetch(API_URL + '/api/session/' + session.session_id + '/stage/' + activeStage + '/interpret',
        { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
      const data = await res.json();
      if (res.ok) { setInterpretation(data); refreshJournal(session.session_id); }
      else setError(data.detail || 'Interprétation indisponible');
    } catch (e) {
      setError('Interprétation injoignable.');
    }
    setInterpretLoading(false);
  };

  // ── assisted mode: journal memory + per-sub-step helpers ───────────────
  const refreshJournal = async (sessionId) => {
    try {
      const res = await fetch(API_URL + '/api/session/' + sessionId + '/journal');
      const data = await res.json();
      if (res.ok) { setInsights(data.insights || []); if (data.level) setLevel(data.level); }
    } catch (e) { /* journal is non-blocking */ }
  };

  const askAssist = async (topic, label) => {
    if (!session) return;
    setAssistLoading(true); setError(null);
    try {
      const res = await fetch(API_URL + '/api/session/' + session.session_id + '/stage/' + activeStage + '/assist',
        { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ topic, label, level, config }) });
      const data = await res.json();
      if (!res.ok) setError(data.detail || 'Assistant indisponible');
      else {
        setAssistAnswers((prev) => ({ ...prev, [topic]: data }));
        await refreshJournal(session.session_id);
      }
    } catch (e) {
      setError('Assistant injoignable.');
    }
    setAssistLoading(false);
  };

  const setLevelRemote = (lvl) => {
    setLevel(lvl);
    if (session) {
      fetch(API_URL + '/api/session/' + session.session_id + '/level',
        { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ level: lvl }) })
        .catch(() => {});
    }
  };

  const applyRecoKey = (key, value) => {
    setConfig((prev) => ({ ...prev, [key]: value }));
    setSubPhase('decide');
  };

  const runStage = async () => {
    setBusy(true); setSubPhase('act'); setError(null);
    try {
      const res = await fetch(API_URL + '/api/session/' + session.session_id + '/stage/' + activeStage + '/run',
        { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ config }) });
      const data = await res.json();
      if (!res.ok) { setError(data.detail || "Échec de l'exécution"); setBusy(false); return; }
      setSession((prev) => ({ ...prev, status: data.status }));
      await loadStage(session.session_id, activeStage);
    } catch (e) {
      setError("Échec de l'exécution.");
    }
    setBusy(false);
  };

  // Cluster decision table: re-run evaluation with expert-chosen business names.
  const applyClusterLabels = async (labels) => {
    if (!labels || !Object.keys(labels).length) return;
    setBusy(true); setError(null);
    try {
      const res = await fetch(API_URL + '/api/session/' + session.session_id + '/stage/evaluate/run',
        { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ config: { cluster_labels: labels } }) });
      const data = await res.json();
      if (!res.ok) { setError(data.detail || 'Échec du renommage'); setBusy(false); return; }
      setSession((prev) => ({ ...prev, status: data.status }));
      await loadStage(session.session_id, 'evaluate');
    } catch (e) {
      setError('Échec du renommage des clusters.');
    }
    setBusy(false);
  };

  const gotoNext = () => {
    const ids = session.stages.map((s) => s.stage_id);
    const i = ids.indexOf(activeStage);
    if (i >= 0 && i < ids.length - 1) loadStage(session.session_id, ids[i + 1]);
  };

  const reset = () => {
    try { localStorage.removeItem('ml_session'); } catch (e) { /* ignore */ }
    setSession(null); setStageData(null); setActiveStage(null);
    setConfig({}); setReco(null); setInsights([]); setSubPhase('observe'); setError(null);
  };

  // ── Landing (no session) ──────────────────────────────────────────────
  if (!session) {
    return (
      <div className="landing">
        <div className="panel glass-panel landing-card">
          <h2 className="panel-header">Construire un modèle, étape par étape</h2>
          <p className="muted">
            Pipeline agentique : Nettoyage › Transformation › Intégration › Séparation › Modèle › Fine-tuning
            › Évaluation › Explicabilité. À chaque étape, l'agent propose un affinage ; l'expert valide ou ajuste.
          </p>

          <div className="card mt-3">
            <h3 className="text-sm text-secondary mb-2">Importer un CSV</h3>
            <div className="upload-zone" onClick={() => fileInputRef.current.click()}>
              <span className="icon">+</span>
              <p>Choisir un fichier CSV</p>
              <input type="file" accept=".csv" style={{ display: 'none' }} ref={fileInputRef}
                onChange={startUpload} />
            </div>
          </div>

          <div className="card mt-2">
            <h3 className="text-sm text-secondary mb-2">Ou un jeu de démonstration</h3>
            {demoDatasets.map((ds) => (
              <button key={ds.name} className="btn btn-demo" onClick={() => startDemo(ds.name)} disabled={busy}>
                <strong>{ds.type}</strong><br />
                <span className="demo-desc">{ds.description}</span>
              </button>
            ))}
          </div>

          {agent ? (
            <div className={agent.configured ? 'agent-chip agent-ok' : 'agent-chip agent-off'}>
              {agent.configured
                ? 'Agent Groq actif'
                : 'Agent Groq non configuré — recommandations heuristiques'}
            </div>
          ) : null}
          {agent && agent.configured ? (
            <ModelSelector agent={agent} apiBase={API_URL} onChange={setAgent} />
          ) : null}
          {error ? <div className="banner banner-block mt-2">{error}</div> : null}
        </div>
      </div>
    );
  }

  // ── Session active ────────────────────────────────────────────────────
  const ids = session.stages.map((s) => s.stage_id);
  const isLast = ids.indexOf(activeStage) === ids.length - 1;

  return (
    <div className="lab">
      <div className="lab-bar glass-panel">
        <div className="lab-meta">
          <strong>{session.filename}</strong>
          <span>{session.overview.rows} lignes · {session.overview.cols} colonnes</span>
          <span className={session.context.supervised ? 'tag tag-sup' : 'tag tag-unsup'}>
            {session.context.supervised ? 'Supervisé' : 'Non supervisé'}
          </span>
          <span className="tag tag-type">
            {PTYPE_LABELS[session.context.problem_type] || session.context.problem_type}
          </span>
          {session.context.target_col ? <span className="tag">cible : {session.context.target_col}</span> : null}
          {agent && agent.configured ? (
            <ModelSelector agent={agent} apiBase={API_URL} onChange={setAgent} />
          ) : agent ? (
            <span className="tag tag-warn">agent heuristique</span>
          ) : null}
        </div>
        <button className="btn btn-secondary" onClick={reset}>Nouvelle analyse</button>
      </div>

      <StageStepper stages={session.stages} status={session.status}
        activeStage={activeStage} onSelect={(id) => loadStage(session.session_id, id)} />

      {error ? <div className="banner banner-block">{error}</div> : null}

      <div className="lab-body">
        <aside className="lab-aside glass-panel">
          <Copilot
            stage={stageData}
            insights={insights}
            level={level}
            busy={assistLoading}
            onAssist={askAssist}
            onSetLevel={setLevelRemote}
          />
        </aside>

        <main className="lab-main glass-panel">
          <StagePanel
            stage={stageData}
            config={config}
            onConfigChange={onConfigChange}
            reco={reco}
            recoLoading={recoLoading}
            onAsk={askAgent}
            onApply={applyReco}
            onApplyKey={applyRecoKey}
            onRun={runStage}
            onNext={gotoNext}
            busy={busy}
            subPhase={subPhase}
            apiBase={API_URL}
            sessionId={session.session_id}
            isLast={isLast}
            interpretation={interpretation}
            interpretLoading={interpretLoading}
            onInterpret={askInterpret}
            onAssist={askAssist}
            assistBusy={assistLoading}
            assistAnswers={assistAnswers}
            onApplyAssist={applyAssistConfig}
            onApplyClusterLabels={applyClusterLabels}
          />
        </main>
      </div>
    </div>
  );
};

export default Dashboard;
