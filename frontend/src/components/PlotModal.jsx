import React, { useEffect } from 'react';
import { useTranslation } from 'react-i18next';

// Full-screen detail view for a diagnostic figure. The grids rendered inline are
// readable only enlarged, so every plot is click-to-zoom. Closes on backdrop
// click, the ✕ button, or Escape.
export default function PlotModal({ src, caption, onClose }) {
  const { t } = useTranslation('plot');
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
          <span className="plot-modal-cap">{caption || t('figureDefault')}</span>
          <button type="button" className="plot-modal-x" onClick={onClose} aria-label={t('close')}>✕</button>
        </div>
        <div className="plot-modal-body">
          <img src={src} alt={caption || t('altZoomed')} className="plot-modal-img" />
        </div>
      </div>
    </div>
  );
}
