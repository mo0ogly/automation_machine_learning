import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import './ai-cockpit.css';

// Reusable inference-parameter editor (temperature, top_p, max_tokens, penalties).
// The field spec is the server's single source of truth (GET /api/ai/param-spec),
// so adding a parameter server-side surfaces here with no change. `value` holds
// the current overrides (a partial map); a field left at its default is not sent.
// Used both per-backend (persisted defaults, Backends IA) and per-request (Cockpit).
export default function InferenceSettings({ apiBase, value, onChange, title }) {
  const { t } = useTranslation('inference');
  const [fields, setFields] = useState([]);
  const [err, setErr] = useState(false);

  useEffect(() => {
    let alive = true;
    fetch(apiBase + '/api/ai/param-spec')
      .then((r) => r.json())
      .then((d) => { if (alive) setFields(d.fields || []); })
      .catch(() => { if (alive) setErr(true); });
    return () => { alive = false; };
  }, [apiBase]);

  const val = value || {};
  const isSet = (name) => Object.prototype.hasOwnProperty.call(val, name);
  const shown = (f) => (isSet(f.name) ? val[f.name] : f.default);

  const set = (name, raw) => {
    const next = { ...val };
    next[name] = raw;
    onChange(next);
  };
  const clear = (name) => {
    const next = { ...val };
    delete next[name];
    onChange(next);
  };

  if (err) return <div className="muted infp-err">{t('unavailable')}</div>;
  if (!fields.length) return <div className="muted infp-loading">{t('loading')}</div>;

  return (
    <div className="infp">
      {title ? <div className="infp-title">{title}</div> : null}
      {fields.map((f) => {
        const isInt = f.step >= 1;
        const current = shown(f);
        return (
          <div key={f.name} className="infp-row">
            <div className="infp-head">
              <label className="infp-label" title={f.help}>
                {f.label}
                {isSet(f.name) ? <span className="infp-badge" title={t('customValue')}>•</span> : null}
              </label>
              <span className="infp-controls">
                <input
                  className="infp-num" type="number" min={f.min} max={f.max} step={f.step}
                  value={current}
                  onChange={(e) => {
                    if (e.target.value === '') { clear(f.name); return; }
                    const n = isInt ? parseInt(e.target.value, 10) : parseFloat(e.target.value);
                    if (!Number.isNaN(n)) set(f.name, n);
                  }}
                />
                {isSet(f.name) ? (
                  <button type="button" className="infp-reset" title={t('resetDefault')}
                    onClick={() => clear(f.name)}>↺</button>
                ) : null}
              </span>
            </div>
            <input
              className="infp-range" type="range" min={f.min} max={f.max} step={f.step}
              value={current}
              onChange={(e) => set(f.name, isInt ? parseInt(e.target.value, 10) : parseFloat(e.target.value))}
            />
            <p className="infp-help">{f.help}</p>
          </div>
        );
      })}
    </div>
  );
}
