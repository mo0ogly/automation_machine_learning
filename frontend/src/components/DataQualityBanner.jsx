import React, { useState } from 'react';
import AssistButton from './AssistButton';
import AssistAnswer from './AssistAnswer';
import './data-quality.css';

// Ingestion data-quality warnings (from validation.py) surfaced to the analyst,
// each with an AI button that explains the issue and what to do — so a non-expert
// is never left alone in front of a dataset problem. Collapsible; the AI answer
// renders inline under the warning.
export default function DataQualityBanner({ warnings, onAssist, assistBusy, assistAnswers }) {
  const [open, setOpen] = useState(true);
  if (!warnings || !warnings.length) return null;
  return (
    <div className="dq-banner">
      <button type="button" className="dq-head" onClick={() => setOpen((o) => !o)}>
        <span className="dq-icon" aria-hidden="true">!</span>
        <span className="dq-title">
          {warnings.length} avertissement{warnings.length > 1 ? 's' : ''} sur la qualité des données
        </span>
        <span className="dq-toggle">{open ? '▾' : '▸'}</span>
      </button>
      {open ? (
        <ul className="dq-list">
          {warnings.map((w, i) => {
            const topic = 'dataquality:' + w.code;
            return (
              <li key={i} className="dq-item">
                <div className="dq-item-row">
                  <span className="dq-msg">{w.message}</span>
                  {onAssist ? (
                    <AssistButton topic={topic} text="IA" label={w.message}
                      onAssist={onAssist} busy={assistBusy} />
                  ) : null}
                </div>
                {w.columns && w.columns.length ? (
                  <div className="dq-cols">{w.columns.join(', ')}</div>
                ) : null}
                <AssistAnswer topic={topic} answers={assistAnswers} />
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}
