import { useState } from 'react'
import './App.css'
import Dashboard from './components/Dashboard'
import ReinforcementView from './components/ReinforcementView'
import ExploitView from './components/ExploitView'
import ConfigMenu from './components/ConfigMenu'
import AiBackendsPanel from './components/AiBackendsPanel'

// API base: configurable at build time (Docker passes VITE_API_URL), defaults to
// the local dev backend so `npm run dev` keeps working unchanged.
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

function App() {
  const [view, setView] = useState('dashboard')
  // Global config menu (top-right): the AI backends panel is reachable from any
  // view. aiRefresh bumps so the Pipeline view re-reads the active backend after
  // a change made from here.
  const [aiPanelOpen, setAiPanelOpen] = useState(false)
  const [aiRefresh, setAiRefresh] = useState(0)
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
          <ConfigMenu onOpenAi={() => setAiPanelOpen(true)} />
        </div>
      </header>
      <main className="app-main">
        {view === 'rl' ? <ReinforcementView />
          : view === 'exploit' ? <ExploitView />
            : <Dashboard aiRefresh={aiRefresh} />}
      </main>
      {aiPanelOpen ? (
        <AiBackendsPanel apiBase={API_URL} onClose={() => setAiPanelOpen(false)}
          onChanged={() => setAiRefresh((n) => n + 1)} />
      ) : null}
    </div>
  )
}

export default App
