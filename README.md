# automation_machine_learning

> **English** · [Français](README.fr.md)

**Marrying two worlds**: the **rigor of classical machine learning** (statistical models,
deterministic metrics, reproducibility) and the **fluency of LLMs** (reasoning, contextual
recommendations, natural-language explanations) — to get the best of both.

Concretely: a machine-learning model built in **explicit, inspectable and replayable
stages**, where an **LLM copilot** (multi-provider, OpenAI-compatible) *observes* the numeric diagnostics and
*orients* with recommendations grounded in the real numbers, while the **expert** *decides*
and *acts*.

```
Clean → Transform → Integrate → Separate → Model → Fine-tuning → Evaluate → Explainability
```

Each stage: **Observe** (deterministic diagnostics) → **Orient** (agent recommendation,
grounded in the real numbers) → **Decide** (the expert sets the config) → **Act**
(run / replay). Replaying a stage automatically invalidates the downstream ones.

> **"OODA" and "agentic", without overselling.** The Observe-Orient-Decide-Act loop is a
> *conceptual frame* (not Boyd's strict military OODA). And it is "agentic" in the sense that
> an LLM agent steps in at every stage **with a re-injected session memory** — but
> **human-in-the-loop**: the LLM proposes, the expert decides. It is **not** an autonomous
> agent acting without supervision; control stays with the human.

All **3 learning paradigms** are covered:

- **Supervised** — regression + classification (binary & multiclass): RMSE/R², or
  accuracy / precision / recall / F1 + per-class report + confusion matrix.
- **Unsupervised** — **clustering** (KMeans / DBSCAN / Agglomerative; silhouette,
  Davies-Bouldin, Calinski-Harabasz; business reading in real units + a **decision table**
  to name clusters) **and anomaly detection** (Isolation Forest / LOF).
- **Reinforcement** — two modes in a dedicated "Reinforcement" tab: a tabular **Q-learning**
  demo on a GridWorld (one or several goals, visible traps), and a **Deep RL** workbench
  (Gymnasium + Stable-Baselines3) on continuous-state environments. It ships **13 algorithms**
  (PPO/A2C/DQN/SAC/TD3/DDPG core + QRDQN/TRPO/TQC/RecurrentPPO/ARS/CrossQ/MaskablePPO from
  sb3-contrib), and three purpose-built **cyber-defense** environments: SOC alert triage under a
  response budget (with action masking), spreading-**incident containment** (a real temporal
  trade-off), and online **IDS threshold tuning** (a *continuous* action — so the continuous-control
  algorithms apply to security, not to a pendulum). Every run is scored against a measured
  **random baseline** ("does it actually beat chance?") and an **AI diagnosis** button gives a
  plain verdict (good / mediocre / insufficient) plus concrete SOC next steps. Ready-to-train
  cyber-first presets ("base models") are included. Agents are a
  first-class object: **save** a trained agent to a persistent **"My agents"** registry,
  **re-evaluate** it, **continue training** (warm-start), **import** an externally-trained `.zip`,
  **import your own CSV** of alerts as a bespoke triage environment, and **export** a
  self-describing bundle (model + metrics report).

> **Detailed architecture** (core, agentic layer, 3 paradigms):
> [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

### Agentic layer (assisted mode)

- **Analysis copilot** (side panel): contextual assistants + a **memory journal** — every
  AI answer is recorded and **re-injected into subsequent prompts**.
- **One AI per chart**: each figure has its caption, a `✦` button that explains it, and the
  answer shows **inline below the chart** (in addition to the journal). Zoom modal (DPI 160).
- **Decision tables**: the expert ticks the columns/features to keep (AI advice + reason)
  and names the clusters.
- **Novice / Expert** toggle on explanation verbosity.
- **FR / EN interface** (`react-i18next`): a language switch in the top nav toggles the whole
  UI between French and English, persisted in `localStorage`. French is the source of truth
  and the fallback language.

## Architecture

### Backend (FastAPI, port 8000)
| File | Responsibility |
|------|----------------|
| `backend/app.py` | Routes: session, per-stage diagnose/recommend/run, predict, export, `/api/rl/train` |
| `backend/llm_agent.py` | Groq refinement agent (OpenAI-compatible REST) + deterministic heuristic fallback |
| `backend/env_loader.py` | `.env` loading + TLS guard (mitmproxy CA → certifi when the proxy is down) |
| `backend/pipeline/context.py` | Target + problem-type detection (regression / classification / clustering / anomaly) |
| `backend/pipeline/session.py` | **Replayable** session state (snapshots + downstream invalidation) |
| `backend/pipeline/persistence.py` | SQLite write-through mirror (one joblib blob/session) — sessions **survive a backend restart** |
| `backend/pipeline/stages/*.py` | One stage per module (uniform `default_config`/`config_schema`/`diagnose`/`run` contract); `tune.py` (GridSearchCV), `explain.py` (SHAP) |
| `backend/rl/` | Reinforcement subsystem: `gridworld.py`, `qlearning.py`, `plots.py` (NumPy only) |

### Frontend (React + Vite, port 5173)
| Component | Role |
|-----------|------|
| `Dashboard.jsx` | Flow orchestration + session state (persisted in `localStorage`) |
| `StagePanel.jsx` | Stage panel (tabs): diagnostics, agent recommendation, config, result, charts |
| `Copilot.jsx` | Analysis copilot: contextual assistants + memory journal + Novice/Expert level |
| `ReinforcementView.jsx` | "Reinforcement" tab: settings, metrics, policy/value/reward plots |
| `PlotModal.jsx` · `ColumnTable.jsx` | Chart zoom modal · decision tables |
| `LanguageSwitcher.jsx` · `i18n/` | FR/EN toggle · `react-i18next` setup, one JSON namespace per component under `i18n/locales/{fr,en}/` |

## Modeling & data handling

- **4-way typology**: quantitative continuous / discrete / **nominal** / **ordinal** categorical.
- **Ordered ordinal encoding**: quality grades (`Po<Fa<TA<Gd<Ex`) keep their semantic order
  (a dedicated lookup table), not alphabetical order; nominals are One-Hot encoded.
- **Feature engineering**: domain features (guarded) plus generic **interactions** (products /
  ratios of the highest-variance numeric columns, bounded) and **binning** (quantile / uniform
  discretisation). Shared with the leakage-free preprocessor: the interaction base columns and
  bin edges are **fit on the train split only** and reused on test/serving (`feature_engineering.py`).
- **Cleaning**: model-based **imputation** (KNN / iterative, estimating a missing cell from the
  other features) beside median/mean/zero; **outlier handling** by IQR (Tukey) or z-score, in
  clip or remove variants; and a **per-column data-quality diagnostic** (missing %, distinct,
  outliers, flags: constant / high-cardinality id / heavy-missing), sorted worst-first.
- **Outlier exclusion** driven by univariate analysis, expert-configurable.
- **Leakage-free preprocessing**: the Separation stage splits FIRST, then fits every
  data-dependent transformer (skew correction, one-hot categories, scaler statistics,
  **univariate feature selection** and PCA) on the **train partition only** (`pipeline/preprocessing.py`); the fitted preprocessor is
  reused verbatim by serving (`/predict`) and the model export, so serving can never drift
  from training. The full-frame transform remains for the exploratory EDA views only.
- **Models**: Linear/Ridge/Lasso/ElasticNet/Logistic, **SVM**, **k-NN**, **Naive Bayes**,
  Decision Tree, Random Forest, Gradient Boosting, **XGBoost** — every family selectable on the
  leaderboard, tunable with its own grid, and described inline (with an AI helper button) so a
  non-expert analyst is never left alone before a technical choice.
- **Honest model selection**: the Modelling leaderboard ranks candidates by **k-fold
  cross-validation on the train set** (mean ± std, train-vs-CV overfit gap) — the held-out
  test set is never consulted before Evaluation.
- **Class-imbalance handling**: on skewed cyber targets (KEV ~13%, phishing ~22%), the
  Modelling stage offers `class_weight='balanced'` (cross-validation-safe, used by the
  leaderboard) and **resampling** — random over/under-sampling and **SMOTE** (synthetic
  minority interpolation, no `imbalanced-learn` dependency) applied to the **final training
  fit only** (never the test set, never inside the CV folds). On KEV this lifts rare-class
  recall ~4x at the default threshold.
- **Fine-tuning**: per-family hyperparameter grids (linear, tree, forest, boosting, XGBoost),
  `GridSearchCV` or `RandomizedSearchCV`, defaults to the baseline algorithm; tuned-vs-baseline
  compared on CV (and the optional validation carve-out), never on the test set.
- **Evaluation**: RMSE/MAE/MAPE/R² (regression); accuracy/precision/recall/F1 + **ROC-AUC,
  PR-AUC with their curves** (binary) or weighted OVR AUC (multiclass); overfit control
  (train/test/CV) and a **learning curve**; optional `class_weight='balanced'` for imbalance.
- **Model card (enriched)**: the Exploit view's model dossier now includes the recommended
  **operating point** (min-cost threshold + resulting recall/precision) and a data-driven
  **assessment** (verdict + strengths + cautions: overfitting gap, ROC-AUC, calibration,
  leakage-free flag, drift reminder).
- **Explainability**: `SHAP` importance + waterfall — `TreeExplainer` for tree models,
  `LinearExplainer` for linear families, configurable explained class in multiclass.
- **Partial dependence (PDP)**: beside SHAP (which ranks feature *importance*), the
  Explicability stage plots the *shape* of the learned effect — 1-D curves for the top
  SHAP features and a **2-D surface for the top pair** (surfacing interactions) plus optional
  **ICE** curves (one per instance, revealing subgroup heterogeneity), adaptive to
  regression / binary / multiclass (`explain_plots.py`).
- **Operational evaluation (SOC / threat-intel)**: an adaptive operating-point panel on top of
  the metrics — an interactive **decision-threshold** slider (0.5 is rarely right in cyber),
  **cost of errors** (a missed attack vs a false alert), a business confusion matrix
  (detection / miss / false alert / normal), **calibration** (reliability curve, Brier, ECE),
  imbalance-robust scores (**MCC**, balanced accuracy, kappa), an **alert-budget** view
  (precision@k / detection@k) and a **SOC deployment playbook**. Recomputed live from the
  stored test predictions (`/operating-point`, no re-fit); adapts to the paradigm (binary/
  multiclass detection, anomaly, regression tolerance bands).
- **Drift & stability monitoring (post-deployment)**: upload a new batch of rows to compare
  against the training reference — **data drift** (PSI + Kolmogorov-Smirnov per feature),
  **concept drift** (prediction-distribution shift / alert-rate change), **reproducibility**
  (re-score a reference sample: determinism + consistency with the recorded evaluation — the
  honest, measurable form of "jitter"), and **threshold re-calibration** on the new batch.
  `POST /monitor`, adaptive to the paradigm, with a per-panel AI helper.
- **Jitter protocol (prediction stability)**: perturb the reference set with Gaussian noise at
  increasing amplitudes (0.1% to 10% of each feature's std), re-score, and measure the
  **flip rate** of the verdicts — with a tolerance curve, a breaking point and a
  stable/sensitive/unstable verdict. Deterministic (fixed seed), `POST /jitter`, no re-fit.
  A detector whose verdicts flip at 0.1% noise is unstable in a critical environment
  regardless of the hardware it runs on.
- **Advanced stability analyses** (`POST /stability/{analysis}`, all deterministic, no upload):
  **numerical jitter** (float32 vs float64 and single-thread re-scoring — the only software-side
  form of "hardware jitter"), **margin analysis** (share of the population within a hair's width
  of the decision threshold — who would flip first), **prediction churn** (re-fit with different
  seeds, measure verdict disagreement — structural instability), **conformal prediction**
  (finite-sample coverage guarantee under exchangeability: prediction sets flag statistically
  ambiguous verdicts; conformal p-values for unsupervised detection), and **certified robustness**
  via randomized smoothing (Cohen et al., ICML 2019 — certified L2 radius of the smoothed
  classifier, Clopper-Pearson bound). Each returns a verdict, key numbers and a figure.
- **Cyber demo datasets** (synthetic, for SOC/threat-intel learning): phishing URLs, spam,
  CVE severity (CVSS vector), and KEV exploitation (heavily imbalanced) — alongside the
  existing cyber-risk, prompt-injection and anomaly demos.

## Getting started

### Option A — Docker (recommended)

The whole stack (backend FastAPI + frontend nginx) in one command. Needs Docker
Desktop / Docker Engine with the compose plugin.

```bash
cp .env.example .env          # optional: set GROQ_API_KEY (a heuristic fallback runs without it)

./mlauto.sh up                # build + start, waits until healthy   (Linux/macOS/Git Bash)
.\mlauto.ps1 up               # same, on Windows PowerShell
```

Then open **http://localhost:5173**. Other verbs: `down`, `restart`, `build`,
`rebuild`, `logs [svc]`, `status`, `health`, `shell [svc]`, `test`, `clean`
(`./mlauto.sh help`). Sessions persist on the `mlauto-data` volume (SQLite), so
they survive `down` + rebuild. Ports are overridable in `.env`
(`BACKEND_PORT` / `FRONTEND_PORT`).

### Option B — local (no Docker)

```bash
# Backend
cd backend
python -m pip install -r requirements.txt
cp .env.example .env          # then set GROQ_API_KEY (otherwise a heuristic fallback is used)
python -m uvicorn app:app --port 8000

# Frontend (second terminal)
cd frontend
npm install                   # includes react-i18next / i18next / i18next-browser-languagedetector
npm run dev                   # http://localhost:5173 (calls the backend on :8000)
```

## API (excerpt)
| Method | Route | Effect |
|--------|-------|--------|
| POST | `/api/session/start` (upload) · `/api/session/start-demo/{name}` | Create a session, detect target/type |
| GET | `/api/session/{sid}/stage/{stage}` | Schema + diagnostics + last result |
| POST | `/api/session/{sid}/stage/{stage}/run` · `/recommend` · `/assist` | Run · refine · explain an element |
| POST | `/api/session/{sid}/autorun` | Run all stages (default config) |
| POST | `/api/rl/train` | Train a Q-learning agent on GridWorld → metrics + plots |
| GET | `/api/rl/deep/catalog` | Deep RL environments, 13 algorithms + hyperparameters, presets, saved agents |
| POST | `/api/rl/deep/train` | Start a Deep RL training job → `job_id` |
| GET | `/api/rl/deep/job/{id}` · `/download` | Poll a job (progress + result) · download the trained agent (`.zip`) |
| POST | `/api/rl/deep/save` | Persist a finished job's agent to the "My agents" registry |
| GET · DELETE | `/api/rl/deep/registry` · `/registry/{id}` | List saved agents · delete one |
| GET | `/api/rl/deep/registry/{id}/download` · `/export` | Download an agent (`.zip`) · export a bundle (model + report) |
| POST | `/api/rl/deep/evaluate` · `/continue` | Evaluate a saved agent · resume training (warm-start) |
| POST | `/api/rl/deep/import` · `/import-env` | Import an SB3 `.zip` agent · import a CSV as a triage env |
| DELETE | `/api/rl/deep/env/{id}` | Delete a user-imported CSV environment |

## Tests
```bash
cd backend && python -m pytest tests/test_api.py -q   # 44 tests, no network
```

## Roadmap

- **LLM providers** — **done**: a settings panel (the `⚙ Moteur IA` button) manages multiple
  OpenAI-compatible backends driven by a server-side provider **catalog** of **26 vendors**
  ported from [recette_IA_agents](https://github.com/mo0ogly/recette_IA_agents) — Groq, OpenAI,
  Mistral, DeepSeek, xAI (Grok), OpenRouter, Together, Fireworks, Moonshot (Kimi), Z.AI (GLM),
  DashScope/Qwen, Nvidia, Nous, Ollama Cloud, Novita, StepFun, Arcee, Xiaomi, GMI, Hugging Face,
  OpenCode Zen, Kilo Code, Alibaba Coding Plan, Qwen Portal, Cerebras, and `openai_compat`
  (Ollama/LiteLLM/vLLM with a per-backend base URL). Each backend has **write-only keys** (or the
  provider env var — see `backend/.env.example`) and a connectivity **Test**.
- **Session persistence** — **done**: sessions are mirrored to SQLite (`backend/sessions.db`)
  and survive a backend restart (toggle with `ML_PERSIST_SESSIONS`). Next: a shared store
  (Redis/Postgres) for a multi-process backend.
- **Unsupervised** — **done**: Davies-Bouldin / Calinski-Harabasz indices + the Ward dendrogram
  for agglomerative clustering (truncated to the last 30 merges, sampled beyond 300 rows).

## License

This project is **source-available, for noncommercial use only**, under the
[PolyForm Noncommercial License 1.0.0](LICENSE). Commercial use is not permitted under
this license — for a commercial license, contact the copyright holder. Note: a
"noncommercial" license is not "open source" in the strict (OSI) sense, which forbids any
field-of-use restriction; the accurate term here is *source-available*.
