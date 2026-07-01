# automation_machine_learning

> **Français** · [English](README.md)

**Marier deux mondes** : la **rigueur du machine learning classique** (modèles statistiques,
métriques déterministes, reproductibilité) et la **fluidité des LLM** (raisonnement,
recommandations contextuelles, explications en langage naturel) — pour en tirer le meilleur
des deux.

Concrètement : un modèle de machine learning construit en **étapes explicites, inspectables
et rejouables**, où un **LLM copilote** (multi-provider, compatible OpenAI) *observe* les diagnostics
chiffrés et *oriente* par des recommandations ancrées sur les vrais nombres, pendant que
l'**expert** *décide* et *agit*.

```
Nettoyage → Transformation → Intégration → Séparation → Modèle → Fine-tuning → Évaluation → Explicabilité
(clean)     (transform)      (integrate)    (separate)   (model)  (tune)        (evaluate)   (explain)
```

Chaque étape : **Observe** (diagnostics déterministes) → **Orient** (recommandation
de l'agent, ancrée sur les vrais chiffres) → **Decide** (l'expert règle la config) →
**Act** (exécuter / rejouer). Rejouer une étape invalide automatiquement les étapes aval.

> **« OODA » et « agentique », sans survente.** La boucle Observe-Orient-Decide-Act est un
> *cadre conceptuel* (pas l'OODA militaire strict de Boyd). Et c'est « agentique » au sens où
> un agent LLM intervient à chaque étape **avec une mémoire de session ré-injectée** — mais en
> **human-in-the-loop** : le LLM propose, l'expert tranche. Ce n'est **pas** un agent autonome
> qui agirait sans supervision ; le contrôle reste à l'humain.

Les **3 paradigmes** d'apprentissage sont couverts :

- **Supervisé** — régression + classification (binaire & multiclasse) : RMSE/R², ou
  accuracy / précision / rappel / F1 + rapport par classe + matrice de confusion.
- **Non supervisé** — **clustering** (KMeans / DBSCAN / Agglomératif ; silhouette,
  Davies-Bouldin, Calinski-Harabasz ; lecture métier en valeurs réelles + **table de
  décision** pour nommer les clusters) **et détection d'anomalies** (Isolation Forest / LOF).
- **Renforcement** — Q-learning sur un environnement GridWorld (un ou plusieurs buts,
  pièges visibles), onglet « Renforcement » dédié.

> **Architecture détaillée** (socle, couche agentique, 3 paradigmes) :
> [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

### Couche agentique (mode assisté)

- **Copilote d'analyse** (panneau latéral) : assistants contextuels + **journal mémoire** —
  chaque réponse IA est mémorisée et **ré-injectée dans les prompts suivants**.
- **Une IA par graphe** : chaque figure a sa légende, un bouton `✦` qui l'explique, et la
  réponse s'affiche **inline sous le graphe** (en plus du journal). Modale de zoom (DPI 160).
- **Tables de décision** : l'expert coche les colonnes/variables à garder (avis + raison IA)
  et nomme les clusters.
- Bascule **Novice / Expert** sur la verbosité des explications.

## Architecture

### Backend (FastAPI, port 8000)
| Fichier | Responsabilité |
|---------|----------------|
| `backend/app.py` | Routes : session, diagnose/recommend/run par étape, predict, export, `/api/rl/train` |
| `backend/llm_agent.py` | Agent d'affinage Groq (REST compatible OpenAI) + repli heuristique déterministe |
| `backend/env_loader.py` | Chargement `.env` + garde TLS (mitmproxy CA → certifi si proxy down) |
| `backend/pipeline/context.py` | Détection cible + type de problème (régression / classification / clustering / anomalie) |
| `backend/pipeline/session.py` | État de session **rejouable** (snapshots + invalidation aval) |
| `backend/pipeline/persistence.py` | Miroir SQLite write-through (un blob joblib/session) — les sessions **survivent à un redémarrage** du backend |
| `backend/pipeline/stages/*.py` | Une étape par module (contrat uniforme `default_config`/`config_schema`/`diagnose`/`run`) ; `tune.py` (GridSearchCV), `explain.py` (SHAP) |
| `backend/rl/` | Sous-système renforcement : `gridworld.py`, `qlearning.py`, `plots.py` (NumPy seul) |

### Frontend (React + Vite, port 5173)
| Composant | Rôle |
|-----------|------|
| `Dashboard.jsx` | Orchestration du flux + état de session (persisté en `localStorage`) |
| `StagePanel.jsx` | Panneau d'étape (onglets) : diagnostics, reco agent, config, résultat, graphes |
| `Copilot.jsx` | Copilote d'analyse : assistants contextuels + journal mémoire + niveau Novice/Expert |
| `ReinforcementView.jsx` | Onglet « Renforcement » : réglages, métriques, politique/valeur/récompense |
| `PlotModal.jsx` · `ColumnTable.jsx` | Modale de zoom des graphes · tables de décision |

## Modélisation & traitement des données

- **Typologie en 4 voies** : quantitative continue / discrète / catégorielle **nominale** / **ordinale**.
- **Encodage ordinal ordonné** : les notes de qualité (`Po<Fa<TA<Gd<Ex`) gardent leur ordre
  sémantique (table de correspondance dédiée), pas l'ordre alphabétique ; les nominales en One-Hot.
- **Exclusion d'aberrants** pilotée par l'analyse univariée, configurable par l'expert.
- **Prétraitement anti-fuite** : l'étape Séparation découpe D'ABORD, puis ajuste chaque
  transformateur dépendant des données (redressement d'asymétrie, catégories One-Hot,
  statistiques d'échelle, PCA) sur la **partition train uniquement**
  (`pipeline/preprocessing.py`) ; le préprocesseur ajusté est réutilisé tel quel par le
  serving (`/predict`) et l'export du modèle — le serving ne peut pas dériver de
  l'entraînement. La transformation plein-cadre ne sert plus qu'aux vues exploratoires (EDA).
- **Modèles** : Linéaire/Ridge/Lasso/Logistique, Arbre de décision, Random Forest,
  Gradient Boosting, **XGBoost**.
- **Sélection honnête du modèle** : le leaderboard de Modélisation classe les candidats par
  **validation croisée k-fold sur le train** (moyenne ± écart-type, écart train/CV de
  surapprentissage) — le jeu de test n'est jamais consulté avant l'Évaluation.
- **Fine-tuning** : grilles d'hyperparamètres par famille (linéaire, arbre, forêt, boosting,
  XGBoost), `GridSearchCV` ou `RandomizedSearchCV`, algorithme du baseline par défaut ;
  comparaison tuné-vs-baseline en CV (et sur le jeu de validation optionnel), jamais sur le test.
- **Évaluation** : RMSE/MAE/MAPE/R² (régression) ; accuracy/précision/rappel/F1 + **ROC-AUC,
  PR-AUC avec leurs courbes** (binaire) ou AUC OVR pondéré (multiclasse) ; contrôle du
  surapprentissage (train/test/CV) et **courbe d'apprentissage** ; option
  `class_weight='balanced'` pour le déséquilibre.
- **Explicabilité** : `SHAP` importance + waterfall — `TreeExplainer` pour les arbres,
  `LinearExplainer` pour les familles linéaires, classe expliquée configurable en multiclasse.

## Démarrer

### Option A — Docker (recommandé)

Toute la stack (backend FastAPI + frontend nginx) en une commande. Nécessite
Docker Desktop / Docker Engine avec le plugin compose.

```bash
cp .env.example .env          # optionnel : renseigner GROQ_API_KEY (repli heuristique sinon)

./mlauto.sh up                # build + démarrage, attend que ce soit sain   (Linux/macOS/Git Bash)
.\mlauto.ps1 up               # idem, sous Windows PowerShell
```

Puis ouvrir **http://localhost:5173**. Autres verbes : `down`, `restart`,
`build`, `rebuild`, `logs [svc]`, `status`, `health`, `shell [svc]`, `test`,
`clean` (`./mlauto.sh help`). Les sessions persistent sur le volume
`mlauto-data` (SQLite) et survivent à `down` + rebuild. Ports surchargeables
dans `.env` (`BACKEND_PORT` / `FRONTEND_PORT`).

### Option B — local (sans Docker)

```bash
# Backend
cd backend
python -m pip install -r requirements.txt
cp .env.example .env          # puis renseigner GROQ_API_KEY (sinon repli heuristique)
python -m uvicorn app:app --port 8000

# Frontend (second terminal)
cd frontend
npm install
npm run dev                   # http://localhost:5173 (appelle le backend :8000)
```

## API (extrait)
| Méthode | Route | Effet |
|---------|-------|-------|
| POST | `/api/session/start` (upload) · `/api/session/start-demo/{name}` | Crée une session, détecte cible/type |
| GET | `/api/session/{sid}/stage/{stage}` | Schéma + diagnostics + dernier résultat |
| POST | `/api/session/{sid}/stage/{stage}/run` · `/recommend` · `/assist` | Exécute · affine · explique un élément |
| POST | `/api/session/{sid}/autorun` | Exécute toutes les étapes (config par défaut) |
| POST | `/api/rl/train` | Entraîne un agent Q-learning sur GridWorld → métriques + graphes |

## Tests
```bash
cd backend && python -m pytest tests/test_api.py -q   # 44 tests, sans réseau
```

## Roadmap

- **Providers LLM** — **fait** : une fenêtre de paramétrage (bouton `⚙ Moteur IA`) gère
  plusieurs backends compatibles OpenAI, pilotée par un **catalogue** côté serveur de **26 vendors**
  repris de [recette_IA_agents](https://github.com/mo0ogly/recette_IA_agents) — Groq, OpenAI,
  Mistral, DeepSeek, xAI (Grok), OpenRouter, Together, Fireworks, Moonshot (Kimi), Z.AI (GLM),
  DashScope/Qwen, Nvidia, Nous, Ollama Cloud, Novita, StepFun, Arcee, Xiaomi, GMI, Hugging Face,
  OpenCode Zen, Kilo Code, Alibaba Coding Plan, Qwen Portal, Cerebras, et `openai_compat`
  (Ollama/LiteLLM/vLLM avec base URL par backend). Chaque backend a des **clés write-only** (ou la
  variable d'environnement du provider — voir `backend/.env.example`) et un **Test** de connectivité.
- **Persistance des sessions** — **faite** : les sessions sont mirroir-ées en SQLite
  (`backend/sessions.db`) et survivent à un redémarrage du backend (toggle `ML_PERSIST_SESSIONS`).
  À suivre : un store partagé (Redis/Postgres) pour un backend multi-process.
- **Non supervisé** — **fait** : indices Davies-Bouldin / Calinski-Harabasz + dendrogramme de
  Ward pour l'agglomératif (troncature aux 30 dernières fusions, échantillonné au-delà de 300 lignes).

## Licence

Ce projet est **source-available, à usage non commercial uniquement**, sous
[PolyForm Noncommercial License 1.0.0](LICENSE). L'usage commercial n'est pas autorisé
sous cette licence — pour une licence commerciale, contacter le détenteur des droits.
À noter : une licence « non commerciale » n'est pas « open source » au sens strict (OSI),
qui interdit toute restriction de domaine d'usage ; le terme exact ici est *source-available*.
