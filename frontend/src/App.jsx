import { useState, useEffect, Suspense, lazy } from 'react'
import { useTranslation } from 'react-i18next'
import './App.css'
import LanguageSwitcher from './components/LanguageSwitcher'
import Dashboard from './components/Dashboard'
import ReinforcementView from './components/ReinforcementView'
import ExploitView from './components/ExploitView'
import ConfigMenu from './components/ConfigMenu'
import AiBackendsPanel from './components/AiBackendsPanel'
import ModelsMenu from './components/ModelsMenu'
import { isCyber } from './components/cyber'
import { groupModels } from './components/modelGroups'
import { API_URL } from './apiBase'

// Prompts panel pulls in Monaco (bundled offline). Code-split so the editor only
// loads when the panel is opened, keeping the initial app bundle light.
const PromptsPanel = lazy(() => import('./components/PromptsPanel'))

// Map a prompt's localisation.view to a top-nav view id.
const VIEW_OF = { 'Pipeline': 'dashboard', 'Renforcement': 'rl', 'Exploiter': 'exploit' };

// App mark: a small neural-network glyph — 3 inputs -> 3 hidden -> 1 output —
// symbolising the pipeline's "données -> modèle -> prédiction". The output node
// is success-green (the prediction); the rest uses the brand blue->violet
// gradient. Theme-driven via CSS variables so it tracks the palette.
function LogoMark() {
  const L1 = [9, 16, 23];
  const L2 = [8, 16, 24];
  const xIn = 7, xHid = 16, xOut = 25, yOut = 16;
  return (
    <svg className="logo-mark" viewBox="0 0 32 32" role="img" aria-label="automation_machine_learning">
      <defs>
        <linearGradient id="lm-grad" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="var(--accent-primary)" />
          <stop offset="100%" stopColor="var(--accent-secondary)" />
        </linearGradient>
      </defs>
      <rect x="1" y="1" width="30" height="30" rx="8" fill="none"
        stroke="url(#lm-grad)" strokeWidth="1.1" opacity="0.30" />
      {L1.map((a, i) => L2.map((b, j) => (
        <line key={'e1-' + i + '-' + j} x1={xIn} y1={a} x2={xHid} y2={b}
          stroke="url(#lm-grad)" strokeWidth="0.6" opacity="0.32" />
      )))}
      {L2.map((b, j) => (
        <line key={'e2-' + j} x1={xHid} y1={b} x2={xOut} y2={yOut}
          stroke="url(#lm-grad)" strokeWidth="0.8" opacity="0.55" />
      ))}
      {L1.map((y, i) => <circle key={'n1-' + i} cx={xIn} cy={y} r="2.1" fill="url(#lm-grad)" />)}
      {L2.map((y, j) => <circle key={'n2-' + j} cx={xHid} cy={y} r="2.1" fill="url(#lm-grad)" />)}
      <circle className="lm-halo" cx={xOut} cy={yOut} r="4.6" fill="var(--status-success)" opacity="0.22" />
      <circle cx={xOut} cy={yOut} r="2.7" fill="var(--status-success)" />
    </svg>
  );
}

