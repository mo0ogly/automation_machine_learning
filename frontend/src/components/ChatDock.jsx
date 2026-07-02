import React, { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
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

function Bubble({ msg, t }) {
  const isUser = msg.role === 'user';
  return (
    <div className={'chat-msg ' + (isUser ? 'chat-msg-user' : 'chat-msg-ai')}>
      {!isUser ? (
        <div className="chat-msg-meta">
          <span className={'chat-src ' + (msg.source === 'llm' ? 'src-llm'
            : msg.source === 'error' ? 'src-error' : 'src-heur')}>
            {msg.source === 'llm' ? t('sourceAi') : (msg.source === 'error' ? t('sourceError') : t('sourceSystem'))}
          </span>
          {msg.model ? <span className="muted chat-model">{msg.model}</span> : null}
        </div>
      ) : null}
      <div className="chat-bubble">{msg.content}</div>
    </div>
  );
}

export default function ChatDock({ apiBase, sessionId, title }) {
  const { t } = useTranslation('chat');
  const [thread, setThread] = useState([]);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [params, setParams] = useState({});
  const [showSettings, setShowSettings] = useState(false);
  const [recalled, setRecalled] = useState([]);   // earlier exchanges surfaced by memory
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
    setRecalled([]);
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
      .then((d) => {
        if (sidRef.current !== mySid) return;
        setThread(d.thread || []);
        setRecalled(Array.isArray(d.recalled) ? d.recalled : []);
      })
      .catch((c) => {
        if (sidRef.current !== mySid) return;   // user moved on: drop this result
        // Roll back the optimistic echo and restore the draft so nothing is lost.
        setThread((t) => t.filter((m) => m.id !== 'pending-user'));
        setDraft((d) => d || message);
        setErr(c === 400 ? t('errEmptyMessage') : t('errUnreachable'));
      })
      .finally(() => { if (sidRef.current === mySid) setBusy(false); });
  };

  const clear = () => {
    if (!sessionId || !thread.length || busy) return;
    if (!window.confirm(t('confirmClear'))) return;
    fetch(apiBase + '/api/session/' + sessionId + '/chat', { method: 'DELETE' })
      .then((r) => { if (r.ok) { setThread([]); setRecalled([]); } }).catch(() => {});
  };

  const onKey = (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); send(); }
  };

  if (!sessionId) {
    return (
      <div className="chatdock" data-prompt-loc="chat">
        <div className="chatdock-head"><span className="chatdock-title"><Spark /> {title || t('defaultTitle')}</span></div>
        <p className="muted chatdock-empty">{t('noSession')}</p>
      </div>
    );
  }

  return (
    <div className="chatdock" data-prompt-loc="chat">
      <div className="chatdock-head">
        <span className="chatdock-title"><Spark /> {title || t('defaultTitle')}</span>
        <span className="chatdock-actions">
          <button type="button" className={'chatdock-cog' + (showSettings ? ' on' : '')}
            onClick={() => setShowSettings((s) => !s)} title={t('settingsTooltip')}>
            {t('settings')}
          </button>
          <button type="button" className="chatdock-clear" onClick={clear}
            disabled={busy || !thread.length} title={t('clearTooltip')}>{t('clear')}</button>
        </span>
      </div>

      {showSettings ? (
        <div className="chatdock-settings">
          <InferenceSettings apiBase={apiBase} value={params} onChange={setParams}
            title={t('conversationSettingsTitle')} />
        </div>
      ) : null}

      <div className="chatdock-list" ref={listRef}>
        {thread.length === 0 && !busy ? (
          <p className="muted chatdock-empty">{t('emptyThread')}</p>
        ) : null}
        {thread.map((m) => <Bubble key={m.id} msg={m} t={t} />)}
        {busy ? <div className="chat-thinking"><span className="spinner" /> {t('thinking')}</div> : null}
      </div>

      {recalled.length ? (
        <details className="chat-recall">
          <summary>{t('recallSummary', { count: recalled.length })}</summary>
          <ul>
            {recalled.map((e, i) => (
              <li key={i}><span className="chat-recall-q">{e.user}</span></li>
            ))}
          </ul>
        </details>
      ) : null}

      {err ? <div className="banner banner-block chatdock-err">{err}</div> : null}

      <div className="chatdock-compose">
        <textarea
          className="chatdock-input" rows={2} value={draft} placeholder={t('composePlaceholder')}
          onChange={(e) => setDraft(e.target.value)} onKeyDown={onKey} disabled={busy}
        />
        <button type="button" className="btn btn-ai chatdock-send" onClick={send}
          disabled={busy || !draft.trim()}>{busy ? '…' : t('send')}</button>
      </div>
    </div>
  );
}
