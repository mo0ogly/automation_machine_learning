# Recette PDCA-C — automation_machine_learning

Catalogue des 65 checks du mode `/apex -rc`, adapte a CE depot (frontend React/Vite
port 5173, backend FastAPI port 8000, venv `.venv`). Remplace les catalogues
poc_medical/LIA-SEC du SKILL.md quand la tache courante concerne ce projet.

## Pre-flight (BLOQUANT)

```bash
# Backend deja lance ? (serveur de l'utilisateur : REUTILISER, jamais doubler — regle ports fixes)
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/docs
# -> 200 = reutiliser | connexion refusee = demarrer via .venv

# Syntaxe backend (toujours via le venv du projet)
.venv/Scripts/python.exe -m py_compile backend/app.py

# Build frontend
cd frontend && npm run build   # -> "built in" attendu
```

Si le backend qui tourne date d'avant les modifications backend de la session :
valider les changements EN PROCESS (`python -c "import app; app.rl_train(...)"`)
plutot que de redemarrer le serveur de l'utilisateur sans son accord.

## Agents et modeles

Memes 6 agents paralleles que le SKILL.md (model: haiku, aggregation: sonnet),
memes regles de Swarm Context Sheet. Seuls les catalogues ci-dessous changent.

---

## C.1 Build & Compile (10 checks, poids 15 %)

| ID | Check |
|----|-------|
| C-01 | `npm run build` (frontend/) termine avec "built in", zero erreur |
| C-02 | Aucune ligne "error"/"Error" dans la sortie de build |
| C-03 | `npm run test` (vitest) : tous les tests verts |
| C-04 | `py_compile` sur tous les `.py` de backend/ (depth 1) — 0 erreur |
| C-05 | `.venv` python : `import app` (sys.path backend/) — exit 0 |
| C-06 | Aucun template literal `${}` dans les `.jsx` (regle projet) |
| C-07 | Aucun `console.log()` dans les `.jsx` (hors commentaires) |
| C-08 | "localhost" en dur uniquement via l'idiome `VITE_API_URL \|\| 'http://localhost:8000'` |
| C-09 | Aucun fichier source > 800 lignes (hors lockfiles, dist/, datasets) |
| C-10 | `npm run lint` (oxlint) : zero erreur (les warnings preexistants sont budgetes) |

## C.2 API Consistency (10 checks, poids 20 %) — port 8000

| ID | Check |
|----|-------|
| C-11 | `GET /api/datasets` -> 200, liste non vide |
| C-12 | `POST /api/rl/train` -> contrat complet : `metrics`, `plots` (3), `policy`, `config.rewards`, `env` |
| C-13 | Clamps serveur : size hors [3,10], episodes hors [20,2000] -> valeurs bornees, pas d'erreur |
| C-14 | `POST /api/rl/explain` avec param inconnu -> 404 |
| C-15 | `policy` : longueur == size², actions dans {0,1,2,3} |
| C-16 | `env.obstacles`/`env.traps` renvoyes == envoyes (apres `_clean_cells`) |
| C-17 | Cycle session : create -> stages -> predict (smoke) |
| C-18 | Aucun endpoint 501/stub dans app.py + routes_* |
| C-19 | `GET /api/models` (leaderboard) -> 200 |
| C-20 | Aucune donnee mockee/hardcodee dans les routes GET qui retournent des listes |

## C.3 Frontend Quality (10 checks, poids 15 %)

