import React from 'react';

// Horizontal pipeline stepper: Nettoyage -> Transformation -> Integration
// -> Separation -> Model -> Evaluation. Reflects per-stage status.
export default function StageStepper({ stages, status, activeStage, onSelect }) {
  const statusMap = {};
  (status || []).forEach((s) => { statusMap[s.stage_id] = s; });

  return (
    <div className="stepper">
      {stages.map((st, idx) => {
        const s = statusMap[st.stage_id] || {};
        let cls = 'step step-' + st.kind;
        if (st.stage_id === activeStage) cls += ' step-active';
        if (s.ran && !s.stale) cls += ' step-done';
        if (s.stale) cls += ' step-stale';

        let state = 'en attente';
        if (s.stale) state = 'à rejouer';
        else if (s.ran) state = 'validée';
        else if (st.stage_id === activeStage) state = 'en cours';

        return (
          <React.Fragment key={st.stage_id}>
            <button className={cls} onClick={() => onSelect(st.stage_id)} title={st.objective}>
              <span className="step-badge">{st.index}</span>
              <span className="step-title">{st.title}</span>
              <span className="step-state">{state}</span>
            </button>
            {idx < stages.length - 1 ? (
              <span className={idx === 3 ? 'step-arrow step-arrow-major' : 'step-arrow'}>›</span>
            ) : null}
          </React.Fragment>
        );
      })}
    </div>
  );
}
