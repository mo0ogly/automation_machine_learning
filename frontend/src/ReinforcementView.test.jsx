import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import ReinforcementView from './components/ReinforcementView';

afterEach(() => vi.restoreAllMocks());

const trainPayload = (over = {}) => ({
  metrics: {
    'Récompense initiale (moy.)': -20, 'Récompense finale (moy.)': 4,
    "Gain d'apprentissage": 24, 'Taux de réussite final': '95%',
    'Pas moyens (fin)': 8.2, 'Chemin optimal (Manhattan)': 8,
  },
  plots: [{ img: 'data:image/png;base64,xxx', caption: 'Courbe de récompense' }],
  config: { size: 5, episodes: 300, alpha: 0.1, gamma: 0.95, epsilon: 1, n_traps: 0, n_goals: 1 },
  env: { size: 5, start: [0, 0], goals: [[4, 4]], obstacles: [], traps: [] },
  ...over,
});

describe('ReinforcementView (smoke)', () => {
  it('renders the guided steps, grid and presets', () => {
    render(<ReinforcementView />);
    expect(screen.getByText('Apprentissage par renforcement')).toBeTruthy();
    expect(screen.getByText('Concevoir l’environnement')).toBeTruthy();
    expect(screen.getByText('Régler l’algorithme')).toBeTruthy();
    expect(screen.getByText('Analyser l’apprentissage')).toBeTruthy();
    // 5×5 default grid = 25 cells in 5 ARIA rows
    expect(screen.getAllByRole('gridcell').length).toBe(25);
    expect(screen.getAllByRole('row').length).toBe(5);
    expect(screen.getByText('Labyrinthe')).toBeTruthy();
  });

  it('paints an obstacle then erases it', () => {
    render(<ReinforcementView />);
    const cell = screen.getByRole('gridcell', { name: /Case 2,3/ });
    fireEvent.click(cell); // default tool = obstacle
    expect(cell.className).toContain('rl-cell-obstacle');
    fireEvent.click(screen.getByRole('radio', { name: /Gomme/ }));
    fireEvent.click(cell);
    expect(cell.className).toContain('rl-cell-free');
  });

  it('applies a preset (Labyrinthe -> 7×7 grid with obstacles)', () => {
    render(<ReinforcementView />);
    fireEvent.click(screen.getByText('Labyrinthe'));
    expect(screen.getAllByRole('gridcell').length).toBe(49);
    expect(screen.getAllByTitle(/Obstacle/).length).toBeGreaterThan(5);
  });

  it('moves the roving focus with arrow keys (single tab stop)', () => {
    render(<ReinforcementView />);
    const grid = screen.getByRole('grid');
    const first = screen.getByRole('gridcell', { name: /Case 1,1/ });
    const right = screen.getByRole('gridcell', { name: /Case 1,2/ });
    expect(first.tabIndex).toBe(0);
    expect(right.tabIndex).toBe(-1);
    fireEvent.keyDown(grid, { key: 'ArrowRight' });
    expect(screen.getByRole('gridcell', { name: /Case 1,2/ }).tabIndex).toBe(0);
    expect(screen.getByRole('gridcell', { name: /Case 1,1/ }).tabIndex).toBe(-1);
  });

  it('trains via the API and shows verdict + metrics + plots', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => trainPayload() })));
    render(<ReinforcementView />);
    fireEvent.click(screen.getByText("Entraîner l'agent"));
    await waitFor(() => expect(screen.getByText('L’agent a appris')).toBeTruthy());
    expect(screen.getByText('Taux de réussite final')).toBeTruthy();
    expect(screen.getByAltText('Courbe de récompense')).toBeTruthy();
    const [, opts] = fetch.mock.calls[0];
    const body = JSON.parse(opts.body);
    expect(body).toHaveProperty('obstacles');
    expect(body).toHaveProperty('traps');
  });

  it('flags the results as stale when the config changes after training', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => trainPayload() })));
    render(<ReinforcementView />);
    fireEvent.click(screen.getByText("Entraîner l'agent"));
    await waitFor(() => expect(screen.getByText('L’agent a appris')).toBeTruthy());
    expect(screen.queryByText(/Configuration modifiée depuis cet entraînement/)).toBeNull();
    fireEvent.click(screen.getByText('Champ de mines'));
    expect(screen.getByText(/Configuration modifiée depuis cet entraînement/)).toBeTruthy();
  });

  it('does not resurrect an erased explicit trap as an auto marker', async () => {
    render(<ReinforcementView />);
    // Place an explicit trap at (2,2) -> Case 3,3.
    fireEvent.click(screen.getByRole('radio', { name: /Piège/ }));
    const cell = screen.getByRole('gridcell', { name: /Case 3,3/ });
    fireEvent.click(cell);
    expect(cell.className).toContain('rl-cell-trap');
    // Train: backend echoes the explicit trap in env.traps.
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => trainPayload({
        env: { size: 5, start: [0, 0], goals: [[4, 4]], obstacles: [], traps: [[2, 2]] },
      }),
    })));
    fireEvent.click(screen.getByText("Entraîner l'agent"));
    await waitFor(() => expect(screen.getByText('L’agent a appris')).toBeTruthy());
    // Erase it: the cell must become free, not a ghost "auto" trap.
    fireEvent.click(screen.getByRole('radio', { name: /Gomme/ }));
    fireEvent.click(cell);
    expect(screen.getByRole('gridcell', { name: /Case 3,3/ }).className).toContain('rl-cell-free');
  });
});
