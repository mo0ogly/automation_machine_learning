import React, { useEffect, useRef, useState } from 'react';
import InferenceSettings from './InferenceSettings';
import './ai-cockpit.css';

// AI cockpit — a real multi-turn conversation with the copilot, grounded in the
// active session (context + memory) server-side. Self-contained: it owns its
// thread (GET/POST/DELETE /api/session/{id}/chat) and a per-request inference
// override panel. Reused in the Pipeline (Copilot) and Exploit views.
function Spark() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M12 2l1.7 5.1L19 9l-5.3 1.9L12 16l-1.7-5.1L5 9l5.3-1.9L12 2z" />
    </svg>
  );
}

function Bubble({ msg }) {
  const isUser = msg.role === 'user';
  return (
    <div className={'chat-msg ' + (isUser ? 'chat-msg-user' : 'chat-msg-ai')}>
      {!isUser ? (
        <div className="chat-msg-meta">
          <span className={'chat-src ' + (msg.source === 'llm' ? 'src-llm'
            : msg.source === 'error' ? 'src-error' : 'src-heur')}>
            {msg.source === 'llm' ? 'IA' : (msg.source === 'error' ? 'erreur' : 'système')}
          </span>
          {msg.model ? <span className="muted chat-model">{msg.model}</span> : null}
        </div>
      ) : null}
      <div className="chat-bubble">{msg.content}</div>
    </div>
  );
}

export default function ChatDock({ apiBase, sessionId, title }) {
  const [thread, setThread] = useState([]);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [params, setParams] = useState({});
  const [showSettings, setShowSettings] = useState(false);
  const listRef = useRef(null);
  // Always holds the session the component is currently bound to, so async
  // handlers can drop stale responses when the user switches session mid-flight.
  const sidRef = useRef(sessionId);
  sidRef.current = sessionId;

  useEffect(() => {
    // Switching session resets the transient UI (error banner, draft) so state
    // from the previous session never bleeds into the new one.
    setErr(null);
    setDraft('');
    if (!sessionId) { setThread([]); return; }
    const mySid = sessionId;
    fetch(apiBase + '/api/session/' + sessionId + '/chat')
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((d) => { if (sidRef.current === mySid) setThread(d.thread || []); })
      .catch(() => { if (sidRef.current === mySid) setThread([]); });
  }, [apiBase, sessionId]);

  useEffect(() => {
    if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight;
  }, [thread, busy]);

  const send = () => {
    const message = draft.trim();
    if (!message || !sessionId || busy) return;
    const mySid = sessionId;
    setBusy(true);
    setErr(null);
    // Optimistic echo of the user's turn while the copilot thinks.
    setThread((t) => [...t, { id: 'pending-user', role: 'user', content: message }]);
    setDraft('');
    const body = { message };
    if (Object.keys(params).length) body.params = params;
    fetch(apiBase + '/api/session/' + sessionId + '/chat', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((d) => { if (sidRef.current === mySid) setThread(d.thread || []); })
      .catch((c) => {
        if (sidRef.current !== mySid) return;   // user moved on: drop this result
        // Roll back the optimistic echo and restore the draft so nothing is lost.
        setThread((t) => t.filter((m) => m.id !== 'pending-user'));
        setDraft((d) => d || message);
        setErr(c === 400 ? 'Message vide.' : 'Le copilote est injoignable.');
      })
      .finally(() => { if (sidRef.current === mySid) setBusy(false); });
  };

  const clear = () => {
    if (!sessionId || !thread.length || busy) return;
    if (!window.confirm('Effacer toute la conversation ?')) return;
    fetch(apiBase + '/api/session/' + sessionId + '/chat', { method: 'DELETE' })
      .then((r) => { if (r.ok) setThread([]); }).catch(() => {});
  };

  const onKey = (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); send(); }
  };

  if (!sessionId) {
    return (
      <div className="chatdock" data-prompt-loc="chat">
        <div className="chatdock-head"><span className="chatdock-title"><Spark /> {title || 'Cockpit IA'}</span></div>
        <p className="muted chatdock-empty">
          Aucune session active. Charge un jeu de données dans l'onglet Pipeline pour dialoguer
          avec le copilote à propos de tes données et de ton modèle.
        </p>
      </div>
    );
  }

  return (
    <div className="chatdock" data-prompt-loc="chat">
      <div className="chatdock-head">
        <span className="chatdock-title"><Spark /> {title || 'Cockpit IA'}</span>
        <span className="chatdock-actions">
          <button type="button" className={'chatdock-cog' + (showSettings ? ' on' : '')}
            onClick={() => setShowSettings((s) => !s)} title="Réglages d'inférence (température, tokens…)">
            Réglages
          </button>
          <button type="button" className="chatdock-clear" onClick={clear}
            disabled={busy || !thread.length} title="Effacer la conversation">Effacer</button>
        </span>
      </div>

      {showSettings ? (
        <div className="chatdock-settings">
          <InferenceSettings apiBase={apiBase} value={params} onChange={setParams}
            title="Paramètres de cette conversation (surchargent le backend actif)" />
        </div>
      ) : null}

      <div className="chatdock-list" ref={listRef}>
        {thread.length === 0 && !busy ? (
          <p className="muted chatdock-empty">
            Pose une question sur ton jeu de données, une étape du pipeline ou ton modèle. Le
            copilote tient compte du contexte et de tout l'historique de la conversation.
          </p>
        ) : null}
        {thread.map((m) => <Bubble key={m.id} msg={m} />)}
        {busy ? <div className="chat-thinking"><span className="spinner" /> Le copilote réfléchit…</div> : null}
      </div>

      {err ? <div className="banner banner-block chatdock-err">{err}</div> : null}

      <div className="chatdock-compose">
        <textarea
          className="chatdock-input" rows={2} value={draft} placeholder="Écris ta question… (Ctrl+Entrée pour envoyer)"
          onChange={(e) => setDraft(e.target.value)} onKeyDown={onKey} disabled={busy}
        />
        <button type="button" className="btn btn-ai chatdock-send" onClick={send}
          disabled={busy || !draft.trim()}>{busy ? '…' : 'Envoyer'}</button>
      </div>
    </div>
  );
}
