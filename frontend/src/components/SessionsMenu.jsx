import React, { useState, useEffect, useCallback } from 'react';

// Session manager (CRUD). Lists every persisted session and lets the expert
// re-open, rename or delete one — the app only tracks a single active session
// at a time, so without this menu past work (incl. trained models) is easy to
// lose track of. Reuses the .ai-modal / .ai-table styling for visual coherence.

const PTYPE_LABELS = {
  regression: 'Régression', classification: 'Classification',
  clustering: 'Clustering', anomaly: "Détection d'anomalies",
};

function fmtDate(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' });
  } catch (e) {
    return String(iso).slice(0, 16).replace('T', ' ');
  }
}

export default function SessionsMenu({ apiBase, currentId, onOpen, onClose, onDeleted }) {
  const [sessions, setSessions] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(null); // id being renamed
  const [draft, setDraft] = useState('');
  const [confirmDel, setConfirmDel] = useState(null); // id pending delete confirm

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const r = await fetch(apiBase + '/api/sessions');
      const d = await r.json();
      if (!r.ok) { setError(d.detail || 'Erreur de chargement'); return; }
      setSessions(d.sessions || []);
    } catch (e) {
      setError('API injoignable — le backend tourne-t-il sur :8000 ?');
    }
  }, [apiBase]);

  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  const openOne = async (id) => {
    setBusy(true); setError(null);
    try {
      const r = await fetch(apiBase + '/api/session/' + id);
      const d = await r.json();
      if (!r.ok) { setError(d.detail || 'Session introuvable'); setBusy(false); return; }
      onOpen(d);
    } catch (e) {
      setError('API injoignable.');
    }
    setBusy(false);
  };

  const saveName = async (id) => {
    const name = draft.trim();
    if (!name) return;
    setBusy(true); setError(null);
    try {
      const r = await fetch(apiBase + '/api/session/' + id, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: name }),
      });
      if (!r.ok) { const d = await r.json(); setError(d.detail || 'Échec du renommage'); }
      else { setEditing(null); await refresh(); }
    } catch (e) {
      setError('API injoignable.');
    }
    setBusy(false);
  };

  const remove = async (id) => {
    setBusy(true); setError(null);
    try {
      const r = await fetch(apiBase + '/api/session/' + id, { method: 'DELETE' });
      if (!r.ok) { setError('Échec de la suppression'); }
      else {
        setConfirmDel(null);
        if (id === currentId && onDeleted) onDeleted(id);
        await refresh();
      }
    } catch (e) {
      setError('API injoignable.');
    }
    setBusy(false);
  };

  return (
    <div className="ai-modal-overlay" onClick={onClose}>
      <div className="ai-modal glass-panel" onClick={(e) => e.stopPropagation()}>
        <div className="ai-modal-head">
          <h2>Mes sessions</h2>
          <button type="button" className="ai-modal-close" onClick={onClose} title="Fermer">×</button>
        </div>
        <p className="ai-modal-note">
          Rouvrez, renommez ou supprimez une analyse. Les sessions et leurs modèles sont conservés
          entre les redémarrages.
        </p>
        {error ? <div className="banner banner-block mb-2">{error}</div> : null}

        {sessions === null ? (
          <p className="ai-empty">Chargement…</p>
        ) : sessions.length === 0 ? (
          <p className="ai-empty">Aucune session enregistrée pour l'instant.</p>
        ) : (
          <table className="ai-table">
            <thead>
              <tr>
                <th>Nom</th><th>Type</th><th>Modèle</th><th>Taille</th><th>Modifiée</th><th />
              </tr>
            </thead>
            <tbody>
              {sessions.map((s) => {
                const sm = s.summary || {};
                const isCur = s.id === currentId;
                return (
                  <tr key={s.id} className={isCur ? 'ai-row-active' : ''}>
                    <td>
                      {editing === s.id ? (
                        <span className="ai-test-row">
                          <input value={draft} autoFocus onChange={(e) => setDraft(e.target.value)}
                            onKeyDown={(e) => { if (e.key === 'Enter') saveName(s.id); }} />
                          <button type="button" className="ai-btn ai-btn-primary" disabled={busy}
                            onClick={() => saveName(s.id)}>Valider</button>
                          <button type="button" className="ai-btn" onClick={() => setEditing(null)}>Annuler</button>
                        </span>
                      ) : (
                        <span>
                          <strong>{s.filename || '(sans nom)'}</strong>
                          {isCur ? <span className="ai-key-ok"> · active</span> : null}
                        </span>
                      )}
                    </td>
                    <td>{PTYPE_LABELS[sm.problem_type] || '—'}</td>
                    <td>{sm.model ? <span className="ai-key-ok">{sm.model}</span> : <span className="text-secondary">—</span>}</td>
                    <td>{sm.n_rows != null ? sm.n_rows + ' × ' + sm.n_cols : '—'}</td>
                    <td>{fmtDate(s.updated_at)}</td>
                    <td>
                      {confirmDel === s.id ? (
                        <span className="ai-test-row">
                          <span className="text-warning">Supprimer ?</span>
                          <button type="button" className="ai-btn ai-btn-danger" disabled={busy}
                            onClick={() => remove(s.id)}>Oui</button>
                          <button type="button" className="ai-btn" onClick={() => setConfirmDel(null)}>Non</button>
                        </span>
                      ) : (
                        <span className="ai-test-row">
                          <button type="button" className="ai-btn ai-btn-primary" disabled={busy || editing === s.id}
                            onClick={() => openOne(s.id)}>Ouvrir</button>
                          <button type="button" className="ai-btn" disabled={busy}
                            onClick={() => { setEditing(s.id); setDraft(s.filename || ''); }}>Renommer</button>
                          <button type="button" className="ai-btn ai-btn-danger" disabled={busy}
                            onClick={() => setConfirmDel(s.id)}>Supprimer</button>
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
