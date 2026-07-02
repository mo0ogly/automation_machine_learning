# Architecture & guide de reprise — ML Automator

Document de référence pour comprendre tout le travail réalisé (pipeline agentique,
copilote, mémoire, IA par graphe) et **le reprendre pour étendre le ML non
supervisé**. Les identifiants de code restent en anglais ; les explications en français.

---

## 1. Vue d'ensemble

Construction d'un modèle ML décomposée en **8 étapes explicites, inspectables et
rejouables**. À chaque étape : on **observe** des diagnostics déterministes, l'**agent
Groq propose** un affinage ancré sur les vrais chiffres, l'**expert décide** (réglages /
tables de décision), puis on **exécute**. Rejouer une étape invalide les étapes aval.

```mermaid
flowchart LR
  CLEAN[Nettoyage] --> TRANSFORM[Transformation] --> INTEGRATE[Intégration] --> SEPARATE[Séparation]
  SEPARATE --> MODEL[Modèle] --> TUNE[Fine-tuning] --> EVAL[Évaluation] --> EXPLAIN[Explicabilité]
  classDef data fill:#0f3460,stroke:#e94560,color:#fff;
  classDef model fill:#3a1c5a,stroke:#8b5cf6,color:#fff;
  class CLEAN,TRANSFORM,INTEGRATE,SEPARATE data;
  class MODEL,TUNE,EVAL,EXPLAIN model;
```

- **Data-stages** (`clean, transform, integrate, separate`) opèrent sur un *dataframe*.
- **Model-stages** (`model, tune, evaluate, explain`) opèrent sur les *artefacts* de session.

**Trois paradigmes d'apprentissage couverts :**
- **Supervisé** — régression + classification (binaire & multiclasse), via le pipeline 8 étapes.
- **Non supervisé** — clustering (KMeans / DBSCAN / Agglomératif) **et** détection d'anomalies
  (Isolation Forest / LOF), via le même pipeline (`model` + `evaluate` spécialisés, pas de split).
- **Renforcement** — sous-système séparé (`backend/rl/`, route `/api/rl/train`, onglet
  « Renforcement ») : agent Q-learning tabulaire sur un environnement GridWorld. Voir §10.

---

## 2. Le socle backend (`backend/pipeline/`)

