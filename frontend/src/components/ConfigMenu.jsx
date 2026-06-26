import React, { useState, useRef, useEffect } from 'react';

// Lab-bar "Configuration" dropdown. Groups settings into sections; the "IA"
// submenu opens the AI backends panel. Sits next to AiBackendButton (which keeps
// its role of showing/opening the active backend) and is built to grow more
// sections later without touching the bar layout.
export default function ConfigMenu({ onOpenAi }) {
  const [open, setOpen] = useState(false);
  const [sub, setSub] = useState(null); // id of the expanded submenu
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const onDoc = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const close = () => { setOpen(false); setSub(null); };
  const toggleSub = (id) => setSub((s) => (s === id ? null : id));

  return (
    <div className="cfg-menu" ref={ref}>
      <button type="button" className="cfg-menu-btn" onClick={() => setOpen((o) => !o)}
        aria-haspopup="true" aria-expanded={open} title="Configuration">
        <span className="cfg-menu-gear" aria-hidden="true">⚙</span>
        <span>Configuration</span>
      </button>
      {open ? (
        <div className="cfg-menu-pop glass-panel" role="menu">
          <button type="button" className="cfg-menu-item cfg-menu-parent" role="menuitem"
            aria-expanded={sub === 'ia'} onClick={() => toggleSub('ia')}>
            <span>IA</span>
            <span className="cfg-menu-caret" aria-hidden="true">{sub === 'ia' ? '▾' : '▸'}</span>
          </button>
          {sub === 'ia' ? (
            <div className="cfg-menu-sub">
              <button type="button" className="cfg-menu-item" role="menuitem"
                onClick={() => { close(); onOpenAi(); }}>
                Backends IA…
              </button>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
