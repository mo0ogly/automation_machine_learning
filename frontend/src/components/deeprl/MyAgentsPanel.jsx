import React from 'react';
import { useTranslation } from 'react-i18next';
import { agentDownloadUrl, agentExportUrl } from './api';

// "My agents": the analyst's saved/imported models. Each row can be re-evaluated,
// warm-started (continue training), downloaded, exported as a self-describing
// bundle, or deleted. Purely presentational — all state lives in DeepRLView.
export default function MyAgentsPanel({ agents, onEvaluate, onContinue, onDelete, busy }) {
  const { t } = useTranslation('reinforcement');
  const list = agents || [];

  return (
    <section className="rl-panel glass-panel" aria-label={t('deep.registry.title')}>
      <header className="rl-step-head">
        <span className="rl-step-no">★</span>
        <div><h3>{t('deep.registry.title')}</h3><p>{t('deep.registry.hint')}</p></div>
      </header>
      {list.length === 0 ? (
        <p className="rl-hint">{t('deep.registry.empty')}</p>
      ) : (
        <div className="rl-agent-grid">
          {list.map((a) => {
            const reward = a.metrics && a.metrics["Récompense d'évaluation (moy.)"];
            return (
              <article key={a.id} className="rl-agent-card glass-panel">
                <div className="rl-agent-head">
                  <strong className="rl-agent-name">{a.name}</strong>
                  {a.imported ? (
                    <span className="rl-tag rl-tag-imported">{t('deep.registry.importedBadge')}</span>
                  ) : null}
                </div>
                <span className="rl-agent-meta">{a.algo} · {a.env_id}</span>
                <span className="rl-agent-sub">
                  {reward != null ? t('deep.registry.reward', { value: reward }) + ' · ' : ''}
                  {a.created}
                </span>
                <div className="rl-agent-actions">
                  <button type="button" className="btn btn-primary btn-sm" disabled={busy}
                    onClick={() => onEvaluate(a)}>{t('deep.registry.evaluate')}</button>
                  <button type="button" className="btn btn-secondary btn-sm" disabled={busy}
                    onClick={() => onContinue(a)}>{t('deep.registry.continue')}</button>
                  <a className="btn btn-secondary btn-sm" download href={agentDownloadUrl(a.id)}>
                    {t('deep.registry.download')}</a>
                  <a className="btn btn-secondary btn-sm" download href={agentExportUrl(a.id)}>
                    {t('deep.registry.export')}</a>
                  <button type="button" className="btn btn-ghost btn-sm rl-agent-del" disabled={busy}
                    onClick={() => onDelete(a)}>{t('deep.registry.delete')}</button>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
