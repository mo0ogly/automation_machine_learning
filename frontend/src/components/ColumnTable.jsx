import React from 'react';

const DEFAULT_COLS = [
  { key: 'column', label: 'Colonne' },
  { key: 'type', label: 'Type' },
  { key: 'missing_pct', label: 'Manq.%' },
  { key: 'n_unique', label: 'Distinct' },
  { key: 'recommended', label: 'Avis' },
  { key: 'reason', label: 'Pourquoi' },
];

// Per-column keep/drop table. The control value is the list of column names to DROP;
// the expert ticks "Garder" per row. Each row shows the agent's advice + reason.
// `ctrl.cols` (optional) configures which fields are displayed, so the same widget
// serves both the cleaning column table and the integration feature table.
export default function ColumnTable({ ctrl, value, onChange }) {
  const rows = ctrl.columns || [];
  const cols = ctrl.cols || DEFAULT_COLS;
  const dropped = new Set(value || []);

  const toggle = (col, keep) => {
    const next = new Set(dropped);
    if (keep) next.delete(col); else next.add(col);
    onChange(ctrl.name, Array.from(next));
  };
  const applyAdvice = () =>
    onChange(ctrl.name, rows.filter((r) => r.recommended === 'retirer').map((r) => r.column));
  const keepAll = () => onChange(ctrl.name, []);

  const kept = rows.filter((r) => !dropped.has(r.column)).length;

  const cell = (row, key) => {
    if (key === 'recommended') {
      return (
        <span className={row.recommended === 'retirer' ? 'coltable-rec-drop' : 'coltable-rec-keep'}>
          {row.recommended}
        </span>
      );
    }
    const v = row[key];
    return v === null || v === undefined ? '—' : String(v);
  };

  return (
    <div className="coltable">
      <div className="coltable-head">
        <span className="cfg-label">{ctrl.label}</span>
        <span className="coltable-count">{kept} gardées / {rows.length}</span>
        <button type="button" className="coltable-btn" onClick={applyAdvice}>Appliquer l'avis</button>
        <button type="button" className="coltable-btn" onClick={keepAll}>Tout garder</button>
      </div>
      {ctrl.help ? <p className="cfg-help">{ctrl.help}</p> : null}
      <div className="coltable-scroll">
        <table className="coltable-table">
          <thead>
            <tr><th>Garder</th>{cols.map((c) => <th key={c.key}>{c.label}</th>)}</tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const keep = !dropped.has(row.column);
              const isTarget = row.type === 'Cible';
              return (
                <tr key={row.column} className={keep ? '' : 'coltable-droprow'}>
                  <td>
                    <input type="checkbox" checked={keep} disabled={isTarget}
                      onChange={(e) => toggle(row.column, e.target.checked)} />
                  </td>
                  {cols.map((c) => {
                    let cls = '';
                    if (c.key === 'column') cls = 'coltable-col';
                    else if (c.key === 'type') cls = 'coltable-type';
                    else if (c.key === 'reason') cls = 'coltable-reason';
                    else if (c.key === 'missing_pct' && row.missing_pct > 50) cls = 'coltable-miss';
                    return <td key={c.key} className={cls}>{cell(row, c.key)}</td>;
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
