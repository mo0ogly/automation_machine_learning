import React from 'react';
import { useTranslation } from 'react-i18next';

// The per-stage agent's refinement proposal (the "affinage").
// The expert can apply each suggestion individually (partial) or all at once
// (total); either way the config controls below stay manually editable.
export default function AgentRecommendation({ reco, loading, onApply, onApplyKey, currentConfig = {} }) {
  const { t } = useTranslation('agentRec');
  if (loading) {
    return (
      <div className="reco-card reco-loading">
        <div className="spinner" />
        <p className="muted">{t('loading')}</p>
      </div>
    );
  }
  if (!reco) return null;

  const isLLM = reco.source === 'llm';
  const conf = Math.round((reco.confidence || 0) * 100);
  const suggested = reco.suggested_config || {};
  const entries = Object.entries(suggested);
  const hasSuggestion = entries.length > 0;
  const allApplied = hasSuggestion && entries.every(([k, v]) => String(currentConfig[k]) === String(v));

  // Lists (e.g. dropped_features) read better as a count than a raw join.
  const fmtVal = (v) => (Array.isArray(v)
    ? (v.length ? t('varsToRemove', { count: v.length }) : t('noneToRemove'))
    : String(v));

  return (
    <div className="reco-card">
      <div className="reco-head">
        <span className={isLLM ? 'reco-badge reco-llm' : 'reco-badge reco-heur'}>
          {isLLM ? t('sourceLlm') : t('sourceHeuristic')}
        </span>
        {reco.model ? <span className="reco-model">{reco.model}</span> : null}
        <span className="reco-conf">{t('confidence', { conf })}</span>
      </div>

      {reco.summary ? <p className="reco-summary">{reco.summary}</p> : null}

      {reco.rationale && reco.rationale.length ? (
        <ul className="reco-rationale">
          {reco.rationale.map((r, i) => <li key={i}>{r}</li>)}
        </ul>
      ) : null}

      {reco.reason ? <p className="reco-reason">{reco.reason}</p> : null}
      {reco.risk ? <p className="reco-risk">{t('risk', { risk: reco.risk })}</p> : null}

      {hasSuggestion ? (
        <>
          <p className="reco-hint">{t('hint')}</p>
          <div className="reco-suggestions">
            {entries.map(([k, v]) => {
              const applied = String(currentConfig[k]) === String(v);
              return (
                <div key={k} className={applied ? 'reco-sug reco-sug-applied' : 'reco-sug'}>
                  <span className="reco-chip" title={Array.isArray(v) ? v.join(', ') : undefined}>{k} = {fmtVal(v)}</span>
                  {applied ? (
                    <span className="reco-applied">{t('applied')}</span>
                  ) : (
                    <button className="reco-key-btn" onClick={() => onApplyKey(k, v)}>{t('apply')}</button>
                  )}
                </div>
              );
            })}
          </div>
          <button className="btn btn-primary reco-apply" onClick={onApply} disabled={allApplied}>
            {allApplied ? t('allApplied') : t('applyAll')}
          </button>
        </>
      ) : (
        <p className="muted">{t('noChange')}</p>
      )}
    </div>
  );
}
