import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import ModelsMenu from './components/ModelsMenu';

afterEach(() => vi.restoreAllMocks());

// Minimal /api/sessions payload: one session carrying a trained model.
const SESSIONS = {
  sessions: [
    { id: 'abc123', filename: 'transactions.csv', updated_at: '2026-07-05T10:00:00',
      summary: { model: 'IsolationForest', problem_type: 'anomaly', n_rows: 500, n_cols: 12 } },
  ],
};

describe('ModelsMenu (smoke)', () => {
  it('renders one row per model with the download/open actions column', async () => {
    vi.stubGlobal('fetch', vi.fn(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve(SESSIONS) })));
    render(<ModelsMenu apiBase="http://localhost:8000" onClose={() => {}} />);
    // Row content from the catalogue
    expect(await screen.findByText('transactions.csv')).toBeTruthy();
    expect(screen.getByText('IsolationForest')).toBeTruthy();
    // The actions column: labelled header + the three actions in the row
    expect(screen.getByText('Télécharger / ouvrir')).toBeTruthy();
    const bundle = screen.getByText('Bundle .zip');
    expect(bundle.getAttribute('href')).toContain('/api/session/abc123/export-bundle');
    const pkl = screen.getByText('.pkl');
    expect(pkl.getAttribute('href')).toContain('/api/session/abc123/download-model');
    expect(screen.getByText('Ouvrir')).toBeTruthy();
  });
});
