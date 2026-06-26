import React from 'react';
import ColumnTable from './ColumnTable';
import AssistButton from './AssistButton';
import AssistAnswer from './AssistAnswer';

// Renders a single config control from a backend schema descriptor.
function Control({ ctrl, value, onChange }) {
  const v = value !== undefined && value !== null ? value : ctrl.default;

  if (ctrl.type === 'select') {
    return (
      <label className="cfg-row">
        <span className="cfg-label">{ctrl.label}</span>
        <select className="cfg-input" value={v} onChange={(e) => onChange(ctrl.name, e.target.value)}>
          {ctrl.options.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
        {ctrl.help ? <span className="cfg-help">{ctrl.help}</span> : null}
      </label>
    );
  }

  if (ctrl.type === 'toggle') {
    return (
      <label className="cfg-row cfg-toggle">
        <span className="cfg-label">
          <input type="checkbox" checked={!!v} onChange={(e) => onChange(ctrl.name, e.target.checked)} />
          {ctrl.label}
        </span>
        {ctrl.help ? <span className="cfg-help">{ctrl.help}</span> : null}
      </label>
    );
  }

  if (ctrl.type === 'range') {
    return (
      <label className="cfg-row">
        <span className="cfg-label">{ctrl.label} <strong className="cfg-val">{v}</strong></span>
        <input
          type="range"
          min={ctrl.min}
          max={ctrl.max}
          step={ctrl.step}
          value={v}
          onChange={(e) => onChange(ctrl.name, parseFloat(e.target.value))}
        />
        {ctrl.help ? <span className="cfg-help">{ctrl.help}</span> : null}
      </label>
    );
  }

  // number
  return (
    <label className="cfg-row">
      <span className="cfg-label">{ctrl.label}</span>
      <input
        className="cfg-input"
        type="number"
        min={ctrl.min}
        max={ctrl.max}
        value={v}
        onChange={(e) => onChange(ctrl.name, e.target.value === '' ? '' : parseFloat(e.target.value))}
      />
      {ctrl.help ? <span className="cfg-help">{ctrl.help}</span> : null}
    </label>
  );
}

// Renders the full config form for a stage. `highlight` marks the keys the
// agent just proposed, so the expert sees what changed.
export default function ConfigControls({ schema, config, onChange, highlight = {},
  onAssist, assistBusy, assistAnswers, onApplyAssist }) {
  if (!schema || !schema.length) {
    return <p className="muted">Aucun paramètre à régler pour cette étape.</p>;
  }
  const tables = schema.filter((c) => c.type === 'column_table');
  const simple = schema.filter((c) => c.type !== 'column_table');
  return (
    <div className="cfg-wrap">
      {tables.map((ctrl) => (
        <ColumnTable key={ctrl.name} ctrl={ctrl} value={config[ctrl.name]} onChange={onChange} />
      ))}
      {simple.length ? (
        <div className="cfg-grid">
          {simple.map((ctrl) => (
            <div key={ctrl.name} className={highlight[ctrl.name] ? 'cfg-cell cfg-highlight' : 'cfg-cell'}>
              <Control ctrl={ctrl} value={config[ctrl.name]} onChange={onChange} />
              {onAssist ? (
                <div className="cfg-assist">
                  <AssistButton topic={'param:' + ctrl.name} label={ctrl.label} text="IA"
                    onAssist={onAssist} busy={assistBusy} />
                </div>
              ) : null}
              <AssistAnswer topic={'param:' + ctrl.name} answers={assistAnswers} onApply={onApplyAssist} />
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
