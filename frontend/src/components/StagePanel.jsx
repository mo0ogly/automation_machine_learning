import React, { useState, useEffect, useRef } from 'react';
import { useTranslation, Trans } from 'react-i18next';
import DiagnosticsView from './DiagnosticsView';
import ConfigControls from './ConfigControls';
import AgentRecommendation from './AgentRecommendation';
import ModelLeaderboard from './ModelLeaderboard';
import OperatingPoint from './OperatingPoint';
import MonitoringPanel from './MonitoringPanel';
import PlotModal from './PlotModal';
import AssistButton from './AssistButton';
import AssistAnswer from './AssistAnswer';

// Sparkle icon — signals "ask the AI for help".
function AIIcon() {
  return (
    <svg className="ai-icon" width="15" height="15" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M12 2l1.7 5.1L19 9l-5.3 1.9L12 16l-1.7-5.1L5 9l5.3-1.9L12 2z" />
      <path d="M18.5 13l.9 2.5 2.6.9-2.6.9-.9 2.5-.9-2.5-2.6-.9 2.6-.9.9-2.5z" opacity="0.65" />
    </svg>
  );
}

const TABS = [
  { id: 'observe', tKey: 'tabs.observe' },
  { id: 'graphs', tKey: 'tabs.graphs' },
  { id: 'agent', tKey: 'tabs.agent' },
  { id: 'config', tKey: 'tabs.config' },
  { id: 'result', tKey: 'tabs.result' },
];

// AssistAnswer is imported from ./AssistAnswer (shared with the badge helpers).

// Figure image. The freeze on plot-heavy views (many base64 PNGs decoded at once)
// is avoided natively: `.plot-fig` carries `content-visibility: auto`, so the browser
// skips rasterising off-screen figures and renders them as they approach the viewport.
// `decoding="async"` keeps decoding off the main thread. The <img> is always in the
// DOM (no IntersectionObserver gate), so a figure never stays blank — even in a
// background/hidden tab or a bfcache restore where IO callbacks are suspended.
// NB: no `loading="lazy"` — these are inline base64 data-URIs (no network request to
// defer), and lazy-loading inside a `content-visibility: auto` subtree leaves the IO
// callback suspended, so figures rendered blank ~1 time out of 2 until a reflow.
function PlotImg({ src, alt, className }) {
  return <img src={src} alt={alt} className={className} decoding="async" />;
}

function Plots({ plots, onZoom, onAssist, assistBusy, assistAnswers, onApplyAssist }) {
  const { t } = useTranslation('stage');
  if (!plots || !plots.length) return null;
  const srcOf = (p) => (typeof p === 'string' ? p : p.img);
  const capOf = (p) => (typeof p === 'string' ? '' : (p.caption || ''));
  return (
    <div className="plots-grid">
      {plots.map((p, i) => {
        const src = srcOf(p);
        const caption = capOf(p);
        const topic = 'graphe: ' + caption;
        return (
          <figure key={i} className="plot-fig">
            <button type="button" className="plot-thumb" title={t('plots.enlarge')}
              onClick={() => onZoom && onZoom({ src, caption })}>
              <PlotImg src={src} alt={caption || t('plots.figureAlt', { n: i })} className="plot-img" />
              <span className="plot-zoom-hint" aria-hidden="true">⤢</span>
            </button>
            {caption ? (
              <figcaption className="plot-cap">
                <span className="plot-cap-txt" title={caption}>{caption}</span>
                {onAssist ? (
                  <AssistButton topic={topic} label={caption} text={t('ai')}
                    onAssist={onAssist} busy={assistBusy} />
                ) : null}
              </figcaption>
            ) : null}
            {caption ? <AssistAnswer topic={topic} answers={assistAnswers} onApply={onApplyAssist} /> : null}
          </figure>
        );
      })}
    </div>
  );
}

