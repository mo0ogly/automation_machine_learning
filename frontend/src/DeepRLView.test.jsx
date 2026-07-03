import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import DeepRLView from './components/DeepRLView';
import ReinforcementView from './components/ReinforcementView';

afterEach(() => vi.restoreAllMocks());

// Algo radios share text (descriptions mention other algos), so match on the
// button's <strong> id rather than its full accessible name.
const algoBtn = (id) => screen.getAllByRole('radio')
  .find((b) => b.querySelector('strong') && b.querySelector('strong').textContent === id);

// Minimal but realistic /api/rl/deep/catalog payload (cyber env first, 3 algos, presets).
const CATALOG = {
  envs: [
    { id: 'AlertTriage-v0', group: 'cyber_defense', action_kind: 'discrete', obs_dim: 4, reward_threshold: 30.0 },
    { id: 'CartPole-v1', group: 'classic_control', action_kind: 'discrete', obs_dim: 4, reward_threshold: 475.0 },
    { id: 'Pendulum-v1', group: 'classic_control', action_kind: 'continuous', obs_dim: 3, reward_threshold: null },
  ],
  algos: [
    { id: 'PPO', family: 'on-policy', action_kinds: ['discrete', 'continuous'],
      fields: [{ name: 'total_timesteps', min: 2000, max: 200000, step: 1000, default: 30000 },
               { name: 'learning_rate', min: 0.0001, max: 0.01, step: 0.0001, default: 0.0003 }] },
    { id: 'DQN', family: 'off-policy', action_kinds: ['discrete'],
      fields: [{ name: 'total_timesteps', min: 2000, max: 200000, step: 1000, default: 30000 }] },
    { id: 'A2C', family: 'on-policy', action_kinds: ['discrete', 'continuous'], fields: [] },
  ],
  presets: [
    { id: 'soc_triage_dqn', group: 'cyber_defense', env_id: 'AlertTriage-v0', algo: 'DQN', config: {}, recommended: true },
    { id: 'cartpole_ppo', group: 'classic_control', env_id: 'CartPole-v1', algo: 'PPO', config: {}, recommended: false },
  ],
};

function mockCatalogFetch() {
  vi.stubGlobal('fetch', vi.fn((url) => {
    if (String(url).includes('/api/rl/deep/catalog')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(CATALOG) });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  }));
}

// A finished training job (metrics table + one captioned plot), so the results
// section and its AI helpers render.
const DONE_JOB = {
  status: 'done', progress: 1,
  result: {
    metrics: { Algorithme: 'PPO', Environnement: 'CartPole-v1', "Récompense d'évaluation (moy.)": 320.5 },
    plots: [{ img: 'data:image/png;base64,xxx', caption: "Deep RL — courbe d'apprentissage" }],
    solved: false, cancelled: false, env_id: 'CartPole-v1', algo: 'PPO', can_download: true,
  },
};

function mockTrainFetch() {
  vi.stubGlobal('fetch', vi.fn((url, opts) => {
    const u = String(url);
    if (u.includes('/api/rl/deep/catalog')) return Promise.resolve({ ok: true, json: () => Promise.resolve(CATALOG) });
    if (u.includes('/train')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ job_id: 'j1', status: 'running' }) });
    if (u.includes('/job/j1')) return Promise.resolve({ ok: true, json: () => Promise.resolve(DONE_JOB) });
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  }));
}

describe('DeepRLView (smoke)', () => {
  it('renders the workbench from the catalogue: envs, algos, presets', async () => {
    mockCatalogFetch();
    render(<DeepRLView />);
    // Title + steps
    expect(await screen.findByText('Deep Reinforcement Learning')).toBeTruthy();
    expect(screen.getByText('Modèles de base')).toBeTruthy();
    // Cyber-defense env + preset (i18n labels), proving the catalogue was consumed
    await waitFor(() => expect(screen.getByText("Triage d'alertes SOC")).toBeTruthy());
    expect(screen.getByText('Triage SOC (DQN)')).toBeTruthy();
    // The three algorithm buttons render
    expect(algoBtn('PPO')).toBeTruthy();
    expect(algoBtn('DQN')).toBeTruthy();
    expect(algoBtn('A2C')).toBeTruthy();
    // Train button present
    expect(screen.getByText("Entraîner l'agent")).toBeTruthy();
  });

  it('shows the results table with AI assistance (results + per-chart)', async () => {
    mockTrainFetch();
    render(<DeepRLView />);
    await screen.findByText('Deep Reinforcement Learning');
    fireEvent.click(screen.getByText("Entraîner l'agent"));
    // The metrics table renders...
    await waitFor(() => expect(screen.getByText('Algorithme')).toBeTruthy());
    expect(screen.getByText("Récompense d'évaluation (moy.)")).toBeTruthy();
    // ...with an AI button on the whole results table...
    expect(screen.getByTitle(/Expliquer les résultats/)).toBeTruthy();
    // ...and an AI button on the chart.
    expect(screen.getByText("Deep RL — courbe d'apprentissage")).toBeTruthy();
    expect(screen.getByTitle(/courbe d'apprentissage/)).toBeTruthy();
    // Download link present (trained model).
    expect(screen.getByText("Télécharger l'agent (.zip)")).toBeTruthy();
  });

  it('greys out DQN on a continuous environment', async () => {
    mockCatalogFetch();
    render(<DeepRLView />);
    await screen.findByText('Deep Reinforcement Learning');
    // Select the continuous env (Pendulum) -> DQN must become disabled.
    fireEvent.click(screen.getByText('Pendulum'));
    await waitFor(() => expect(algoBtn('DQN').disabled).toBe(true));
    expect(algoBtn('PPO').disabled).toBe(false);
  });
});

describe('ReinforcementView paradigm toggle', () => {
  it('switches from the GridWorld demo to the Deep RL workbench', async () => {
    mockCatalogFetch();
    render(<ReinforcementView />);
    // Demo is shown by default (GridWorld title present).
    expect(screen.getByText('Apprentissage par renforcement')).toBeTruthy();
    // Click the "Deep RL" tab -> the Deep RL workbench mounts.
    fireEvent.click(screen.getByRole('tab', { name: /Deep RL/ }));
    expect(await screen.findByText('Deep Reinforcement Learning')).toBeTruthy();
  });
});
