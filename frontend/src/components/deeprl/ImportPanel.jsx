import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { importAgent, importEnv } from './api';

// Compatible = action space matches AND (for a mask-only algo) the env is maskable.
function isCompatible(algo, env) {
  if (!algo || !env) return false;
  if (!algo.action_kinds.includes(env.action_kind)) return false;
  return algo.requires_mask ? Boolean(env.maskable) : true;
}

// Import panel: bring an externally-trained SB3 .zip into "My agents", or turn a
// CSV of real alerts into a custom SOC-triage environment. Manages its own form
// state; notifies the parent so it can refresh the catalogue/registry.
export default function ImportPanel({ envs, algos, onAgentImported, onEnvImported }) {
  const { t } = useTranslation('reinforcement');
  const envList = envs || [];
  const algoList = algos || [];

  const [aName, setAName] = useState('');
  const [aEnv, setAEnv] = useState('');
  const [aAlgo, setAAlgo] = useState('');
  const [aFile, setAFile] = useState(null);
  const [eName, setEName] = useState('');
  const [eFile, setEFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [note, setNote] = useState(null);

  const selEnv = envList.find((e) => e.id === aEnv) || null;
  const compatAlgos = algoList.filter((a) => isCompatible(a, selEnv));

  const submitAgent = async (ev) => {
    ev.preventDefault();
    if (!aFile || !aEnv || !aAlgo) { setErr(t('deep.import.incomplete')); return; }
    setBusy(true); setErr(null); setNote(null);
    try {
      const entry = await importAgent(aFile, aName, aEnv, aAlgo);
      setNote(t('deep.import.agentOk', { name: entry.name }));
      setAName(''); setAFile(null);
      if (onAgentImported) onAgentImported(entry);
    } catch (e) { setErr(e.message); }
    setBusy(false);
  };

  const submitEnv = async (ev) => {
    ev.preventDefault();
    if (!eFile) { setErr(t('deep.import.incomplete')); return; }
    setBusy(true); setErr(null); setNote(null);
    try {
      const meta = await importEnv(eFile, eName);
      setNote(t('deep.import.envOk', { name: meta.label || meta.id }));
      setEName(''); setEFile(null);
      if (onEnvImported) onEnvImported(meta);
    } catch (e) { setErr(e.message); }
    setBusy(false);
  };

  return (
    <section className="rl-panel glass-panel" aria-label={t('deep.import.title')}>
      <header className="rl-step-head">
        <span className="rl-step-no">↥</span>
        <div><h3>{t('deep.import.title')}</h3><p>{t('deep.import.hint')}</p></div>
      </header>

      <div className="rl-import-grid">
        <form className="rl-import-form" onSubmit={submitAgent}>
          <h4>{t('deep.import.agentTitle')}</h4>
          <p className="rl-field-hint">{t('deep.import.agentHint')}</p>
          <label>{t('deep.import.name')}
            <input type="text" value={aName} onChange={(e) => setAName(e.target.value)}
              placeholder={t('deep.import.namePlaceholder')} />
          </label>
          <label>{t('deep.import.env')}
            <select value={aEnv} onChange={(e) => { setAEnv(e.target.value); setAAlgo(''); }}>
              <option value="">—</option>
              {envList.map((e) => <option key={e.id} value={e.id}>{e.id}</option>)}
            </select>
          </label>
          <label>{t('deep.import.algo')}
            <select value={aAlgo} onChange={(e) => setAAlgo(e.target.value)} disabled={!selEnv}>
              <option value="">—</option>
              {compatAlgos.map((a) => <option key={a.id} value={a.id}>{a.id}</option>)}
            </select>
          </label>
          <label className="rl-file">{t('deep.import.file')}
            <input type="file" accept=".zip" onChange={(e) => setAFile(e.target.files[0] || null)} />
          </label>
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {t('deep.import.submitAgent')}</button>
        </form>

        <form className="rl-import-form" onSubmit={submitEnv}>
          <h4>{t('deep.import.envTitle')}</h4>
          <p className="rl-field-hint">{t('deep.import.envHint')}</p>
          <label>{t('deep.import.name')}
            <input type="text" value={eName} onChange={(e) => setEName(e.target.value)}
              placeholder={t('deep.import.envNamePlaceholder')} />
          </label>
          <label className="rl-file">{t('deep.import.csv')}
            <input type="file" accept=".csv" onChange={(e) => setEFile(e.target.files[0] || null)} />
          </label>
          <code className="rl-csv-cols">threat_score, asset_criticality, source_reputation, label</code>
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {t('deep.import.submitEnv')}</button>
        </form>
      </div>

      {err ? <div className="banner banner-block">{err}</div> : null}
      {note ? <div className="rl-verdict rl-verdict-success" role="status"><span>{note}</span></div> : null}
    </section>
  );
}
