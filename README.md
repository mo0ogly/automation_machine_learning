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
- **Reinforcement** — Q-learning on a GridWorld environment (one or several goals, visible
  traps), in a dedicated "Reinforcement" tab.

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

## Modeling & data handling

- **4-way typology**: quantitative continuous / discrete / **nominal** / **ordinal** categorical.
- **Ordered ordinal encoding**: quality grades (`Po<Fa<TA<Gd<Ex`) keep their semantic order
  (a dedicated lookup table), not alphabetical order; nominals are One-Hot encoded.
- **Outlier exclusion** driven by univariate analysis, expert-configurable.
- **Models**: Linear/Logistic, Decision Tree, Random Forest, Gradient Boosting, **XGBoost**.
- **Fine-tuning** `GridSearchCV`; **Explainability** `SHAP` (importance + waterfall).

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
npm install
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

## Tests
```bash
cd backend && python -m pytest tests/test_api.py -q   # 44 tests, no network
```

## Roadmap

- **LLM providers** — **done**: a settings panel (the `⚙ Moteur IA` button) manages multiple
  OpenAI-compatible backends (Groq, OpenAI, Mistral, DeepSeek, Ollama/local), driven by a
  server-side provider **catalog**, with per-backend **write-only keys** (or the provider env
  var) and a connectivity **Test**. Next: Anthropic (its messages API differs) + a LiteLLM
  gateway preset.
- **Session persistence** — **done**: sessions are mirrored to SQLite (`backend/sessions.db`)
  and survive a backend restart (toggle with `ML_PERSIST_SESSIONS`). Next: a shared store
  (Redis/Postgres) for a multi-process backend.
- **Unsupervised** — Davies-Bouldin / Calinski-Harabasz are in; agglomerative dendrogram next.

## License

This project is **source-available, for noncommercial use only**, under the
[PolyForm Noncommercial License 1.0.0](LICENSE). Commercial use is not permitted under
this license — for a commercial license, contact the copyright holder. Note: a
"noncommercial" license is not "open source" in the strict (OSI) sense, which forbids any
field-of-use restriction; the accurate term here is *source-available*.
