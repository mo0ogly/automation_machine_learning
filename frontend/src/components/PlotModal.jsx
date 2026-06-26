import React, { useEffect } from 'react';

// Full-screen detail view for a diagnostic figure. The grids rendered inline are
// readable only enlarged, so every plot is click-to-zoom. Closes on backdrop
// click, the ✕ button, or Escape.
export default function PlotModal({ src, caption, onClose }) {
  useEffect(() => {
    if (!src) return undefined;
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [src, onClose]);

  if (!src) return null;
  return (
    <div className="plot-modal" onClick={onClose} role="dialog" aria-modal="true">
      <div className="plot-modal-inner" onClick={(e) => e.stopPropagation()}>
        <div className="plot-modal-bar">
          <span className="plot-modal-cap">{caption || 'Figure'}</span>
          <button type="button" className="plot-modal-x" onClick={onClose} aria-label="Fermer">✕</button>
        </div>
        <div className="plot-modal-body">
          <img src={src} alt={caption || 'figure agrandie'} className="plot-modal-img" />
        </div>
      </div>
    </div>
  );
}
