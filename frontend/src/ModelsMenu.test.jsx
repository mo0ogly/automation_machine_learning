import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import ModelsMenu from './components/ModelsMenu';

afterEach(() => vi.restoreAllMocks());

// Minimal /api/sessions payload: three runs of the same dataset + algo (they
// must collapse into one row) and one distinct model.
const SESSIONS = {
  sessions: [
    { id: 'old1', filename: 'transactions.csv', updated_at: '2026-07-04T09:00:00',
      summary: { model: 'IsolationForest', problem_type: 'anomaly', n_rows: 500, n_cols: 12 } },
    { id: 'abc123', filename: 'transactions.csv', updated_at: '2026-07-05T10:00:00',
      summary: { model: 'IsolationForest', problem_type: 'anomaly', n_rows: 500, n_cols: 12 } },
    { id: 'old2', filename: 'transactions.csv', updated_at: '2026-07-03T08:00:00',
      summary: { model: 'IsolationForest', problem_type: 'anomaly', n_rows: 500, n_cols: 12 } },
    { id: 'lof1', filename: 'transactions.csv', updated_at: '2026-07-02T08:00:00',
      summary: { model: 'LocalOutlierFactor', problem_type: 'anomaly', n_rows: 500, n_cols: 12 } },
  ],
};

// Saved Deep RL agents surfaced by /api/rl/deep/registry.
const RL_AGENTS = {
  agents: [
    { id: 'rl1', name: "SOC — Triage d'alertes (simple, DQN)", env_id: 'AlertTriage-v0',
      algo: 'DQN', created: '2026-07-05T18:25:00',
      metrics: { "Récompense d'évaluation (moy.)": 38.2 } },
  ],
};

describe('ModelsMenu (smoke)', () => {
  it('renders one row per model with the download/open actions column', async () => {
    vi.stubGlobal('fetch', vi.fn((url) => {
      const body = String(url).includes('/api/rl/deep/registry') ? RL_AGENTS : SESSIONS;
      return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
    }));
    render(<ModelsMenu apiBase="http://localhost:8000" onClose={() => {}} />);
    // Identical runs collapse: 4 sessions -> 2 rows, dataset shown twice only.
    expect((await screen.findAllByText('transactions.csv')).length).toBe(2);
    expect(screen.getByText('IsolationForest')).toBeTruthy();
    expect(screen.getByText('LocalOutlierFactor')).toBeTruthy();
    expect(screen.getByText('×3')).toBeTruthy();  // grouped-runs counter
    // The explanation column: header + domain phrasing for a cyber dataset
    // (transactions.csv -> fraud detection), once per collapsed row.
    expect(screen.getByText('Ce que fait le modèle')).toBeTruthy();
    expect(screen.getAllByText('Repère les transactions frauduleuses ou anormales').length).toBe(2);
    // The actions column: labelled header + actions pointing at the LATEST run.
    expect(screen.getAllByText('Télécharger / ouvrir').length).toBeGreaterThan(0);
    const bundles = screen.getAllByText('Bundle .zip');
    expect(bundles.length).toBe(3);  // 2 supervised rows + 1 RL agent row
    expect(bundles[0].getAttribute('href')).toContain('/api/session/abc123/export-bundle');
    const pkls = screen.getAllByText('.pkl');
    expect(pkls[0].getAttribute('href')).toContain('/api/session/abc123/download-model');
    expect(screen.getAllByText('Ouvrir').length).toBe(2);
    // Deep RL agents section: saved SOC/NOC agents listed with their downloads.
    expect(screen.getByText('Agents Deep RL (SOC / NOC)')).toBeTruthy();
    expect(await screen.findByText("SOC — Triage d'alertes (simple, DQN)")).toBeTruthy();
    expect(screen.getByText("Triage d'alertes SOC")).toBeTruthy();  // env label
    const zip = screen.getByText('.zip');
    expect(zip.getAttribute('href')).toContain('/api/rl/deep/registry/rl1/download');
  });
});