function ReportCards({ report }) {
  if (!report) return null;
  return (
    <div className="report-cards">
      {Object.entries(report).map(([k, v]) => (
        <div key={k} className="report-card">
          <div className="report-k">{k}</div>
          <div className="report-v">{String(v)}</div>
        </div>
      ))}
    </div>
  );
}

// Pedagogical callout: the "logique de construction du dataset" per stage,
// colour-coded by learning track (supervised vs unsupervised).
function Explanation({ explanation, supervised }) {
  useTranslation('stage');
  if (!explanation || !explanation.why) return null;
  return (
    <div className={supervised ? 'explain explain-sup' : 'explain explain-unsup'}>
      <span className="explain-track">{explanation.track_label}</span>
      <p><Trans i18nKey="stage:explanation.why" components={{ strong: <strong /> }} values={{ why: explanation.why }} /></p>
      <p><Trans i18nKey="stage:explanation.datasetLogic" components={{ strong: <strong /> }} values={{ logic: explanation.dataset_logic }} /></p>
      <p className="explain-note">{explanation.supervision}</p>
    </div>
  );
}

// AI interpretation / conclusion of a stage's results (natural language).
function InterpretationView({ data }) {
  const { t } = useTranslation('stage');
  if (!data) return null;
  const isLLM = data.source === 'llm';
  return (
    <div className="interpret-card">
      <div className="reco-head">
        <span className={isLLM ? 'reco-badge reco-llm' : 'reco-badge reco-heur'}>{t('interpretation.badge')}</span>
        {data.model ? <span className="reco-model">{data.model}</span> : null}
        {data.confidence ? <span className="reco-conf">{t('interpretation.confidence', { pct: Math.round(data.confidence * 100) })}</span> : null}
      </div>
      {data.verdict ? <p className="interpret-verdict">{data.verdict}</p> : null}
      <ul className="reco-rationale">
        {(data.interpretation || []).map((x, i) => <li key={i}>{x}</li>)}
      </ul>
    </div>
  );
}