function App() {
  const { t } = useTranslation('app')
  const [view, setView] = useState('dashboard')
  // Global config menu (top-right): the AI backends panel is reachable from any
  // view. aiRefresh bumps so the Pipeline view re-reads the active backend after
  // a change made from here.
  const [aiPanelOpen, setAiPanelOpen] = useState(false)
  const [promptsOpen, setPromptsOpen] = useState(false)
  const [modelsOpen, setModelsOpen] = useState(false)
  const [aiRefresh, setAiRefresh] = useState(0)
  const [locateNote, setLocateNote] = useState(null)
  // Count of trained cyber models, surfaced as a badge on the "Modèles" button.
  // Refetched when the panel closes (the set may have changed inside it).
  const [cyberCount, setCyberCount] = useState(0)

  useEffect(() => {
    let alive = true;
    // The badge counts everything the Models modal lists: distinct supervised
    // models (dataset + algo pairs, not raw re-training sessions) PLUS the
    // saved Deep RL agents (SOC/NOC) from the RL registry.
    const supervised = fetch(API_URL + '/api/sessions')
      .then((r) => r.json())
      .then((d) => groupModels((d.sessions || []).filter(
        (s) => s.summary && s.summary.model && isCyber(s.filename))).length)
      .catch(() => 0);
    const rlAgents = fetch(API_URL + '/api/rl/deep/registry')
      .then((r) => r.json())
      .then((d) => (d.agents || []).length)
      .catch(() => 0);
    Promise.all([supervised, rlAgents]).then(([nSup, nRl]) => {
      if (alive) setCyberCount(nSup + nRl);
    });
    return () => { alive = false; };
  }, [modelsOpen]);

  // "Localiser": switch to the prompt's view, close the panel, then scroll to and
  // pulse the triggering element ([data-prompt-loc]). If it isn't rendered yet
  // (e.g. no active session), show a transient hint instead.
  const locatePrompt = (loc) => {
    if (!loc) return;
    setPromptsOpen(false);
    setView(VIEW_OF[loc.view] || 'dashboard');
    setLocateNote(null);
    setTimeout(() => {
      const el = document.querySelector('[data-prompt-loc="' + loc.loc + '"]');
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        el.classList.add('prompt-locate-pulse');
        setTimeout(() => el.classList.remove('prompt-locate-pulse'), 2600);
      } else {
        setLocateNote('Ce prompt agit ici : ' + loc.trigger + '. Charge/avance une session pour le voir à l\'écran.');
        setTimeout(() => setLocateNote(null), 7000);
      }
    }, 220);
  };

  return (
    <div className="app-container">
      <header className="app-header glass-panel">
        <div className="logo">
          <LogoMark />
          <div className="logo-text">
            <h1>automation_<span>machine_learning</span></h1>
            <span className="logo-tagline">{t('tagline')}</span>
          </div>
        </div>
        <div className="header-right">
          <nav className="header-nav">
            <button type="button" className={view === 'dashboard' ? 'active' : ''}
              onClick={() => setView('dashboard')}>{t('nav.pipeline')}</button>
            <button type="button" className={view === 'exploit' ? 'active' : ''}
              onClick={() => setView('exploit')}>{t('nav.exploit')}</button>
            <button type="button" className={view === 'rl' ? 'active' : ''}
              onClick={() => setView('rl')}>{t('nav.reinforcement')}</button>
          </nav>
          <button type="button" className="cfg-menu-btn" onClick={() => setModelsOpen(true)}
            title={t('models.tooltip')}>
            {t('models.label')}
            {cyberCount > 0 ? (
              <span className="badge-cyber nav-badge" title={cyberCount + ' modèles cyber'}>
                {cyberCount}</span>
            ) : null}
          </button>
          <LanguageSwitcher />
          <ConfigMenu onOpenAi={() => setAiPanelOpen(true)}
            onOpenPrompts={() => setPromptsOpen(true)} />
        </div>
      </header>
      {locateNote ? <div className="locate-note">{locateNote}</div> : null}
      <main className="app-main">
        {view === 'rl' ? <ReinforcementView />
          : view === 'exploit' ? <ExploitView />
            : <Dashboard aiRefresh={aiRefresh} onOpenRL={() => setView('rl')} />}
      </main>
      {aiPanelOpen ? (
        <AiBackendsPanel apiBase={API_URL} onClose={() => setAiPanelOpen(false)}
          onChanged={() => setAiRefresh((n) => n + 1)} />
      ) : null}
      {promptsOpen ? (
        <Suspense fallback={<div className="locate-note">{t('editor.loading')}</div>}>
          <PromptsPanel apiBase={API_URL} onClose={() => setPromptsOpen(false)}
            onLocate={locatePrompt} />
        </Suspense>
      ) : null}
      {modelsOpen ? (
        <ModelsMenu apiBase={API_URL} onClose={() => setModelsOpen(false)} />
      ) : null}
    </div>
  )
}

export default App
