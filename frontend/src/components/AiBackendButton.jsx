import React from 'react';

// Compact lab-bar control: shows the active AI backend (provider / model) and
// opens the AI backends settings panel. Replaces the Groq-only ModelSelector.
export default function AiBackendButton({ agent, onOpen }) {
  if (!agent) return null;
  const label = agent.provider ? (agent.provider + ' / ' + agent.model) : 'aucun backend IA';
  const dotClass = 'ai-engine-dot ' + (agent.configured ? 'ok' : 'off');
  return (
    <button type="button" className="ai-engine-btn" onClick={onOpen}
      title={agent.configured ? 'Backend IA configuré — cliquer pour gérer'
        : 'Aucun backend IA actif — cliquer pour en configurer un'}>
      <span className={dotClass} aria-hidden="true" />
      <span className="ai-engine-label">Moteur IA</span>
      <span className="ai-engine-val">{label}</span>
      <span className="ai-engine-gear" aria-hidden="true">⚙</span>
    </button>
  );
}
