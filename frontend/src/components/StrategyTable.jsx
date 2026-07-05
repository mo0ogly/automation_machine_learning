import React from 'react';
import { useTranslation } from 'react-i18next';
import './strategy-table.css';

// Per-column cleaning-strategy table: the data-quality diagnostic made actionable.
// Each row shows the column's health metrics plus two dropdowns (imputation,
// outlier handling) that override the stage's global settings for that column.
// Value shape: {impute: {col: mode}, outliers: {col: method}} — empty = global.
export default function StrategyTable({ ctrl, value, onChange }) {
  const { t } = useTranslation('config');
  const rows = ctrl.columns || [];
  const val = value && typeof value === 'object' ? value : (ctrl.default || {});
  const impute = val.impute || {};
  const outliers = val.outliers || {};
  const nOverrides = Object.keys(impute).length + Object.keys(outliers).length;

  const set = (kind, col, v) => {
    const next = { impute: { ...impute }, outliers: { ...outliers } };
    if (v) next[kind][col] = v; else delete next[kind][col];
    onChange(ctrl.name, next);
  };
  const applyRecos = () => {
    const next = { impute: {}, outliers: {} };
    rows.forEach((r) => {
      if (r.rec_impute) next.impute[r.colonne] = r.rec_impute;
      if (r.rec_outliers) next.outliers[r.colonne] = r.rec_outliers;
    });
    onChange(ctrl.name, next);
  };
  const clearAll = () => onChange(ctrl.name, { impute: {}, outliers: {} });

  const imputeOptions = (row) =>
    (row.type === 'num' ? ctrl.impute_options_num : ctrl.impute_options_cat) || [];

  return (
    <div className="coltable">
      <div className="coltable-head">
        <span className="cfg-label">{ctrl.label}</span>
        <span className="coltable-count">{t('strategyCount', { count: nOverrides })}</span>
        <button type="button" className="coltable-btn" onClick={applyRecos}>{t('strategyRecoBtn')}</button>
        <button type="button" className="coltable-btn" onClick={clearAll}>{t('strategyGlobalBtn')}</button>
      </div>
      {ctrl.help ? <p className="cfg-help">{ctrl.help}</p> : null}
      <div className="coltable-scroll">
        <table className="coltable-table">
          <thead>
            <tr>
              <th>{t('colColumn')}</th><th>{t('colType')}</th><th>{t('colMissing')}</th>
              <th>{t('colOutliers')}</th><th>{t('colAlerts')}</th>
              <th>{t('colImpute')}</th><th>{t('colOutlierAction')}</th><th>{t('colReco')}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const isTarget = row.type === 'cible';
              return (
                <tr key={row.colonne}>
                  <td className="coltable-col">{row.colonne}</td>
                  <td className="coltable-type">{row.type}</td>
                  <td className={row['manquant_%'] > 50 ? 'coltable-miss' : ''}>{row['manquant_%']}</td>
                  <td>{row.aberrants}</td>
                  <td className="coltable-reason">{row.alertes}</td>
                  <td>
                    {isTarget ? '—' : (
                      <select className="strategy-select" value={impute[row.colonne] || ''}
                        onChange={(e) => set('impute', row.colonne, e.target.value)}>
                        {imputeOptions(row).map((o) => (
                          <option key={o.value} value={o.value}>{o.label}</option>
                        ))}
                      </select>
                    )}
                  </td>
                  <td>
                    {isTarget || row.type !== 'num' ? '—' : (
                      <select className="strategy-select" value={outliers[row.colonne] || ''}
                        onChange={(e) => set('outliers', row.colonne, e.target.value)}>
                        {(ctrl.outlier_options || []).map((o) => (
                          <option key={o.value} value={o.value}>{o.label}</option>
                        ))}
                      </select>
                    )}
                  </td>
                  <td className="strategy-reco" title={row.raison}>
                    {[row.rec_impute, row.rec_outliers].filter(Boolean).join(' + ') || '—'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
