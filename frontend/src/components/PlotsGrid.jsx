import React from 'react';

// Inline server-rendered figures, shared across the monitoring panels. Each plot
// is either a data-URI string or {img, caption}; captions render when present so
// the jitter section, the drift report and the stability cards look identical.
export default function PlotsGrid({ plots, alt }) {
  if (!plots || !plots.length) return null;
  return (
    <div className="plots-grid mon-plots">
      {plots.map((p, i) => {
        const src = typeof p === 'string' ? p : p.img;
        const cap = typeof p === 'string' ? '' : (p.caption || '');
        return (
          <figure key={i} className="plot-fig">
            <img src={src} alt={cap || alt || 'figure'} className="plot-img" decoding="async" />
            {cap ? <figcaption className="plot-cap"><span className="plot-cap-txt">{cap}</span></figcaption> : null}
          </figure>
        );
      })}
    </div>
  );
}
