import React, { useState, useEffect } from 'react';
import { useTranslation, Trans } from 'react-i18next';

// Data card for a demo dataset: summary, badges, schema/notes sections, source.
// Fetched from GET /api/dataset-card/{name}; rendered in the shared modal shell.
export default function DatasetCardModal({ apiBase, name, onClose }) {
  const { t } = useTranslation('dataset');
  const [card, setCard] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    let alive = true;
    fetch(apiBase + '/api/dataset-card/' + name)
      .then((r) => r.json())
      .then((d) => { if (alive) { if (d.detail) setErr(d.detail); else setCard(d); } })
      .catch(() => { if (alive) setErr(t('unreachable')); });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiBase, name]);

  return (
    <div className="ai-modal-overlay" onClick={onClose}>
      <div className="ai-modal glass-panel" onClick={(e) => e.stopPropagation()}>
        <div className="ai-modal-head">
          <h2>{card ? card.title : t('defaultTitle')}</h2>
          <button type="button" className="ai-modal-close" onClick={onClose} aria-label={t('close')}>×</button>
        </div>
        {err ? <div className="banner banner-block">{err}</div> : null}
        {card ? (
          <div className="dscard">
            <div className="dscard-badges">
              <span className="dscard-badge">{card.type}</span>
              <span className="dscard-badge">{t('rowsCols', { rows: card.rows, cols: card.cols })}</span>
              {card.synthetic
                ? <span className="dscard-badge dscard-synth">{t('synthetic')}</span>
                : <span className="dscard-badge">{t('realData')}</span>}
            </div>
            <p className="dscard-summary">{card.summary}</p>
            <p className="dscard-target">
              <Trans i18nKey="target" ns="dataset" components={{ strong: <strong /> }} values={{ target: card.target }} />
            </p>
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
            <p className="dscard-source">
              <Trans i18nKey="source" ns="dataset" components={{ strong: <strong /> }} values={{ source: card.source }} />
            </p>
          </div>
        ) : (!err ? <p className="muted">{t('loading')}</p> : null)}
      </div>
    </div>
  );
}
