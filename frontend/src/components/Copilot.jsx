import React from 'react';

function Spark() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M12 2l1.7 5.1L19 9l-5.3 1.9L12 16l-1.7-5.1L5 9l5.3-1.9L12 2z" />
    </svg>
  );
}

const LEVELS = [{ id: 'novice', label: 'Novice' }, { id: 'expert', label: 'Expert' }];

// Assisted-analysis copilot. Replaces the decorative loop: it offers context-aware
// AI helpers and shows the analysis JOURNAL — every AI exchange is remembered and
// re-injected into later prompts, so the assistant builds on what it already said.
export default function Copilot({ stage, insights, level, busy, onAssist, onSetLevel }) {
  const meta = stage && stage.meta;
  const ran = !!(stage && stage.result);
  const quick = [
    { topic: 'diagnostics', label: 'Explique les diagnostics' },
    { topic: 'decision', label: 'Que dois-je décider ?' },
  ];
  if (ran) quick.push({ topic: 'result', label: 'Interprète le résultat' });

  const journal = [...(insights || [])].reverse();
  const fmt = (t) => (Array.isArray(t) ? t.join(' · ') : String(t || ''));

  return (
    <div className="copilot">
      <div className="copilot-head">
        <span className="copilot-title"><Spark /> Copilote d'analyse</span>
        <div className="level-toggle" role="group" aria-label="Niveau d'assistance">
          {LEVELS.map((l) => (
            <button key={l.id} type="button" className={level === l.id ? 'lvl lvl-on' : 'lvl'}
              onClick={() => onSetLevel(l.id)} title={'Explications niveau ' + l.label}>{l.label}</button>
          ))}
        </div>
      </div>

      {meta ? (
        <p className="copilot-ctx"><strong>{meta.title}</strong> — {meta.objective}</p>
      ) : <p className="copilot-ctx muted">Sélectionnez une étape.</p>}

      <div className="copilot-actions">
        {quick.map((q) => (
          <button key={q.topic} type="button" className="copilot-q" disabled={busy || !meta}
            onClick={() => onAssist(q.topic, q.label)}><Spark />{q.label}</button>
        ))}
      </div>

      <div className="copilot-journal">
        <div className="copilot-journal-head">
          <span>Journal d'analyse</span>
          <span className="copilot-count" title="Mémoire ré-injectée dans les prompts">{journal.length}</span>
        </div>
        {busy ? <div className="copilot-loading"><span className="spinner" /> L'assistant réfléchit…</div> : null}
        {journal.length === 0 && !busy ? (
          <p className="muted copilot-empty">
            Aucune note pour l'instant. Demande une explication à l'IA (ici ou via les boutons ✦ des
            sous-étapes) : chaque réponse est mémorisée et nourrit les recommandations suivantes.
          </p>
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
