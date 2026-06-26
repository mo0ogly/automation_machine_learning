import React from 'react';

function Spark() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M12 2l1.7 5.1L19 9l-5.3 1.9L12 16l-1.7-5.1L5 9l5.3-1.9L12 2z" />
    </svg>
  );
}

// Specialized AI helper attached to a specific sub-step element. Clicking asks
// the assistant to explain that element; the answer is journalled (memory) and
// shown in the Copilot panel.
export default function AssistButton({ topic, label, onAssist, busy, text = 'Expliquer' }) {
  return (
    <button type="button" className="assist-btn" disabled={busy}
      title={'Demander à l’IA : ' + label} onClick={() => onAssist(topic, label)}>
      <Spark />{busy ? '…' : text}
    </button>
  );
}
