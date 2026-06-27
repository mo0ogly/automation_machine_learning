import React, { useState, useEffect, useCallback } from 'react';

// Trained-models browser (top-right header). A model lives inside the session
// that produced it, so this is a focused, cross-session view of every session
// that carries a fitted model: download its .pkl, or open the session to
// inspect / re-run it. Data comes from /api/sessions (summary.model) — no extra
// endpoint. Reuses the .ai-modal / .ai-table styling for coherence.

const PTYPE_LABELS = {
  regression: 'Régression', classification: 'Classification',
  clustering: 'Clustering', anomaly: "Détection d'anomalies",
};

// A model is "cyber" when its dataset name matches a security keyword. Adjust
// this list to taste — it drives the pinned "Modèles cyber" section + badge.
const CYBER_KEYWORDS = ['cyber', 'prompt', 'injection', 'fraud', 'malware', 'phishing',
  'intrusion', 'threat', 'attack', 'exploit', 'vuln', 'anomal', 'transaction'];
const isCyber = (name) => {
  const n = (name || '').toLowerCase();
  return CYBER_KEYWORDS.some((k) => n.includes(k));
};

function fmtDate(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' });
  } catch (e) {
    return String(iso).slice(0, 16).replace('T', ' ');
  }
}

export default function ModelsMenu({ apiBase, onClose }) {
  const [models, setModels] = useState(null);
  const [error, setError] = useState(null);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const r = await fetch(apiBase + '/api/sessions');
      const d = await r.json();
      if (!r.ok) { setError(d.detail || 'Erreur de chargement'); return; }
      // Keep only sessions that carry a trained model.
      setModels((d.sessions || []).filter((s) => s.summary && s.summary.model));
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

  // Re-open the session that owns the model: persist the pointer, then reload so
  // the Pipeline view rehydrates it (same path as the localStorage restore).
  const openSession = (id) => {
    try { localStorage.setItem('ml_session', id); } catch (e) { /* ignore */ }
    window.location.reload();
  };

  // Cyber models are the heart of the thesis — surface them in a pinned section.
  // Detection by dataset-name keywords (adjustable here).
  const cyber = (models || []).filter((s) => isCyber(s.filename));
  const others = (models || []).filter((s) => !isCyber(s.filename));

  const renderTable = (list, cyberFlag) => (
    <table className="ai-table">
      <thead>
        <tr>
          <th>Jeu de données</th><th>Algorithme</th><th>Type</th><th>Taille</th><th>Modifié</th><th />
        </tr>
      </thead>
      <tbody>
        {list.map((s) => {
          const sm = s.summary || {};
          return (
            <tr key={s.id} className={cyberFlag ? 'cyber-row' : ''}>
              <td>
                <strong>{s.filename || '(sans nom)'}</strong>
                {cyberFlag ? <span className="badge-cyber">CYBER</span> : null}
              </td>
              <td><span className="ai-key-ok">{sm.model}</span></td>
              <td>{PTYPE_LABELS[sm.problem_type] || '—'}</td>
              <td>{sm.n_rows != null ? sm.n_rows + ' × ' + sm.n_cols : '—'}</td>
              <td>{fmtDate(s.updated_at)}</td>
              <td>
                <span className="ai-test-row">
                  <a className="ai-btn ai-btn-primary" href={apiBase + '/api/session/' + s.id + '/export-bundle'}
                    target="_blank" rel="noreferrer" title="Bundle Python autonome (modèle + données + code + predict.py)">Bundle .zip</a>
                  <a className="ai-btn" href={apiBase + '/api/session/' + s.id + '/download-model'}
                    target="_blank" rel="noreferrer" title="Modèle brut (features déjà transformées)">.pkl</a>
                  <button type="button" className="ai-btn" onClick={() => openSession(s.id)}>Ouvrir</button>
                </span>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );

  return (
    <div className="ai-modal-overlay" onClick={onClose}>
      <div className="ai-modal glass-panel" onClick={(e) => e.stopPropagation()}>
        <div className="ai-modal-head">
          <h2>Modèles entraînés</h2>
          <button type="button" className="ai-modal-close" onClick={onClose} title="Fermer">×</button>
        </div>
        <p className="ai-modal-note">
          Tous les modèles construits, toutes sessions confondues. Téléchargez le .pkl prêt à servir,
          ou ouvrez la session pour l'inspecter et le ré-exécuter.
        </p>
        {error ? <div className="banner banner-block mb-2">{error}</div> : null}

        {models === null ? (
          <p className="ai-empty">Chargement…</p>
        ) : models.length === 0 ? (
          <p className="ai-empty">
            Aucun modèle entraîné pour l'instant. Terminez l'étape « Modélisation » d'une session.
          </p>
        ) : (
          <>
            {cyber.length ? (
              <div className="cyber-block">
                <h3 className="cyber-head">
                  <span className="badge-cyber">CYBER</span>
                  Modèles cyber <span className="muted">({cyber.length})</span>
                </h3>
                {renderTable(cyber, true)}
              </div>
            ) : null}
            {others.length ? (
              <>
                <h3 className="other-head">Autres modèles <span className="muted">({others.length})</span></h3>
                {renderTable(others, false)}
              </>
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}