| ID | Check |
|----|-------|
| C-21 | Vue Renforcement : structure ARIA `grid > row > gridcell` valide |
| C-22 | Roving tabindex : un seul `tabIndex=0` dans la grille a tout instant |
| C-23 | Bandeau "Configuration modifiee" des qu'on edite apres un entrainement (stale) |
| C-24 | Legende synchronisee a `config.rewards` de l'API (fallback = defauts backend) |
| C-25 | Pas de piege fantome apres gommage (test dedie vert) |
| C-26 | "Rejouer la trajectoire" visible apres entrainement, masque si stale |
| C-27 | Textes UI en francais coherents dans chaque vue |
| C-28 | Bundle principal < 2 MB hors Monaco (PromptsPanel reste code-split) |
| C-29 | Aucun import manquant dans les `.jsx` modifies (git diff HEAD~3) |
| C-30 | Toutes les classes CSS referencees dans les `.jsx` sont definies (pas d'orphelines) |

## C.4 Security (10 checks, poids 25 %)

| ID | Check |
|----|-------|
| C-31 | Aucun pattern d'injection SQL dans les `.py` |
| C-32 | Aucun `eval()`/`exec()` sur input non valide |
| C-33 | Aucun `pickle.loads()` sans controle de source |
| C-34 | Aucun secret hardcode (`api_key`, `password`, `secret`) hors tests |
| C-35 | Cap d'upload (`MAX_UPLOAD_BYTES`, 25 Mo) actif AVANT le parsing pandas |
| C-36 | CORS pas en `*` sans restriction (ou explicitement documente dev-only) |
| C-37 | Aucun `subprocess`/`os.system()` avec input utilisateur non assaini |
| C-38 | `prompt_guard` actif sur les routes IA |
| C-39 | Hook `.claude/hooks/process_guard.sh` present et aligne ports 5173/8000 |
| C-40 | `backend/.env` en .gitignore et non tracke |

## C.5 ML-Specific (15 checks, poids 15 %)

| ID | Check |
|----|-------|
| C-41 | RL : preset Labyrinthe — chemin S -> BUT franchissable (BFS) |
| C-42 | RL : preset Decouverte (300 ep) -> taux de reussite final >= 80 % |
| C-43 | RL : "Chemin optimal (Manhattan)" == min Manhattan S -> buts |
| C-44 | RL : rollout glouton de `policy` atteint un but sur monde vide entraine |
| C-45 | Pipeline : registre STAGES complet, chaque stage a ses metadonnees |
| C-46 | Dataset cards : chaque CSV de data/ a une carte |
| C-47 | Leaderboard : scores dans des bornes coherentes (0..1 ou %) |
| C-48 | Evaluation operationnelle SOC branchee (routes + panneau) |
| C-49 | Prompts IA editables (panneau Prompts) — zero prompt hardcode (prompt-governance) |
| C-50 | "Localiser" fonctionnel : `data-prompt-loc` presents sur les elements cibles |
| C-51 | `/api/rl/explain` renvoie `explanation` + `suggested_config` applicable en 1 clic |
| C-52 | `to_native` : NaN/inf -> null (JSON toujours valide) |
| C-53 | Plots RL : 3 figures avec captions (courbe, politique, valeur) |
| C-54 | `sessions.db*` (WAL/SHM) non commites |
| C-55 | `pytest backend/tests -k rl` vert |

## C.6 Code Quality (10 checks, poids 10 %)

| ID | Check |
|----|-------|
| C-56 | Aucun id duplique dans les registres (datasets, stages, modeles) |
| C-57 | `pytest backend/tests` complet vert |
| C-58 | Zero TODO/placeholder dans le code livre |
| C-59 | Zero emoticone (glyphes fonctionnels S/BUT/X/⤢/● toleres) |
| C-60 | Docstrings sur les fonctions publiques backend |
| C-61 | README.md + README.fr.md a jour apres changement de feature |
| C-62 | docs/ARCHITECTURE.md a jour |
| C-63 | `git status` : aucun `.env`/credentials dans les untracked |
| C-64 | Aucun fichier orphelin (CSS/JSX cree mais jamais importe) |
| C-65 | Commits : `type(scope): sujet`, PAS de trailer Co-Authored-By (regle user) |

---

## Scorecard

Memes ponderations et verdicts que le SKILL.md :
C.1 15 % · C.2 20 % · C.3 15 % · C.4 25 % · C.5 15 % · C.6 10 %.
PASS >= 70 · CONDITIONAL 50-69 · FAIL < 50.

**Bloquants PR** : C-01, C-04, C-06, C-12, C-18, C-31, C-34, C-35, C-40, C-42, C-56, C-57.

Sauvegarde : `pdca/{task-id}/C_SCORECARD.json` + `.md` (identique au SKILL.md).
