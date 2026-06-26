import { useState } from 'react'
import './App.css'
import Dashboard from './components/Dashboard'
import ReinforcementView from './components/ReinforcementView'
import ExploitView from './components/ExploitView'
import ConfigMenu from './components/ConfigMenu'
import AiBackendsPanel from './components/AiBackendsPanel'
import PromptsPanel from './components/PromptsPanel'
import ModelsMenu from './components/ModelsMenu'

// API base: configurable at build time (Docker passes VITE_API_URL), defaults to
// the local dev backend so `npm run dev` keeps working unchanged.
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// Map a prompt's localisation.view to a top-nav view id.
const VIEW_OF = { 'Pipeline': 'dashboard', 'Renforcement': 'rl' };

function App() {
  const [view, setView] = useState('dashboard')
  // Global config menu (top-right): the AI backends panel is reachable from any
  // view. aiRefresh bumps so the Pipeline view re-reads the active backend after
  // a change made from here.
  const [aiPanelOpen, setAiPanelOpen] = useState(false)
  const [promptsOpen, setPromptsOpen] = useState(false)
  const [modelsOpen, setModelsOpen] = useState(false)
  const [aiRefresh, setAiRefresh] = useState(0)
  const [locateNote, setLocateNote] = useState(null)

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
          <div className="logo-icon animate-pulse"></div>
          <h1>automation_<span>machine_learning</span></h1>
        </div>
        <div className="header-right">
          <nav className="header-nav">
            <button type="button" className={view === 'dashboard' ? 'active' : ''}
              onClick={() => setView('dashboard')}>Pipeline</button>
            <button type="button" className={view === 'exploit' ? 'active' : ''}
              onClick={() => setView('exploit')}>Exploiter</button>
            <button type="button" className={view === 'rl' ? 'active' : ''}
              onClick={() => setView('rl')}>Renforcement</button>
          </nav>
          <button type="button" className="cfg-menu-btn" onClick={() => setModelsOpen(true)}
            title="Modèles entraînés">Modèles</button>
          <ConfigMenu onOpenAi={() => setAiPanelOpen(true)}
            onOpenPrompts={() => setPromptsOpen(true)} />
        </div>
      </header>
      {locateNote ? <div className="locate-note">{locateNote}</div> : null}
      <main className="app-main">
        {view === 'rl' ? <ReinforcementView />
          : view === 'exploit' ? <ExploitView />
            : <Dashboard aiRefresh={aiRefresh} />}
      </main>
      {aiPanelOpen ? (
        <AiBackendsPanel apiBase={API_URL} onClose={() => setAiPanelOpen(false)}
          onChanged={() => setAiRefresh((n) => n + 1)} />
      ) : null}
      {promptsOpen ? (
        <PromptsPanel apiBase={API_URL} onClose={() => setPromptsOpen(false)}
          onLocate={locatePrompt} />
      ) : null}
      {modelsOpen ? (
        <ModelsMenu apiBase={API_URL} onClose={() => setModelsOpen(false)} />
      ) : null}
    </div>
  )
}

export default App
