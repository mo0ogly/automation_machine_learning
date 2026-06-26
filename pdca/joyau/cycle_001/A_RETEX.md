# PDCA cycle 1 — « le joyau » (studio d'exploitation du modèle)

**Date** : 2026-06-26 · **Périmètre** : `ExploitView.jsx` + `pipeline/scoring.py` + routes `/predict*` `/analyze` `/model-card` `/predict/batch` + personas LLM (`llm_agent.py`)
**Benchmark externe** : `prompt-injection-corpus.jsonl` (1000 segments, détection d'injection indirecte `data_to_instruction`, OWASP LLM01:2025)
**Score global** : **58 → 72 / 100** (+14)

## Méthode
- **D** — 3 agents d'audit en parallèle (correction/robustesse · sécurité/IPI · frontend/UX+tests) + harnais sécurité live (Groq) + validation du détecteur contre le corpus. *Content-filter* : payloads jamais lus dans le contexte, manipulés via harnais Python.
- **C** — consolidation scorecard par dimension.
- **A** — remédiation des findings critiques/sûrs + re-vérification + 5 tests ajoutés (57 → 62 verts).

## Finding phare — Injection de prompt indirecte (CRITIQUE, OWASP LLM01)
`/analyze` injectait les **noms de colonnes** du CSV utilisateur (`target`, `top_features`) **verbatim** dans le prompt des personas IA. Frontière `data → instruction` non gardée.
- **Preuve** : 150/150 payloads atteignaient le prompt (escaped-aware). gpt-oss-120b a *résisté* 10/10 en live — mais la défense ne reposait que sur le modèle (fragile, surtout en multi-provider).
- **Fix** : `prompt_guard.py` — normalisation NFKC, strip zero-width/contrôle, cap longueur, remplacement des libellés en forme d'injection, **enveloppe de délimiteurs** `<donnees_modele …>` avec consigne « ne pas suivre ». Câblé dans `_persona_messages` + `_persona_heuristic`.
- **Vérif post-fix** : **0/150** atteignent le prompt verbatim ; 150/150 neutralisés + enveloppés ; LLM répond toujours normalement (transparent pour l'usage légitime).
- **Validation détecteur vs corpus** : accuracy 0.57 / F1 **0.51** (= baseline keyword du README §8, 59/180 FP sur hard_negatives) → les motifs sont faibles **par design** ; la défense primaire est structurelle. *Détecteur TF-IDF entraîné (baseline corpus 0.98 F1) = durcissement cycle 2.*

## Autres correctifs appliqués
| Sév. | Finding | Fix |
|---|---|---|
| HAUTE | DoS upload (cap appliqué après parsing) | `_read_capped` — rejet > 25 Mo **avant** `pd.read_csv` (start + batch) |
| MOY. | Injection de formule CSV à l'export | `_csv_safe` préfixe `= + - @` ; gate `is_numeric_dtype` (pandas infère `str`, pas `object`) |
| CRIT. | Anomalie LOF : prédictions `None` silencieuses | message explicite « LOF ne score pas de nouveaux points » au lieu de None muet |
| HAUTE | `sensitivity` O(N) : `predict_one(base)` par point de balayage | sorti de la compréhension → 2 passes au lieu de N+1 |
| MOY. | `model_card` RMSE=0 falsy ; résumé régression tout-None → catégoriel | `is not None` ; forme régression conservée |
| MOY. | Frontend : `setTimeout` orphelin, race `revokeObjectURL`, données périmées affichées en cas d'erreur | timer tracké + cleanup, revoke différé, `setPred/setTornado(null)` sur échec |

## Backlog cycle 2 (non fait — noté honnêtement)
- **Détecteur TF-IDF char 3-5g + logreg** entraîné sur le corpus (0.98 F1) pour remplacer les motifs.
- **F-02 sécurité** : même garde IPI sur l'agent du **Pipeline** (`build_messages`/`build_assist_messages`, journal, topic/label) — hors périmètre « joyau ».
- **F-02 correction** : PCA en serving re-fit (divergence d'eigenvecteurs) → persister le `pca` d'entraînement et l'appliquer (impacte uniquement les sessions `pca=True`).
- LOF `novelty=True` pour un vrai scoring live (touche `model.py`/`evaluate.py`).
- Auth + rate-limit (aucune sur les routes) ; `model_summary` renvoyé en clair ; CORS `*`.
- Frontend : association `label/htmlFor`, bannières d'erreur explicites ; matrice de tests par paradigme complète (tornado/sensibilité/batch en classif/clustering/anomalie).

## Auto-évaluation
Objectif (baseline + remédiation criticals) : **atteint**. Zéro régression (62/62 verts). Frontière IPL fermée et vérifiée. Honnêteté maintenue (résistance LLM live signalée, détecteur faible reconnu). Commits : `783846e` (sweep utilisateur incluant le gros du PDCA) + `41861f2` (fix dtype CSV).
