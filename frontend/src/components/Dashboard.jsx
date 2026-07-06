import React, { useState, useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import Copilot from './Copilot';
import ChatDock from './ChatDock';
import StageStepper from './StageStepper';
import StagePanel from './StagePanel';
import AiBackendButton from './AiBackendButton';
import AiBackendsPanel from './AiBackendsPanel';
import DatasetCardModal from './DatasetCardModal';
import SessionsMenu from './SessionsMenu';
import { isCyber } from './cyber';
import AssistButton from './AssistButton';
import AssistAnswer from './AssistAnswer';
import DataQualityBanner from './DataQualityBanner';
import { API_URL } from '../apiBase';
import './components.css';

const Dashboard = ({ aiRefresh, onOpenRL }) => {
  const { t } = useTranslation('dashboard');
  // Human-readable label for the detected problem type (badge in the session bar).
  const PTYPE_LABELS = {
    regression: t('problemTypes.regression'), classification: t('problemTypes.classification'),
    clustering: t('problemTypes.clustering'), anomaly: t('problemTypes.anomaly'),
  };
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
  const [aiPanelOpen, setAiPanelOpen] = useState(false);
  const [sessionsOpen, setSessionsOpen] = useState(false);
  const [recentSessions, setRecentSessions] = useState([]);
  const [cardName, setCardName] = useState(null);
  const [rlAgents, setRlAgents] = useState([]);
  const fileInputRef = useRef(null);

  useEffect(() => {
    fetch(API_URL + '/api/demo-datasets').then((r) => r.json())
      .then((d) => setDemoDatasets(d.datasets || [])).catch(() => {});
    fetch(API_URL + '/api/agent-status').then((r) => r.json())
      .then(setAgent).catch(() => {});
    // Recent sessions for the one-click reopen list on the landing screen.
    fetch(API_URL + '/api/sessions').then((r) => r.json())
      .then((d) => setRecentSessions(d.sessions || [])).catch(() => {});
    // Saved Deep RL agents (SOC/NOC), surfaced as a landing card.
    fetch(API_URL + '/api/rl/deep/registry').then((r) => r.json())
      .then((d) => setRlAgents(d.agents || [])).catch(() => {});
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

  // Re-read the active backend when it is changed from the global config menu.
  useEffect(() => {
    if (!aiRefresh) return;
    fetch(API_URL + '/api/agent-status').then((r) => r.json()).then(setAgent).catch(() => {});
  }, [aiRefresh]);

  const firstStageId = (s) => (s && s.stages && s.stages.length ? s.stages[0].stage_id : 'clean');

  const loadStage = async (sessionId, stageId) => {
    setError(null);
    setReco(null);
    setInterpretation(null);
    setAssistAnswers({});
    try {
      const res = await fetch(API_URL + '/api/session/' + sessionId + '/stage/' + stageId);
      const data = await res.json();
      if (!res.ok) { setError(data.detail || t('errors.loadFailed')); return; }
      setStageData(data);
      setActiveStage(stageId);
      setConfig(data.current_config || data.default_config || {});
      setSubPhase(data.result ? 'act' : 'observe');
    } catch (e) {
      setError(t('errors.apiUnreachablePort8000'));
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

  // One-click reopen of a recent session by id (landing list).
  const openSessionById = async (id) => {
    setError(null);
    try {
      const res = await fetch(API_URL + '/api/session/' + id);
      const data = await res.json();
      if (!res.ok) { setError(data.detail || t('errors.sessionNotFound')); return; }
      openSession(data);
    } catch (e) {
      setError(t('errors.apiUnreachableStartBackend'));
    }
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
      if (!res.ok) { setError(data.detail || t('errors.generic')); } else { openSession(data); }
    } catch (e) {
      setError(t('errors.apiUnreachableStartBackend'));
    }
    setBusy(false);
  };

  const startDemo = async (name) => {
    setBusy(true); setError(null);
    try {
      const res = await fetch(API_URL + '/api/session/start-demo/' + name, { method: 'POST' });
      const data = await res.json();
      if (!res.ok) { setError(data.detail || t('errors.generic')); } else { openSession(data); }
    } catch (e) {
      setError(t('errors.apiUnreachableStartBackend'));
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
      if (!res.ok) { setError(data.detail || t('errors.agentUnavailable')); }
      else { setReco(data); refreshJournal(session.session_id); }
    } catch (e) {
      setError(t('errors.agentUnreachable'));
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
        body: JSON.stringify({ stage: activeStage, topic: 'action', label: t('journal.actionApplied'),
          text: t('journal.appliedPrefix') + summary, source: 'user' }),
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
      else setError(data.detail || t('errors.interpretationUnavailable'));
    } catch (e) {
      setError(t('errors.interpretationUnreachable'));
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
      if (!res.ok) setError(data.detail || t('errors.assistUnavailable'));
      else {
        setAssistAnswers((prev) => ({ ...prev, [topic]: data }));
        await refreshJournal(session.session_id);
      }
    } catch (e) {
      setError(t('errors.assistUnreachable'));
    }
    setAssistLoading(false);
  };

  // Stage-targeted assist: explain a specific pipeline stage from the stepper,
  // even when it isn't the active one. Answer keyed by "etape:<id>".
  const askAssistStage = async (stageId, topic, label) => {
    if (!session) return;
    setAssistLoading(true); setError(null);
    try {
      const res = await fetch(API_URL + '/api/session/' + session.session_id + '/stage/' + stageId + '/assist',
        { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ topic, label, level, config: {} }) });
      const data = await res.json();
      if (!res.ok) setError(data.detail || t('errors.assistUnavailable'));
      else {
        setAssistAnswers((prev) => ({ ...prev, [topic]: data }));
        await refreshJournal(session.session_id);
      }
    } catch (e) {
      setError(t('errors.assistUnreachable'));
    }
    setAssistLoading(false);
  };

  // Re-fetch agent status after the AI backends panel changes the active backend.
  const refreshAgent = async () => {
    try { setAgent(await fetch(API_URL + '/api/agent-status').then((r) => r.json())); }
    catch (e) { /* keep current agent on failure */ }
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
      if (!res.ok) { setError(data.detail || t('errors.runFailed')); setBusy(false); return; }
      setSession((prev) => ({ ...prev, status: data.status }));
      await loadStage(session.session_id, activeStage);
    } catch (e) {
      setError(t('errors.runFailedDot'));
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
      if (!res.ok) { setError(data.detail || t('errors.renameFailed')); setBusy(false); return; }
      setSession((prev) => ({ ...prev, status: data.status }));
      await loadStage(session.session_id, 'evaluate');
    } catch (e) {
      setError(t('errors.renameClustersFailed'));
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

  // One demo-dataset row (badged when it is a cyber dataset).
  const renderDemo = (ds, cyber) => (
    <div key={ds.name} className="demo-row">
      <button className="btn btn-demo" onClick={() => startDemo(ds.name)} disabled={busy}>
        <strong>{ds.type}</strong>{cyber ? <span className="badge-cyber">CYBER</span> : null}<br />
        <span className="demo-desc">{ds.description}</span>
      </button>
      <button type="button" className="demo-info-btn" title={t('landing.datasetCardTitle')}
        onClick={() => setCardName(ds.name)}>i</button>
    </div>
  );

  // ── Landing (no session) ──────────────────────────────────────────────
  if (!session) {
    const cyberDemos = demoDatasets.filter((d) => isCyber(d.name));
    const otherDemos = demoDatasets.filter((d) => !isCyber(d.name));
    return (
      <div className="landing">
        <div className="panel glass-panel landing-card">
          <h2 className="panel-header">{t('landing.title')}</h2>
          <p className="muted">
            {t('landing.pipelineDescription')}
          </p>

          <div className="card mt-3">
            <h3 className="text-sm text-secondary mb-2">{t('landing.importCsv')}</h3>
            <div className="upload-zone" onClick={() => fileInputRef.current.click()}>
              <span className="icon">+</span>
              <p>{t('landing.chooseCsvFile')}</p>
              <input type="file" accept=".csv" style={{ display: 'none' }} ref={fileInputRef}
                onChange={startUpload} />
            </div>
          </div>

          <div className="card mt-2">
            <h3 className="text-sm text-secondary mb-2">{t('landing.orDemoDataset')}</h3>
            {cyberDemos.length ? (
              <div className="cyber-block">
                <div className="cyber-subhead"><span className="badge-cyber">CYBER</span> {t('landing.cyberDatasets')}</div>
                {cyberDemos.map((ds) => renderDemo(ds, true))}
              </div>
            ) : null}
            {otherDemos.length ? (
              <>
                {cyberDemos.length ? <div className="other-subhead">{t('landing.otherDatasets')}</div> : null}
                {otherDemos.map((ds) => renderDemo(ds, false))}
              </>
            ) : null}
          </div>

          <div className="card mt-2">
            <div className="cyber-subhead">
              <span className="badge-cyber">SOC / NOC</span> {t('landing.rlTitle')}
            </div>
            <p className="muted landing-rl-desc">
              {rlAgents.length
                ? t('landing.rlCount', { n: rlAgents.length })
                : t('landing.rlEmpty')}
            </p>
            <button type="button" className="btn btn-secondary" onClick={onOpenRL}>
              {t('landing.rlOpen')}
            </button>
          </div>

          {recentSessions.length ? (
            <div className="card mt-2">
              <div className="recent-head">
                <h3 className="text-sm text-secondary mb-2">{t('landing.recentSessions')}</h3>
                <button type="button" className="ai-link" onClick={() => setSessionsOpen(true)}>
                  {t('landing.manageSessions')}
                </button>
              </div>
              <div className="recent-list">
                {recentSessions.slice(0, 5).map((s) => {
                  const sm = s.summary || {};
                  const when = s.updated_at
                    ? new Date(s.updated_at).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' })
                    : '';
                  return (
                    <button key={s.id} type="button" className="recent-row" disabled={busy}
                      onClick={() => openSessionById(s.id)} title={t('landing.reopenSession')}>
                      <span className="recent-name">
                        {s.filename || t('landing.unnamed')}
                        {isCyber(s.filename) ? <span className="badge-cyber">CYBER</span> : null}
                      </span>
                      <span className={sm.model ? 'recent-model recent-model-on' : 'recent-model'}>
                        {sm.model ? '● ' + sm.model : '○ ' + t('landing.noModel')}
                      </span>
                      <span className="recent-date">{when}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          ) : null}

          {agent ? (
            <div className={agent.configured ? 'agent-chip agent-ok' : 'agent-chip agent-off'}>
              {agent.configured
                ? t('landing.agentActive')
                : t('landing.noAgentConfigured')}
            </div>
          ) : null}
          {agent ? (
            <AiBackendButton agent={agent} onOpen={() => setAiPanelOpen(true)} />
          ) : null}
          {error ? <div className="banner banner-block mt-2">{error}</div> : null}
        </div>
        {aiPanelOpen ? (
          <AiBackendsPanel apiBase={API_URL} onClose={() => setAiPanelOpen(false)} onChanged={refreshAgent} />
        ) : null}
        {cardName ? (
          <DatasetCardModal apiBase={API_URL} name={cardName} onClose={() => setCardName(null)} />
        ) : null}
        {sessionsOpen ? (
          <SessionsMenu apiBase={API_URL} currentId={null}
            onOpen={(d) => { setSessionsOpen(false); openSession(d); }}
            onClose={() => setSessionsOpen(false)} />
        ) : null}
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
          <span>{t('lab.overview', { rows: session.overview.rows, cols: session.overview.cols })}</span>
          <span className="badge-ia">
            <span className={session.context.supervised ? 'tag tag-sup' : 'tag tag-unsup'}>
              {session.context.supervised ? t('lab.supervised') : t('lab.unsupervised')}
            </span>
            <AssistButton topic="paradigme" text={t('ai', { ns: 'stage' })} busy={assistLoading} onAssist={askAssist}
              label={session.context.supervised ? t('lab.whySupervised') : t('lab.whyUnsupervised')} />
          </span>
          <span className="badge-ia">
            <span className="tag tag-type">
              {PTYPE_LABELS[session.context.problem_type] || session.context.problem_type}
            </span>
            <AssistButton topic="type_probleme" text={t('ai', { ns: 'stage' })} busy={assistLoading} onAssist={askAssist}
              label={t('lab.explainType', { type: PTYPE_LABELS[session.context.problem_type] || session.context.problem_type })} />
          </span>
          {session.context.target_col ? (
            <span className="badge-ia">
              <span className="tag">{t('lab.target')} : {session.context.target_col}</span>
              <AssistButton topic="cible" text={t('ai', { ns: 'stage' })} busy={assistLoading} onAssist={askAssist}
                label={t('lab.targetRole', { target: session.context.target_col })} />
            </span>
          ) : null}
          {agent ? (
            <AiBackendButton agent={agent} onOpen={() => setAiPanelOpen(true)} />
          ) : null}
        </div>
        <div className="lab-bar-actions">
          <button className="btn btn-secondary" onClick={() => setSessionsOpen(true)}>{t('lab.mySessions')}</button>
          <button className="btn btn-secondary" onClick={reset}>{t('lab.newAnalysis')}</button>
        </div>
      </div>

      {(assistAnswers['type_probleme'] || assistAnswers['paradigme'] || assistAnswers['cible']) ? (
        <div className="badge-ia-answers">
          <AssistAnswer topic="paradigme" answers={assistAnswers} />
          <AssistAnswer topic="type_probleme" answers={assistAnswers} />
          <AssistAnswer topic="cible" answers={assistAnswers} />
        </div>
      ) : null}

      <DataQualityBanner warnings={session.data_quality} onAssist={askAssist}
        assistBusy={assistLoading} assistAnswers={assistAnswers} />

      <StageStepper stages={session.stages} status={session.status}
        activeStage={activeStage} onSelect={(id) => loadStage(session.session_id, id)}
        onAssistStage={askAssistStage} assistBusy={assistLoading} />

      {session.stages.some((s) => assistAnswers['etape:' + s.stage_id]) ? (
        <div className="badge-ia-answers">
          {session.stages.map((s) => (
            <AssistAnswer key={s.stage_id} topic={'etape:' + s.stage_id} answers={assistAnswers} />
          ))}
        </div>
      ) : null}

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
          <ChatDock apiBase={API_URL} sessionId={session && session.session_id}
            title={t('lab.copilotTitle')} />
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
      {aiPanelOpen ? (
        <AiBackendsPanel apiBase={API_URL} onClose={() => setAiPanelOpen(false)} onChanged={refreshAgent} />
      ) : null}
      {sessionsOpen ? (
        <SessionsMenu apiBase={API_URL} currentId={session.session_id}
          onOpen={(d) => { setSessionsOpen(false); openSession(d); }}
          onClose={() => setSessionsOpen(false)}
          onDeleted={() => { setSessionsOpen(false); reset(); }} />
      ) : null}
    </div>
  );
};

export default Dashboard;
