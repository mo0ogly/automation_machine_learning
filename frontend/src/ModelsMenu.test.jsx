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

describe('ModelsMenu (smoke)', () => {
  it('renders one row per model with the download/open actions column', async () => {
    vi.stubGlobal('fetch', vi.fn(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve(SESSIONS) })));
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
    expect(screen.getByText('Télécharger / ouvrir')).toBeTruthy();
    const bundles = screen.getAllByText('Bundle .zip');
    expect(bundles.length).toBe(2);
    expect(bundles[0].getAttribute('href')).toContain('/api/session/abc123/export-bundle');
    const pkls = screen.getAllByText('.pkl');
    expect(pkls[0].getAttribute('href')).toContain('/api/session/abc123/download-model');
    expect(screen.getAllByText('Ouvrir').length).toBe(2);
  });
});
