import React, { useState, useEffect, useCallback } from 'react';
import Editor from '@monaco-editor/react';

// "Prompts IA" panel: inspect and edit the agent's prompts (system instructions
// + per-stage few-shot examples) in a Monaco console. Edits are persisted as
// overrides server-side and picked up on the next agent call. Each prompt shows
// its UI localisation; "Localiser" points the analyst to where it is used.
//
// Text prompts edit as markdown; few-shot prompts edit as JSON (validated on save).

function toDraft(entry) {
  if (!entry) return '';
  return entry.kind === 'json'
    ? JSON.stringify(entry.value, null, 2)
    : String(entry.value != null ? entry.value : '');
}

export default function PromptsPanel({ apiBase, onClose, onLocate }) {
  const [prompts, setPrompts] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [draft, setDraft] = useState('');
  const [err, setErr] = useState(null);
  const [notice, setNotice] = useState(null);
  const [saving, setSaving] = useState(false);

  const selected = prompts.find((p) => p.id === selectedId) || null;
  const dirty = selected ? draft !== toDraft(selected) : false;

  const load = useCallback(async () => {
    try {
      const d = await fetch(apiBase + '/api/prompts').then((r) => r.json());
      const list = d.prompts || [];
      setPrompts(list);
      setSelectedId((cur) => cur || (list[0] && list[0].id) || null);
    } catch (e) { setErr('Catalogue de prompts injoignable.'); }
  }, [apiBase]);

  useEffect(() => { load(); }, [load]);

  // Reset the editor when the selected prompt changes (or its stored value does).
  useEffect(() => { setDraft(toDraft(selected)); setErr(null); setNotice(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, selected && selected.value]);

  const select = (id) => { setSelectedId(id); };

  const save = async () => {
    if (!selected) return;
    let value = draft;
    if (selected.kind === 'json') {
      try { value = JSON.parse(draft); }
      catch (e) { setErr('JSON invalide : ' + e.message); return; }
    } else if (!draft.trim()) {
      setErr('Le prompt ne peut pas être vide.'); return;
    }
    setSaving(true); setErr(null); setNotice(null);
    try {
      const res = await fetch(apiBase + '/api/prompts/' + selected.id,
        { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ value }) });
      const data = await res.json();
      if (!res.ok) { setErr(data.detail || 'Enregistrement refusé.'); }
      else {
        setPrompts((prev) => prev.map((p) => (p.id === data.id ? data : p)));
        setNotice('Enregistré — appliqué au prochain appel de l\'agent.');
      }
    } catch (e) { setErr('Enregistrement échoué.'); }
    setSaving(false);
  };

  const reset = async () => {
    if (!selected || !selected.overridden) return;
    if (!window.confirm('Réinitialiser « ' + selected.label + ' » au prompt par défaut ?')) return;
    setSaving(true); setErr(null); setNotice(null);
    try {
      const res = await fetch(apiBase + '/api/prompts/' + selected.id, { method: 'DELETE' });
      const data = await res.json();
      if (!res.ok) { setErr(data.detail || 'Réinitialisation refusée.'); }
      else {
        setPrompts((prev) => prev.map((p) => (p.id === data.id ? data : p)));
        setDraft(toDraft(data));
        setNotice('Réinitialisé au prompt par défaut.');
      }
    } catch (e) { setErr('Réinitialisation échouée.'); }
    setSaving(false);
  };

  const systemPrompts = prompts.filter((p) => p.kind === 'text');
  const fewshots = prompts.filter((p) => p.kind === 'json');
  const loc = selected ? selected.localisation : null;

  return (
    <div className="ai-modal-overlay" onClick={onClose}>
      <div className="ai-modal glass-panel prompts-modal" onClick={(e) => e.stopPropagation()}>
        <div className="ai-modal-head">
          <h2>Prompts IA</h2>
          <button type="button" className="ai-modal-close" onClick={onClose} aria-label="Fermer">×</button>
        </div>
        <p className="ai-modal-note">
          Le texte exact envoyé à l'IA. Édite-le ici : l'override est persisté côté serveur et pris en
          compte au prochain appel de l'agent (sans redémarrage). « Localiser » montre où ce prompt agit
          dans l'interface.
        </p>
        {err ? <div className="banner banner-block">{err}</div> : null}

        <div className="prompts-body">
          <aside className="prompts-list">
            <div className="prompts-group">Instructions système</div>
            {systemPrompts.map((p) => (
              <button key={p.id} type="button"
                className={'prompts-item' + (p.id === selectedId ? ' active' : '')}
                onClick={() => select(p.id)}>
                <span>{p.label}</span>
                {p.overridden ? <span className="prompts-badge">modifié</span> : null}
              </button>
            ))}
            <div className="prompts-group">Exemples few-shot</div>
            {fewshots.map((p) => (
              <button key={p.id} type="button"
                className={'prompts-item' + (p.id === selectedId ? ' active' : '')}
                onClick={() => select(p.id)}>
                <span>{p.label}</span>
                {p.overridden ? <span className="prompts-badge">modifié</span> : null}
              </button>
            ))}
          </aside>

          <section className="prompts-editor">
            {selected ? (
              <>
                <div className="prompts-meta">
                  <div>
                    <strong>{selected.label}</strong>
                    <p className="prompts-desc">{selected.description}</p>
                  </div>
                  {loc ? (
                    <button type="button" className="ai-btn" title={loc.trigger}
                      onClick={() => onLocate(loc)}>Localiser dans l'UI</button>
                  ) : null}
                </div>
                {loc ? (
                  <div className="prompts-loc">
                    <span className="prompts-loc-tag">{loc.view}</span>
                    <span>{loc.trigger}</span>
                    <code>{loc.endpoint}</code>
                  </div>
                ) : null}

                <div className="prompts-monaco">
                  <Editor
                    height="100%"
                    theme="vs-dark"
                    language={selected.kind === 'json' ? 'json' : 'markdown'}
                    value={draft}
                    onChange={(v) => setDraft(v != null ? v : '')}
                    options={{ minimap: { enabled: false }, fontSize: 13, wordWrap: 'on',
                      scrollBeyondLastLine: false, automaticLayout: true }}
                  />
                </div>

                <div className="prompts-foot">
                  <div className="prompts-status">
                    {notice ? <span className="ai-test-ok">{notice}</span>
                      : dirty ? <span className="prompts-dirty">modifications non enregistrées</span>
                      : selected.overridden ? <span className="prompts-dirty">override actif</span>
                      : <span className="ai-test-pending">prompt par défaut</span>}
                  </div>
                  <div className="prompts-actions">
                    <button type="button" className="ai-btn" disabled={!selected.overridden || saving}
                      onClick={reset}>Réinitialiser</button>
                    <button type="button" className="ai-btn ai-btn-primary" disabled={!dirty || saving}
                      onClick={save}>{saving ? '…' : 'Enregistrer'}</button>
                  </div>
                </div>
              </>
            ) : <p className="ai-empty">Aucun prompt.</p>}
          </section>
        </div>
      </div>
    </div>
  );
}