| Module | Rôle |
|--------|------|
| `context.py` | `PipelineContext` (target, `problem_type` ∈ {REGRESSION, CLASSIFICATION, CLUSTERING, ANOMALY}, `supervised`). Détecté depuis le CSV. |
| `session.py` | `Session` (raw_df, ctx, `runs: dict[str, StageRun]`, **`insights` journal**, `level`). `SessionStore SESSIONS` : cache mémoire + **miroir SQLite** (write-through, lazy-load au `get`). Replay + invalidation aval (`stale`), `current_model()`. |
| `persistence.py` | `SessionPersistence` : un blob `joblib` par session en **SQLite** (modèles, splits, DataFrames, journal). Les sessions **survivent à un redémarrage** du backend. Toggle `ML_PERSIST_SESSIONS=0`, chemin `ML_SESSION_DB`. Best-effort : un échec de DB ne casse jamais une requête. |
| `registry.py` | `STAGE_IDS`, `DATA_STAGE_IDS`, `get_stage()`, `stage_meta()`. |
| `diagnostics.py` | Diagnostics déterministes (overview, missing, outliers IQR, corrélations, leakage…). |
| `typology.py` | Typologie **4 voies** : continue / discrète / nominale / ordinale, + `encode_ordinal` (ordre sémantique préservé : absent=0, Po=1, Fa=2, TA=3, Gd=4, Ex=5). |
| `plotting.py` | `style_plot()`, **`fig_to_base64(fig) → {img, caption, topic}`** (DPI 160, caption auto-extraite du titre de la figure), `message_plot()`. |
| `eda_plots.py` | Univariée / bivariée — **une figure par variable** (lisible + IA par graphe). |
| `monitoring.py` | Surveillance post-déploiement (métriques pures, sans matplotlib) : dérive données (PSI + KS par variable), dérive de concept (TVD sur les prédictions), reproductibilité (déterminisme + cohérence avec l'évaluation enregistrée), re-calibration du seuil sur lot labellisé, et **`jitter_protocol`** (taux de bascule des verdicts sous bruit gaussien croissant, 0,1 %→10 % de l'écart-type par variable, seed fixée, verdict stable/sensible/instable ; LOF refusé honnêtement — pas de re-scoring). |
| `monitoring_plots.py` | Figures du rapport de surveillance : PSI par variable, distribution des prédictions référence vs lot, **courbe de tolérance au jitter** (bascule vs amplitude, point de rupture). |
| `stability.py` | Analyses de stabilité avancées (contrat d'affichage uniforme verdict + summary + notes) : **jitter numérique** (float32 vs float64, mono-thread), **analyse de marge** (population près du seuil), **churn de ré-entraînement** (désaccord entre seeds), **prédiction conforme** (ensembles/intervalles à couverture garantie, p-values conformes en anomalie), **robustesse certifiée** (randomized smoothing, Cohen et al. ICML 2019, borne Clopper-Pearson). Déterministe (seed fixée) ; refus honnêtes (LOF sans re-scoring, régression sans seuil). |
| `stability_plots.py` | Une figure par analyse : histogramme des écarts de score, histogramme des marges, barres de churn par seed, tailles d'ensembles conformes / p-values / résidus, courbe fraction-certifiée vs rayon. |

### Contrat d'une étape (`stages/*.py`)

Chaque module expose le même contrat (cf. `stages/base.py`) :

```python
STAGE_ID, TITLE, OBJECTIVE
default_config(df|ctx) -> dict
config_schema(df|ctx) -> list[control]      # select / toggle / range / number / column_table
diagnose(df|session) -> {"diagnostics": {...}, "plots": [ {img, caption, topic}, ... ]}
run(df, config, ctx) -> (df_out, result)    # data-stages
run(session, config) -> (result, artifacts) # model-stages
```

Les `control` sont rendus tels quels par le frontend. `column_table` = table de décision
(cases Garder/Retirer + avis IA + raison ; valeur = liste des colonnes à retirer).

---

## 3. Les 8 étapes

| # | Étape | Rôle | Supervisé | Non supervisé (clustering) |
|---|-------|------|-----------|----------------------------|
| 1 | `clean` | Choix des colonnes (table de décision), normalisation ordinale, imputation, aberrants IQR, exclusion univariée, doublons. EDA détaillée (valeurs catégorielles, lignes extrêmes). | idem | idem |
| 2 | `transform` | Features dérivées, asymétrie, encodage **ordinal ordonné** / One-Hot nominales, scaling. **EDA univariée + bivariée par type**. | idem | bivariée vs cible désactivée (pas de cible) |
| 3 | `integrate` | Matrice finale : **table de décision des variables** (redondance signalée), **sélection univariée** (SelectKBest F-test / info mutuelle, ajustée train-only dans `preprocessing.py`) et PCA optionnelles. | corr vs cible | corr inter-variables |
| 4 | `separate` | Split train/test stratifié + contrôle de fuite ; **préprocesseur anti-fuite** ajusté sur le train seul (`preprocessing.py`), réutilisé par serving/export. | X/y train/test | `X_full` (pas de split) |
| 5 | `model` | **Leaderboard** N modèles par **validation croisée sur le train** (RMSE/R² ou Acc/F1, moyenne ± σ — test vierge) + choix expert. | régression/classif | **KMeans / DBSCAN / Agglomératif** (clustering, k auto par coude/k-distance) · **Isolation Forest / LOF** (anomalies) |
| 6 | `tune` | GridSearch hyperparamètres. | oui | rejeté (409) |
| 7 | `evaluate` | Métriques test + **contrôle surapprentissage** (train/test/CV) + **vue opérationnelle SOC** (`operational.py` : seuils, coût FN/FP, calibration, budget d'alertes, métriques robustes MCC/bal-acc/kappa ; fiche SOC/TI). Recalcul live via `/operating-point`. | régression : scatter + résidus + bandes de tolérance · classif : confusion + **précision/rappel/F1 pondérés + rapport par classe** + ROC/PR + point de fonctionnement | clustering : **silhouette + lecture métier (valeurs brutes) + PCA + profil** · anomalies : **taux + histogramme des scores + PCA + top lignes atypiques** + budget d'alertes |
| 8 | `explain` | SHAP (importance globale + waterfall individuel). | oui | n/a |

---

## 4. Couche agentique (`llm_agent.py` + `agent_prompts.py`)

Trois capacités IA, toutes avec **repli heuristique déterministe** si `GROQ_API_KEY` absente :

| Fonction | Rôle | Prompt |
|----------|------|--------|
| `recommend(...)` | Propose un affinage de config (`suggested_config`) | `SYSTEM_PROMPT` + few-shot par étape |
| `interpret(...)` | Conclusion en langage naturel d'un résultat | `INTERPRET_SYSTEM` |
| `assist(topic, focus, ...)` | **Explique un élément précis** (un graphe, un tableau, un diagnostic), niveau Novice/Expert | `ASSIST_SYSTEM` |

### Mémoire (le fil conducteur)

- Chaque échange IA (`assist` / `recommend` / `interpret`) est **journalisé** :
  `session.add_insight(stage, topic, label, text, source, model)`.
- `session.journal_summary()` produit un récap compact **ré-injecté** dans les prompts
  suivants (`build_messages`, `build_interpret_messages`, `build_assist_messages`).
  → l'assistant se souvient de ce qu'il a déjà dit, à toutes les sous-étapes.
- `session.level` ∈ {novice, expert} module la verbosité des explications.

### Provider

Groq (OpenAI-compatible REST via `httpx`). Clé dans `backend/.env` (chargée par
`env_loader.py`, qui gère aussi le CA TLS — cf. fix mitmproxy). 7 modèles sélectionnables,
défaut `openai/gpt-oss-120b`. `_call_groq` force `response_format=json_object` +
`reasoning_effort` adapté (low pour gpt-oss, none pour qwen).

---

## 5. Graphes : modale, IA par graphe, réponse inline

Convention **universelle** (toutes les étapes) :

1. `fig_to_base64` renvoie `{img, caption, topic}` — la **caption** est extraite du titre
   matplotlib (DPI 160 → net en modale).
2. Frontend (`Plots` dans `StagePanel.jsx`) : chaque figure → vignette cliquable
   (**modale zoom** `PlotModal`) + sa légende + un bouton **`✦ IA`** (`AssistButton`).
3. Clic `✦` → `POST /stage/{id}/assist` avec `topic = "graphe: <caption>"`. La réponse
   s'affiche **inline sous le graphe** (`AssistAnswer`) **et** est ajoutée au **journal**.
4. `_assist_focus(topic, ...)` (dans `app.py`) résout les données à expliquer : bloc ciblé
   (typologie, leaderboard, table de décision…) **+** contexte (diagnostics + résultat) **+**
   journal mémoire.

> Pour qu'un graphe ait un `✦`, il suffit qu'il ait un **titre** (→ caption). Tous les
> graphes des 8 étapes en ont un, SHAP inclus.

### Rendu robuste (vues riches en graphes)

Une vue peut afficher beaucoup de figures base64 (la Transformation EDA en produit ~28).
Pour éviter le gel du renderer (décodage de tous les PNG d'un coup), `.plot-fig` porte
`content-visibility: auto` (+ `contain-intrinsic-size`) : **le navigateur saute nativement
la rastérisation des figures hors-écran** et les peint à l'approche du viewport. Les `<img>`
portent `decoding="async"` et **restent toujours dans le DOM** — une figure ne reste donc
jamais blanche (contrairement à un gate IntersectionObserver, qui ne se déclenche pas en
onglet caché / bfcache et laissait des graphes vides).

---

## 6. Routes API (`backend/app.py`)

**Robustesse & orchestration.** L'ingestion (`session_ingest.py`) enchaîne garde-taille
→ parse CSV → **validation** (`validation.py`) : un jeu dégénéré (vide, < 5 lignes, cible
mono-classe/vide) est rejeté par un **400 clair** avant toute étape ; les problèmes non
bloquants (colonnes constantes, missingness lourde, cible quasi-dégénérée, forte cardinalité,
échantillon minuscule) sont attachés à la session (`data_quality`) et remontés à l'analyste
(bannière + bouton IA). L'exécution d'une étape (`stage_runner.py`) enveloppe toute exception :
`ValueError` → 409 (précondition expliquée), autre → **422 attribué à l'étape** (jamais de 500
opaque) — ce qui rend l'`autorun` résilient (il ne gère que des `HTTPException`).

| Méthode | Route | Rôle |
|---------|-------|------|
| POST | `/api/session/start` · `/start-demo/{name}` | Crée une session (upload CSV ou jeu de démo) — validée, avec avertissements `data_quality` |
| GET | `/api/session/{id}` | Résumé de session (restauration au reload) |
| GET | `/api/session/{id}/stage/{stage}` | Vue d'étape (schema, diagnostics, plots, result) |
| POST | `/stage/{stage}/run` · `/recommend` · `/interpret` · **`/assist`** | Exécuter / affiner / interpréter / **expliquer un élément** |
| GET | `/api/session/{id}/journal` | Journal mémoire des échanges IA |
| POST | `/api/session/{id}/level` | Niveau Novice/Expert |
| POST | `/autorun` · `/predict` · GET `/download-model` | Pipeline complet / inférence / export `.pkl` |
| POST | `/api/session/{id}/monitor` | Surveillance post-déploiement : upload d'un lot → dérive (PSI/KS), dérive de concept, reproductibilité, re-calibration du seuil (`monitoring.py`, routeur `routes_monitor.py`) |
| POST | `/api/session/{id}/jitter` | Protocole jitter (stabilité des prédictions) : sans upload — bruit gaussien croissant sur le jeu de référence → courbe de taux de bascule, point de rupture, verdict. Déterministe (seed fixée) |
| POST | `/api/session/{id}/stability/{analysis}` | Analyse de stabilité avancée (`numerical` / `margin` / `churn` / `conformal` / `smoothing`) → verdict + chiffres clés + notes + figure (`stability.py`) |
| POST | `/api/agent/model` · GET `/agent-status` | Sélection du modèle Groq |

---

## 7. Frontend (`frontend/src/components/`)

| Composant | Rôle |
|-----------|------|
| `Dashboard.jsx` | État global (session, insights, level, assistAnswers), handlers, **persistance localStorage** |
| `StagePanel.jsx` | Onglets Observation / Aide IA / Réglages / Résultat ; `Plots` (figures + `✦ IA`), `ModelLeaderboard`, `OverfitControl`, **`ClassReport`** (rapport par classe), **`ClusterSummary`** (lecture clusters enrichie), `AssistAnswer` |
| `Copilot.jsx` | Panneau gauche : contexte + assistants rapides + **journal mémoire** + bascule Novice/Expert |
| `ColumnTable.jsx` | Tables de décision génériques (Nettoyage colonnes, Intégration variables) |
| `PlotModal.jsx` · `AssistButton.jsx` · `AssistAnswer.jsx` | Modale zoom · bouton `✦` · réponse IA inline |
| `ConfigControls.jsx` · `DiagnosticsView.jsx` · `ModelSelector.jsx` | Contrôles de config · diagnostics génériques · sélecteur de modèle |
| `MonitoringPanel.jsx` (+ `monitoring.css`) | Panneau Surveillance (étape Évaluation) : upload d'un lot → rapport de dérive (tableau PSI/KS, concept, reproductibilité, re-calibration) + section **jitter** (bouton de mesure, badge de verdict, courbe de tolérance) |
| `StabilityPanel.jsx` | Cartes génériques des 5 analyses de stabilité avancées (bouton Lancer → badge verdict + tableau chiffres clés + notes + figure) — rendu piloté par le contrat d'affichage du backend |

---

## 8. Pipeline supervisé (régression)

| Étape | Implémenté dans |
|-------|-----------------|
| Sélection colonnes (`colonne_a_garder`) | `clean` — table de décision `dropped_columns` |
| `qual_map` (encodage ordinal) | `clean` (`normalize_ordinals`) + `typology.encode_ordinal` |
| Valeurs distinctes catégorielles, lignes extrêmes | `clean.diagnose` |
| Analyse univariée par type | `eda_plots.univariate_plots` |
| Analyse bivariée boxplots | `eda_plots.bivariate_plots` |
| Corrélation / scatter | `integrate.diagnose` |
| Comparaison de modèles | `model` — leaderboard |
| Surapprentissage train/test/CV | `evaluate._overfit_control` |
| SHAP | `explain` |
| GridSearch | `tune` |

---

## 9. Pistes supervisée & non supervisée — déjà en place

**Deux pistes**, toutes deux couvertes par les jeux de démo (`GET /api/demo-datasets`) :

| Jeu | `problem_type` | Piste |
|-----|----------------|-------|
| `breastcancer.csv` | CLASSIFICATION (binaire) | supervisé — diagnostic bénin / malin |
| `Stars.csv` | CLASSIFICATION (multiclasse) | supervisé — type d'étoile, **6 classes** |
| `client_data.csv` | CLUSTERING | non supervisé — segmentation clients |

### 9.a Classification supervisée (binaire + multiclasse)

Le même pipeline 8 étapes traite la classification ; seules les métriques et figures de
l'évaluation diffèrent (branche `ptype != REGRESSION` dans `evaluate.run`) :

| Étape classification | Implémenté dans |
|----------------------|-----------------|
| `accuracy_score` | `evaluate` — métrique `Accuracy` |
| `precision/recall/f1` pondérés | `evaluate` — `Précision/Rappel/F1 (pondéré)` (`average="weighted"`) |
| `classification_report` (par classe) | `evaluate._per_class_report` → `diagnostics["rapport_par_classe"]` (précision/rappel/f1/support, **vrais noms de classe** via `label_encoder.inverse_transform`) → composant `ClassReport` |
| `confusion_matrix` | `evaluate._confusion_plot` (avec libellés de classe) |
| robustesse train/test/CV | `evaluate._overfit_control` (scoring `accuracy`) |

Le **multiclasse** (Stars, 6 classes) emprunte exactement le même chemin — aucun cas
particulier : `LabelEncoder` encode les 6 classes, le rapport par classe les ré-affiche en
clair. Test de bout en bout : `test_autorun_multiclass_stars`.

### 9.b Clustering non supervisé (segmentation client)

| Étape (segmentation client) | Couvert par |
|-----------------------------|-------------|
| Chargement + `describe` | `clean.diagnose` (overview, typologie) |
| Préparation `features_num` (one-hot `drop_first`, drop `client_id`) | `transform` + `integrate` (table de décision, corr inter-variables) |
| Méthode du coude (inertie vs k) | `model._inertia_curve` + `model._elbow_plot` (« Méthode du coude — choix de K ») ; `k_recommande` via `_knee_k` |
| `KMeans(k=3)` | `model._fit_clustering` (k choisi par l'expert, ou recommandé) |
| **Algorithmes au choix** | `select cluster_algo` : KMeans · **DBSCAN** (densité, gère le bruit `label -1`, aide `model._kdistance_plot`) · **Agglomératif** (hiérarchique). Silhouette robuste (sur clusters denses) côté `evaluate`. |
| Lecture en **valeurs brutes** (`groupby(cluster).mean` sur les unités réelles) | `evaluate._cluster_profiles_raw` — jointure par position de la sortie `clean` (avant scaling) aux labels ; moyennes numériques **+ modalités catégorielles majoritaires** |
| Libellés métier des clusters | `evaluate._business_labels` — **seuils bruts** : `revenu_annuel_k>65 & panier_moyen>100` → « Premium fidèle » ; `sensibilite_promo>70 & age<35` → « Digital promo » ; sinon « Famille pragmatique ». Repli générique (σ) pour un autre jeu. |
| Projection PCA 2D | `evaluate._cluster_scatter` |
| Profil des clusters | `evaluate._profile_plot` (écarts standardisés) |
| Indices de validité interne | `evaluate._evaluate_clustering` : **silhouette** + **Davies-Bouldin** (plus bas = mieux) + **Calinski-Harabasz** (plus haut = mieux), sur les clusters denses |
| Renommage métier (table de décision) | libellés auto éditables dans `ClusterSummary` → bouton « Appliquer les noms » → re-run `evaluate` avec `config.cluster_labels` (override de `_business_labels`) |

Résultat exposé : `cluster_summary` = `[{cluster, taille, label_metier, moyennes (brutes), majoritaires}]`
→ composant `ClusterSummary`. `tune` est rejeté (409) côté clustering. Tests :
`test_autorun_clustering_business_labels`, `test_clustering_elbow_in_model_view`,
`test_tune_rejected_for_clustering`, `test_clustering_agglomerative`,
`test_clustering_dbscan_handles_noise`.

### 9.c Détection d'anomalies non supervisée

`problem_type=ANOMALY` (jeu de démo `transactions.csv`, sans cible). Mêmes data-stages que le
clustering (mode unsupervised, `X_full`) ; `model` et `evaluate` spécialisés :

| Étape | Couvert par |
|-------|-------------|
| Détecteur | `model._fit_anomaly` — **Isolation Forest** (`n_estimators=200`) ou **Local Outlier Factor** ; `select anomaly_algo` + `contamination`. `predictions` (-1/1) + `scores` stockés en artefacts. |
| Taux + comptage | `evaluate._evaluate_anomaly` → `Anomalies / Normaux / Taux d'anomalies (%)`. |
| Distribution des scores | `evaluate._anomaly_score_hist` (normaux vs anomalies). |
| Carte des anomalies | `evaluate._anomaly_scatter` (PCA 2D, normaux vs anomalies). |
| Lignes les plus atypiques | `evaluate._top_anomalies` (valeurs **réelles** via sortie `clean`) → composant `AnomalySummary`. |

`tune` est rejeté (409, non supervisé). Badge UI « Détection d'anomalies ». Tests :
`test_anomaly_demo_detected`, `test_autorun_anomaly_detection`, `test_anomaly_lof_algorithm`,
`test_tune_rejected_for_anomaly`.

Tout passe par le **même contrat d'étape** : ajouter un graphe = créer une figure titrée et
la renvoyer via `fig_to_base64` → elle hérite automatiquement de la modale + de l'IA par graphe.

---

## 10. Apprentissage par renforcement (3e paradigme)

Sous-système **séparé du pipeline 8 étapes** : pas de CSV figé, mais un **agent** qui apprend
par essais-erreurs en interagissant avec un **environnement**.

| Élément | Fichier |
|---------|---------|
| Environnement | `backend/rl/gridworld.py` — `GridWorld` n×n déterministe : start, **un ou plusieurs buts** (`goals`, atteindre l'un termine), **pièges** (`traps`, pénalité + fin d'épisode), obstacles ; récompense −1/pas, +10 au but, −10 piège. État = `row*size+col`. `reset()` / `step(action) → (state, reward, done)`. |
| Algorithme | `backend/rl/qlearning.py` — Q-learning tabulaire (epsilon-greedy décroissant) : `Q[s,a] += α·(r + γ·max Q[s',·] − Q[s,a])`. `summarise()` : récompense, réussite, pas, Manhattan vers le but le plus proche. |
| Graphes | `backend/rl/plots.py` — courbe de récompense (moyenne glissante), **politique apprise** (flèche par état, BUT + pièges X visibles), **heatmap V(s)**. |
| API | `POST /api/rl/train` (`app.py`) — params bornés (taille, épisodes, α, γ, ε, **n_goals 1-3, n_traps 0-5**) ; placement déterministe (seedé) des buts/pièges. Plots sérialisés via `PLOT_LOCK`. Stateless. |
| Frontend | Onglet « Renforcement » (`App.jsx`, nav par état) → `ReinforcementView.jsx` (réglages dont **sliders buts/pièges**, légende, métriques + 3 graphes zoomables). |

Dépendances : **NumPy seul** (pas de gym ni torch). Tests : `test_gridworld_step_mechanics`,
`test_qlearning_converges`, `test_rl_train_route`, `test_rl_train_clamps_bounds`.

---

## 11. Lancer & tester

```bash
# Backend (depuis backend/) — charge backend/.env automatiquement
python -m uvicorn app:app --port 8000

# Frontend (depuis frontend/) — process_guard bloque `npm run dev`, lancer vite direct
node node_modules/vite/bin/vite.js --port 5174 --host

# Tests
cd backend && python -m pytest tests/test_api.py -q   # 44 tests
```

**Jeux de démo** (`GET /api/demo-datasets`, fichiers dans `data/` à la racine, lecture seule) :
`house_price_data.csv` (régression) · `breastcancer.csv` (classif binaire) ·
`Stars.csv` (classif multiclasse, 6 classes) · `client_data.csv` (clustering) ·
`transactions.csv` (détection d'anomalies). Le renforcement n'utilise pas de CSV
(environnement généré) — onglet « Renforcement ».

> `transactions.csv` est synthétique et **régénérable à l'identique** :
> `python data/generators/transactions.py` (seeds fixes, déterministe).

### Gotchas à connaître

- **Persistance des sessions** : chaque session est mirroir-ée en SQLite (`backend/sessions.db`,
  gitignored) et **survit à un redémarrage** du backend ; le frontend conserve le `session_id`
  en `localStorage` et le retrouve après reload. Cache mémoire pour le chemin chaud, SQLite
  pour la durabilité. Mono-processus (un backend partagé multi-process resterait à faire :
  Redis/Postgres). Désactivable via `ML_PERSIST_SESSIONS=0` (revient au tout-mémoire).
- **DPI 160** sur tous les graphes (net en modale) ; `_save_light` (SHAP) aussi.
- **TLS / mitmproxy** : `env_loader.ensure_tls_ca()` retombe sur `certifi` si le proxy est
  absent (sinon Groq casse en `CERTIFICATE_VERIFY_FAILED`).
- **Clé Groq** : `backend/.env` (gitignored). Sans clé → repli heuristique déterministe partout.
