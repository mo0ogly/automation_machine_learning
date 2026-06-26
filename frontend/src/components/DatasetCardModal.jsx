import React, { useState, useEffect } from 'react';

// Data card for a demo dataset: summary, badges, schema/notes sections, source.
// Fetched from GET /api/dataset-card/{name}; rendered in the shared modal shell.
export default function DatasetCardModal({ apiBase, name, onClose }) {
  const [card, setCard] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    let alive = true;
    fetch(apiBase + '/api/dataset-card/' + name)
      .then((r) => r.json())
      .then((d) => { if (alive) { if (d.detail) setErr(d.detail); else setCard(d); } })
      .catch(() => { if (alive) setErr('Fiche injoignable.'); });
    return () => { alive = false; };
  }, [apiBase, name]);

  return (
    <div className="ai-modal-overlay" onClick={onClose}>
      <div className="ai-modal glass-panel" onClick={(e) => e.stopPropagation()}>
        <div className="ai-modal-head">
          <h2>{card ? card.title : 'Fiche du jeu de données'}</h2>
          <button type="button" className="ai-modal-close" onClick={onClose} aria-label="Fermer">×</button>
        </div>
        {err ? <div className="banner banner-block">{err}</div> : null}
        {card ? (
          <div className="dscard">
            <div className="dscard-badges">
              <span className="dscard-badge">{card.type}</span>
              <span className="dscard-badge">{card.rows} lignes · {card.cols} colonnes</span>
              {card.synthetic
                ? <span className="dscard-badge dscard-synth">synthétique</span>
                : <span className="dscard-badge">données réelles</span>}
            </div>
            <p className="dscard-summary">{card.summary}</p>
            <p className="dscard-target"><strong>Cible :</strong> {card.target}</p>
            {(card.sections || []).map((s, i) => (
              <div key={i} className="dscard-section">
                <h4>{s.heading}</h4>
                {s.text ? <p>{s.text}</p> : null}
                {s.table ? (
                  <table className="dscard-table"><tbody>
                    {s.table.map((row, j) => (
                      <tr key={j}><td className="dscard-col">{row[0]}</td><td>{row[1]}</td></tr>
                    ))}
                  </tbody></table>
                ) : null}
              </div>
            ))}
            <p className="dscard-source"><strong>Source :</strong> {card.source}</p>
          </div>
        ) : (!err ? <p className="muted">Chargement…</p> : null)}
      </div>
    </div>
  );
}
