import { useState } from 'react'
import './App.css'
import Dashboard from './components/Dashboard'
import ReinforcementView from './components/ReinforcementView'
import ExploitView from './components/ExploitView'

function App() {
  const [view, setView] = useState('dashboard')
  return (
    <div className="app-container">
      <header className="app-header glass-panel">
        <div className="logo">
          <div className="logo-icon animate-pulse"></div>
          <h1>automation_<span>machine_learning</span></h1>
        </div>
        <nav className="header-nav">
          <button type="button" className={view === 'dashboard' ? 'active' : ''}
            onClick={() => setView('dashboard')}>Pipeline</button>
          <button type="button" className={view === 'exploit' ? 'active' : ''}
            onClick={() => setView('exploit')}>Exploiter</button>
          <button type="button" className={view === 'rl' ? 'active' : ''}
            onClick={() => setView('rl')}>Renforcement</button>
        </nav>
      </header>
      <main className="app-main">
        {view === 'rl' ? <ReinforcementView />
          : view === 'exploit' ? <ExploitView />
            : <Dashboard />}
      </main>
    </div>
  )
}

export default App
