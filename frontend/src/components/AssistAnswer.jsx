import React from 'react';

// Inline answer from a sub-step / per-graph / per-badge AI helper, shown right
// where it was asked (in addition to being recorded in the Copilot journal).
// Keyed by `topic`: renders nothing until an answer for that topic arrives.
export default function AssistAnswer({ topic, answers, onApply }) {
  const a = answers && answers[topic];
  if (!a) return null;
  const isLLM = a.source === 'llm';
  const sc = a.suggested_config;
  const hasAction = sc && Object.keys(sc).length > 0;
  const fmtVal = (v) => (Array.isArray(v) ? v.length + ' élément(s)' : String(v));
  return (
    <div className="assist-answer">
      <div className="assist-answer-head">
        <span className={isLLM ? 'reco-badge reco-llm' : 'reco-badge reco-heur'}>Assistant IA</span>
        {a.model ? <span className="reco-model">{a.model}</span> : null}
      </div>
      <ul className="reco-rationale">{(a.explanation || []).map((x, i) => <li key={i}>{x}</li>)}</ul>
      {a.takeaway ? <p className="assist-takeaway">{a.takeaway}</p> : null}
      {hasAction && onApply ? (
        <div className="assist-action">
          <div className="assist-action-keys">
            {Object.entries(sc).map(([k, v]) => (
              <span key={k} className="reco-chip" title={Array.isArray(v) ? v.join(', ') : undefined}>
                {k} = {fmtVal(v)}
              </span>
            ))}
          </div>
          <button type="button" className="btn btn-primary assist-apply" onClick={() => onApply(sc)}>
            Appliquer cette action
          </button>
        </div>
      ) : null}
    </div>
  );
}