// Ordinal normalization applied during cleaning (qual_map).
function NormalizationView({ rows }) {
  const { t } = useTranslation('stage');
  if (!rows || !rows.length) return null;
  return (
    <div className="norm-ordinale">
      <h5>{t('normalization.title', { n: rows.length })}</h5>
      <table className="diag-table">
        <thead><tr><th>{t('normalization.column')}</th><th>{t('normalization.scale')}</th></tr></thead>
        <tbody>
          {rows.map((n) => (
            <tr key={n.colonne}><td>{n.colonne}</td><td className="norm-scale">{n.echelle}</td></tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Business reading of the clusters (unsupervised track) — real average values per
// cluster + majority categoricals + business label.
function ClusterSummary({ rows, onApplyLabels, busy }) {
  const { t } = useTranslation('stage');
  const [names, setNames] = useState({});
  if (!rows || !rows.length) return null;
  const numKeys = Object.keys(rows[0].moyennes || {});
  const catKeys = Object.keys(rows[0].majoritaires || {});
  const editable = typeof onApplyLabels === 'function';
  const nameOf = (r) => (names[r.cluster] !== undefined ? names[r.cluster] : r.label_metier);
  const dirty = rows.some((r) => names[r.cluster] !== undefined && names[r.cluster] !== r.label_metier);
  const apply = () => {
    const map = {};
    rows.forEach((r) => { const v = nameOf(r); if (v && v.trim()) map[String(r.cluster)] = v.trim(); });
    onApplyLabels(map);
  };
  return (
    <div className="cluster-summary">
      <h5>{t('cluster.title')}</h5>
      <div className="coltable-scroll">
        <table className="diag-table">
          <thead>
            <tr>
              <th>{t('cluster.cluster')}</th><th>{t('cluster.businessLabel')}</th><th>{t('cluster.size')}</th>
              {numKeys.map((k) => <th key={k}>{k}</th>)}
              {catKeys.map((k) => <th key={k}>{k}</th>)}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.cluster}>
                <td>{r.cluster}</td>
                <td>{editable ? (
                  <input className="cluster-name-input" value={nameOf(r)} aria-label={t('cluster.nameAriaLabel', { cluster: r.cluster })}
                    onChange={(e) => setNames((p) => ({ ...p, [r.cluster]: e.target.value }))} />
                ) : <strong>{r.label_metier}</strong>}</td>
                <td>{r.taille}</td>
                {numKeys.map((k) => <td key={k}>{r.moyennes ? r.moyennes[k] : '—'}</td>)}
                {catKeys.map((k) => <td key={k} className="norm-scale">{r.majoritaires ? r.majoritaires[k] : '—'}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {editable ? (
        <button type="button" className="btn btn-primary cluster-apply" onClick={apply} disabled={busy || !dirty}>
          {t('cluster.applyNames')}
        </button>
      ) : null}
    </div>
  );
}

// Per-class precision / recall / F1 (classification_report).
function ClassReport({ rows }) {
  const { t } = useTranslation('stage');
  if (!rows || !rows.length) return null;
  return (
    <div className="cluster-summary">
      <h5>{t('classReport.title')}</h5>
      <table className="diag-table">
        <thead><tr><th>{t('classReport.class')}</th><th>{t('classReport.precision')}</th><th>{t('classReport.recall')}</th><th>{t('classReport.f1')}</th><th>{t('classReport.support')}</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.classe}>
              <td><strong>{r.classe}</strong></td>
              <td>{r['précision']}</td><td>{r.rappel}</td><td>{r.f1}</td><td>{r.support}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Most abnormal rows (unsupervised anomaly detection) — raw values + anomaly score.
function AnomalySummary({ rows }) {
  const { t } = useTranslation('stage');
  if (!rows || !rows.length) return null;
  const cols = Object.keys(rows[0]).filter((k) => k !== 'score');
  return (
    <div className="cluster-summary">
      <h5>{t('anomaly.title')}</h5>
      <div className="coltable-scroll">
        <table className="diag-table">
          <thead>
            <tr>{cols.map((c) => <th key={c}>{c}</th>)}<th>score</th></tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                {cols.map((c) => <td key={c}>{String(r[c])}</td>)}
                <td className="norm-scale">{r.score}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// Overfitting control: train vs test gap + cross-validation.
function OverfitControl({ data }) {
  const { t } = useTranslation('stage');
  if (!data) return null;
  const verdict = data.verdict;
  const entries = Object.entries(data).filter(([k]) => k !== 'verdict');
  const bad = verdict && verdict.indexOf('surapprentissage') === 0;
  return (
    <div className="overfit-control">
      <h5>{t('overfit.title')}</h5>
      <table className="diag-table">
        <tbody>
          {entries.map(([k, v]) => (
            <tr key={k}><td>{k}</td><td className="overfit-val">{String(v)}</td></tr>
          ))}
        </tbody>
      </table>
      {verdict ? <p className={bad ? 'overfit-verdict overfit-bad' : 'overfit-verdict'}>{verdict}</p> : null}
    </div>
  );
}

// Deploy controls shown once the model has been evaluated.
function DeploySection({ apiBase, sessionId }) {
  const { t } = useTranslation('stage');
  const [features, setFeatures] = useState('{}');
  const [prediction, setPrediction] = useState(null);
  const [error, setError] = useState(null);

  const test = async () => {
    setError(null); setPrediction(null);
    try {
      const res = await fetch(apiBase + '/api/session/' + sessionId + '/predict', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: features,
      });
      const data = await res.json();
      if (!res.ok) { setError(data.detail || t('deploy.apiError')); return; }
      setPrediction(data.prediction);
    } catch (e) {
      setError(t('deploy.jsonError'));
    }
  };

  return (
    <div className="deploy">
      <h4>{t('deploy.title')}</h4>
      <a className="btn btn-secondary" href={apiBase + '/api/session/' + sessionId + '/download-model'}
         target="_blank" rel="noreferrer">{t('deploy.download')}</a>
      <p className="muted deploy-hint">{t('deploy.hint')}</p>
      <textarea className="deploy-input" rows="3" value={features} onChange={(e) => setFeatures(e.target.value)} />
      <button className="btn btn-primary" onClick={test}>{t('deploy.test')}</button>
      {prediction !== null ? <div className="deploy-result">{t('deploy.result')} <strong>{String(prediction)}</strong></div> : null}
      {error ? <div className="warn-text">{error}</div> : null}
    </div>
  );
}

export default function StagePanel(props) {
  const { t } = useTranslation('stage');
  const {
    stage, config, onConfigChange, reco, recoLoading, onAsk, onApply, onApplyKey,
    onRun, onNext, busy, apiBase, sessionId, isLast,
    interpretation, interpretLoading, onInterpret,
    onAssist, assistBusy, assistAnswers, onApplyAssist, onApplyClusterLabels,
  } = props;

  const [tab, setTab] = useState('observe');
  const [zoom, setZoom] = useState(null);
  const stageId = stage && stage.meta ? stage.meta.stage_id : null;
  const hasResult = !!(stage && stage.result);
  const prevResult = useRef(false);

  // Reset to Observation when the stage changes; jump to Result after a run.
  useEffect(() => { setTab('observe'); prevResult.current = false; }, [stageId]);
  useEffect(() => {
    if (hasResult && !prevResult.current) setTab('result');
    prevResult.current = hasResult;
  }, [hasResult]);

  if (!stage) return <div className="stage-panel"><p className="muted">{t('selectStage')}</p></div>;

  const meta = stage.meta;
  const ran = stage.status && stage.status.ran;
  const stale = stage.status && stage.status.stale;
  const blocked = !!stage.input_error;
  const diagPlots = stage.diagnose_plots || [];
  const resultPlots = (stage.result && stage.result.plots) || [];
  const plotCount = diagPlots.length + resultPlots.length;
  const highlight = {};
  if (reco && reco.suggested_config) Object.keys(reco.suggested_config).forEach((k) => { highlight[k] = true; });

  return (
    <div className="stage-panel">
      <div className="stage-head">
        <div>
          <h3 className="stage-title"><span className="stage-num">{meta.index}</span>{meta.title}</h3>
          <p className="stage-obj">{meta.objective}</p>
        </div>
      </div>

      <Explanation explanation={stage.explanation} supervised={stage.supervised} />

      {stale ? <div className="banner banner-stale">{t('banners.stale')}</div> : null}
      {blocked ? <div className="banner banner-block">{stage.input_error}</div> : null}

      {!blocked ? (
        <>
          <div className="tabs" role="tablist">
            {TABS.map((item) => {
              const disabled = item.id === 'result' && !hasResult;
              return (
                <button key={item.id} type="button" className={tab === item.id ? 'tab tab-on' : 'tab'}
                  disabled={disabled} onClick={() => setTab(item.id)}>
                  {item.id === 'agent' ? <AIIcon /> : null}{t(item.tKey)}
                  {item.id === 'result' && hasResult ? <span className="tab-dot" /> : null}
                  {item.id === 'graphs' && plotCount ? <span className="tab-count">{plotCount}</span> : null}
                </button>
              );
            })}
          </div>

          <div className="tab-content">
            {tab === 'observe' ? (
              <>
                <div className="substep-bar">
                  <span className="substep-hint">{t('hints.readDiagnostics')}</span>
                  <AssistButton topic="diagnostics" label={t('assist.explainDiagnostics')}
                    onAssist={onAssist} busy={assistBusy} />
                </div>
                <AssistAnswer topic="diagnostics" answers={assistAnswers} onApply={onApplyAssist} />
                <DiagnosticsView diagnostics={stage.diagnostics} />
                {stage.diagnostics && stage.diagnostics.leaderboard ? (
                  <ModelLeaderboard
                    rows={stage.diagnostics.leaderboard}
                    metric={stage.diagnostics.primary_metric}
                    cvFolds={stage.diagnostics.cv_folds}
                    leakageFree={stage.diagnostics.leakage_free}
                    selected={config.algorithm}
                    onChoose={(m) => { onConfigChange('algorithm', m); setTab('config'); }}
                    onAssist={onAssist} assistBusy={assistBusy} assistAnswers={assistAnswers}
                    onApplyAssist={onApplyAssist}
                  />
                ) : null}
              </>
            ) : null}

            {tab === 'graphs' ? (
              plotCount ? (
                <>
                  {diagPlots.length ? (
                    <>
                      <div className="substep-bar">
                        <span className="substep-hint">{t('hints.plotsDiagnostics')}</span>
                        <AssistButton topic="diagnostics" label={t('assist.explainPlots')}
                          onAssist={onAssist} busy={assistBusy} />
                      </div>
                      <Plots plots={diagPlots} onZoom={setZoom} onAssist={onAssist}
                        assistBusy={assistBusy} assistAnswers={assistAnswers} onApplyAssist={onApplyAssist} />
                    </>
                  ) : null}
                  {resultPlots.length ? (
                    <>
                      <div className="substep-bar">
                        <span className="substep-hint">{t('hints.plotsResult')}</span>
                      </div>
                      <Plots plots={resultPlots} onZoom={setZoom} onAssist={onAssist}
                        assistBusy={assistBusy} assistAnswers={assistAnswers} onApplyAssist={onApplyAssist} />
                    </>
                  ) : null}
                </>
              ) : <p className="muted">{t('hints.noPlots')}</p>
            ) : null}

            {tab === 'agent' ? (
              <>
                <button className="btn btn-ai" onClick={onAsk} disabled={recoLoading || busy}
                  data-prompt-loc="recommend">
                  <AIIcon />{recoLoading ? t('busy.analyzing') : t('actions.askRefine')}
                </button>
                <AgentRecommendation reco={reco} loading={recoLoading} onApply={onApply}
                  onApplyKey={onApplyKey} currentConfig={config} />
              </>
            ) : null}

            {tab === 'config' ? (
              <>
                <div className="substep-bar">
                  <span className="substep-hint">{t('hints.settings')}</span>
                  <AssistButton topic="decision" label={t('assist.whatToDecide')}
                    onAssist={onAssist} busy={assistBusy} />
                </div>
                <AssistAnswer topic="decision" answers={assistAnswers} onApply={onApplyAssist} />
                <ConfigControls schema={stage.schema} config={config} onChange={onConfigChange} highlight={highlight}
                  onAssist={onAssist} assistBusy={assistBusy} assistAnswers={assistAnswers} onApplyAssist={onApplyAssist} />
              </>
            ) : null}

            {tab === 'result' ? (
              hasResult ? (
                <>
                  <div className="substep-bar">
                    <span className="substep-hint">{t('hints.stageResult')}</span>
                    <AssistButton topic="result" label={t('assist.explainResult')}
                      onAssist={onAssist} busy={assistBusy} />
                  </div>
                  <AssistAnswer topic="result" answers={assistAnswers} onApply={onApplyAssist} />
                  {stage.result.diagnostics && stage.result.diagnostics.leakage_free ? (
                    <div className="lb-chips">
                      <span className="lb-chip lb-chip-clean"
                        title={t('leakageFree.title')}>
                        {t('leakageFree.label')}
                      </span>
                    </div>
                  ) : null}
                  <ReportCards report={stage.result.report} />
                  {stage.result.diagnostics && stage.result.diagnostics.normalisation_ordinale ? (
                    <NormalizationView rows={stage.result.diagnostics.normalisation_ordinale} />
                  ) : null}
                  {stage.result.diagnostics && stage.result.diagnostics.cluster_summary ? (
                    <ClusterSummary rows={stage.result.diagnostics.cluster_summary}
                      onApplyLabels={onApplyClusterLabels} busy={busy} />
                  ) : null}
                  {stage.result.diagnostics && stage.result.diagnostics.rapport_par_classe ? (
                    <ClassReport rows={stage.result.diagnostics.rapport_par_classe} />
                  ) : null}
                  {stage.result.diagnostics && stage.result.diagnostics.top_anomalies ? (
                    <AnomalySummary rows={stage.result.diagnostics.top_anomalies} />
                  ) : null}
                  {stage.result.diagnostics && stage.result.diagnostics.controle_surapprentissage ? (
                    <>
                      <div className="substep-bar">
                        <span className="substep-hint">{t('hints.overfitControl')}</span>
                        <AssistButton topic="controle_surapprentissage" label={t('assist.explainOverfit')}
                          onAssist={onAssist} busy={assistBusy} />
                      </div>
                      <AssistAnswer topic="controle_surapprentissage" answers={assistAnswers} onApply={onApplyAssist} />
                      <OverfitControl data={stage.result.diagnostics.controle_surapprentissage} />
                    </>
                  ) : null}
                  {meta.stage_id === 'evaluate' && stage.result.diagnostics
                    && stage.result.diagnostics.operational ? (
                    <>
                      <div className="substep-bar">
                        <span className="substep-hint">{t('hints.operationalView')}</span>
                        <AssistButton topic="operational" label={t('assist.explainOperatingPoint')}
                          onAssist={onAssist} busy={assistBusy} />
                      </div>
                      <AssistAnswer topic="operational" answers={assistAnswers} onApply={onApplyAssist} />
                      <OperatingPoint operational={stage.result.diagnostics.operational}
                        apiBase={apiBase} sessionId={sessionId} />
                    </>
                  ) : null}
                  {meta.stage_id === 'evaluate' ? (
                    <>
                      <div className="substep-bar">
                        <span className="substep-hint">{t('hints.monitoring')}</span>
                        <AssistButton topic="monitoring" label={t('assist.explainMonitoring')}
                          onAssist={onAssist} busy={assistBusy} />
                      </div>
                      <AssistAnswer topic="monitoring" answers={assistAnswers} onApply={onApplyAssist} />
                      <MonitoringPanel apiBase={apiBase} sessionId={sessionId} />
                    </>
                  ) : null}
                  {stage.result.warnings && stage.result.warnings.length ? (
                    <ul className="warn-list">{stage.result.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
                  ) : null}
                  {stage.result.log && stage.result.log.length ? (
                    <div className="log-mini">{stage.result.log.map((l, i) => <div key={i}>{'> ' + l}</div>)}</div>
                  ) : null}
                  {stage.result.plots && stage.result.plots.length ? (
                    <p className="muted plots-pointer">
                      {t('hints.plotsPointer', { n: stage.result.plots.length })}
                    </p>
                  ) : null}
                  <button className="btn btn-ai" onClick={onInterpret} disabled={interpretLoading}
                    data-prompt-loc="interpret">
                    <AIIcon />{interpretLoading ? t('busy.analyzing') : t('actions.askInterpretation')}
                  </button>
                  <InterpretationView data={interpretation} />
                  {meta.stage_id === 'evaluate' ? <DeploySection apiBase={apiBase} sessionId={sessionId} /> : null}
                </>
              ) : <p className="muted">{t('hints.runToSeeResult')}</p>
            ) : null}
          </div>

          <div className="stage-actions">
            <button className="btn btn-primary btn-run" onClick={onRun} disabled={busy}>
              {busy ? t('busy.running') : ran ? t('actions.replay') : t('actions.run')}
            </button>
            {ran && !isLast ? (
              <button className="btn btn-secondary" onClick={onNext} disabled={busy}>
                {t('actions.validateNext')}
              </button>
            ) : null}
          </div>
        </>
      ) : null}

      <PlotModal src={zoom && zoom.src} caption={zoom && zoom.caption} onClose={() => setZoom(null)} />
    </div>
  );
}
