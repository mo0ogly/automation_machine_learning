import React from 'react';

// Dropdown to switch the agent's Groq LLM at runtime (POST /api/agent/model).
export default function ModelSelector({ agent, apiBase, onChange }) {
  if (!agent || !agent.available_models || !agent.available_models.length) return null;

  const change = async (id) => {
    try {
      const res = await fetch(apiBase + '/api/agent/model', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model: id }),
      });
      const data = await res.json();
      if (res.ok && onChange) onChange(data);
    } catch (e) {
      /* keep current selection on failure */
    }
  };

  return (
    <label className="model-select" title="Moteur LLM de l'agent (Groq) — prix indicatif entrée / sortie par million de tokens">
      <span className="model-select-label">Moteur</span>
      <select value={agent.model} onChange={(e) => change(e.target.value)}>
        {agent.available_models.map((m) => (
          <option key={m.id} value={m.id}>{m.label} — {m.price}</option>
        ))}
      </select>
    </label>
  );
}
