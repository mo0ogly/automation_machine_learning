import React from 'react';
import { useTranslation } from 'react-i18next';

function Spark() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M12 2l1.7 5.1L19 9l-5.3 1.9L12 16l-1.7-5.1L5 9l5.3-1.9L12 2z" />
    </svg>
  );
}

// Assisted-analysis copilot. Replaces the decorative loop: it offers context-aware
// AI helpers and shows the analysis JOURNAL — every AI exchange is remembered and
// re-injected into later prompts, so the assistant builds on what it already said.
export default function Copilot({ stage, insights, level, busy, onAssist, onSetLevel }) {
  const { t } = useTranslation('copilot');
  const LEVELS = [{ id: 'novice', label: t('levelNovice') }, { id: 'expert', label: t('levelExpert') }];
  const meta = stage && stage.meta;
  const ran = !!(stage && stage.result);
  const quick = [
    { topic: 'diagnostics', label: t('quickDiagnostics') },
    { topic: 'decision', label: t('quickDecision') },
  ];
  if (ran) quick.push({ topic: 'result', label: t('quickResult') });

  const journal = [...(insights || [])].reverse();
  const fmt = (t) => (Array.isArray(t) ? t.join(' · ') : String(t || ''));

  return (
    <div className="copilot">
      <div className="copilot-head">
        <span className="copilot-title"><Spark /> {t('title')}</span>
        <div className="level-toggle" role="group" aria-label={t('levelGroupAria')}>
          {LEVELS.map((l) => (
            <button key={l.id} type="button" className={level === l.id ? 'lvl lvl-on' : 'lvl'}
              onClick={() => onSetLevel(l.id)} title={t('levelTitle', { level: l.label })}>{l.label}</button>
          ))}
        </div>
      </div>

      {meta ? (
        <p className="copilot-ctx"><strong>{meta.title}</strong> — {meta.objective}</p>
      ) : <p className="copilot-ctx muted">{t('selectStage')}</p>}

      <div className="copilot-actions">
        {quick.map((q) => (
          <button key={q.topic} type="button" className="copilot-q" disabled={busy || !meta}
            onClick={() => onAssist(q.topic, q.label)}><Spark />{q.label}</button>
        ))}
      </div>

      <div className="copilot-journal">
        <div className="copilot-journal-head">
          <span>{t('journalTitle')}</span>
          <span className="copilot-count" title={t('memoryTitle')}>{journal.length}</span>
        </div>
        {busy ? <div className="copilot-loading"><span className="spinner" /> {t('thinking')}</div> : null}
        {journal.length === 0 && !busy ? (
          <p className="muted copilot-empty">{t('empty')}</p>
        ) : null}
        <ul className="journal-list">
          {journal.map((e) => (
            <li key={e.id} className="journal-item">
              <div className="journal-meta">
                <span className="journal-label">{e.label}</span>
                <span className={e.source === 'llm' ? 'journal-src src-llm' : 'journal-src src-heur'}>
                  {e.stage} · {e.topic}
                </span>
              </div>
              <div className="journal-text">{fmt(e.text)}</div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
