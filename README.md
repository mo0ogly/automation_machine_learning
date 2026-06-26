# ML Automator — pipeline ML agentique, expert-in-the-loop

Construction d'un modèle de machine learning décomposée en **étapes explicites,
inspectables et rejouables**, où un agent LLM (Groq) propose un affinage à chaque
étape et où l'expert valide ou ajuste — dans une boucle OODA.

```
Nettoyage → Transformation → Intégration → Séparation → Modèle → Fine-tuning → Évaluation → Explicabilité
(clean)     (transform)      (integrate)    (separate)   (model)  (tune)        (evaluate)   (explain)
```

Chaque étape : **Observe** (diagnostics déterministes) → **Orient** (recommandation
de l'agent, ancrée sur les vrais chiffres) → **Decide** (l'expert règle la config) →
**Act** (exécuter / rejouer). Rejouer une étape invalide automatiquement les étapes aval.

Les **3 paradigmes** sont couverts : **supervisé** (régression, classification binaire &
multiclasse), **non supervisé** (clustering KMeans/DBSCAN/Agglomératif **et** détection
d'anomalies Isolation Forest/LOF) et **renforcement** (Q-learning sur GridWorld, onglet
« Renforcement »).

> **Architecture détaillée & guide de reprise** (socle, couche agentique, fidélité notebook,
> 3 paradigmes & Atelier Jour 2) : [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

### Couche agentique (mode assisté)

- **Copilote d'analyse** (panneau latéral) : assistants contextuels + **journal mémoire** —
  chaque réponse IA est mémorisée et **ré-injectée dans les prompts suivants**.
- **Une IA par graphe** : chaque figure a sa légende, un bouton `✦` qui l'explique, et la
  réponse s'affiche **inline sous le graphe** (en plus du journal). Modale de zoom (DPI 160).
- **Tables de décision** : l'expert coche les colonnes/variables à garder (avis + raison IA).
- Bascule **Novice / Expert** sur la verbosité des explications.

## Architecture

### Backend (FastAPI, port 8000)
| Fichier | Responsabilité |
|---------|----------------|
| `backend/app.py` | Routes : session, diagnose/recommend/run par étape, predict, export |
| `backend/llm_agent.py` | Agent d'affinage Groq (REST compatible OpenAI) + repli heuristique déterministe |
| `backend/env_loader.py` | Chargement `.env` + garde TLS (mitmproxy CA → certifi si proxy down) |
| `backend/pipeline/context.py` | Détection cible + type de problème |
| `backend/pipeline/session.py` | État de session **rejouable** (snapshots + invalidation aval) |
| `backend/pipeline/diagnostics.py` | Diagnostics purs/déterministes (alimentent l'UI **et** l'agent) |
| `backend/pipeline/typology.py` | Typologie 4 voies (continue/discrète/nominale/ordinale) + encodage ordinal **ordonné** |
| `backend/pipeline/stages/*.py` | Une étape par module (contrat uniforme `default_config`/`config_schema`/`diagnose`/`run`) ; `tune.py` (GridSearchCV), `explain.py` (SHAP) |

## Fidélité aux ateliers J1/J2 (notebooks corrigés)

- **Typologie en 4 voies** : quantitative continue / discrète / catégorielle **nominale** / **ordinale**.
- **Encodage ordinal ordonné** : les notes de qualité (`Po<Fa<TA<Gd<Ex`) sont encodées en gardant leur ordre sémantique (`qual_map` du notebook), pas en ordre alphabétique ; les nominales en One-Hot.
- **Exclusion d'aberrants** pilotée par l'analyse univariée (ex. `GrLivArea > 4000`), configurable par l'expert.
- **Modèles** : Linéaire/Logistique, Arbre de décision, Random Forest, Gradient Boosting, **XGBoost**.
- **Fine-tuning** : `GridSearchCV` (validation croisée) — le modèle optimisé remplace la baseline.
- **Explicabilité** : `SHAP` (importance globale + waterfall) sur les modèles à base d'arbres.

### Frontend (React + Vite, port 5173)
| Composant | Rôle |
|-----------|------|
| `Dashboard.jsx` | Orchestration du flux + état de session (persisté en `localStorage`) |
| `StageStepper.jsx` | Stepper des 8 étapes (statut fait / actif / à rejouer) |
| `StagePanel.jsx` | Panneau d'étape (onglets) : diagnostics, reco agent, config, résultat, graphes |
| `Copilot.jsx` | Copilote d'analyse : assistants contextuels + journal mémoire + niveau Novice/Expert |
| `AssistButton.jsx` · `AssistAnswer.jsx` | Bouton `✦` par sous-étape/graphe · réponse IA inline |
| `PlotModal.jsx` · `ColumnTable.jsx` | Modale de zoom des graphes · tables de décision |
| `AgentRecommendation.jsx` · `ConfigControls.jsx` · `DiagnosticsView.jsx` | Affinage proposé · contrôles depuis le schéma · diagnostics génériques |

## Démarrer

### 1. Backend
```bash
cd backend
python -m pip install -r requirements.txt
# Clé Groq (sinon repli heuristique déterministe) :
cp .env.example .env   # puis renseigner GROQ_API_KEY
python -m uvicorn app:app --port 8000
```

### 2. Frontend
```bash
cd frontend
npm install
npm run dev     # http://localhost:5173 (proxy vers le backend :8000)
```

## Agent d'affinage (Groq)

- À chaque étape, `llm_agent.recommend()` envoie à Groq l'objectif de l'étape, le
  schéma de configuration et les **diagnostics chiffrés réels** ; le modèle renvoie
  un JSON strict (résumé, justifications, `suggested_config`, risque, confiance).
- La config suggérée est **validée contre le schéma** avant tout usage (aucune clé
  ni valeur invalide ne peut atteindre `run`).
- Si Groq est indisponible (clé absente, réseau), un **repli heuristique déterministe**
  prend le relais — clairement étiqueté `source: "heuristic-fallback"`.
- Modèle par défaut : `openai/gpt-oss-120b` (7 modèles sélectionnables ; configurable via `GROQ_MODEL`).
- Mêmes mécanismes pour `interpret` (conclusion d'un résultat) et `assist` (explication d'un
  élément/graphe précis) ; tous **ré-injectent le journal mémoire** de la session.

## API (extrait)
| Méthode | Route | Effet |
|---------|-------|-------|
| POST | `/api/session/start` (upload) · `/api/session/start-demo/{name}` | Crée une session, détecte cible/type |
| GET | `/api/session/{sid}/stage/{stage}` | Schéma + diagnostics + dernier résultat |
| POST | `/api/session/{sid}/stage/{stage}/recommend` | Affinage de l'agent |
| POST | `/api/session/{sid}/stage/{stage}/run` | Exécute / rejoue l'étape |
| POST | `/api/session/{sid}/autorun` | Exécute toutes les étapes (config par défaut) |
| POST | `/api/session/{sid}/predict` · GET `/download-model` | Inférence · export `.pkl` |

## Tests
```bash
cd backend && python -m pytest tests/test_api.py -q   # 36 tests, sans réseau
```
