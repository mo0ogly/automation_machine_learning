# Regles de programmation — AEGIS

## React (Frontend — port 5173)

1. **Pas d'emoticons** dans le code, commentaires ou strings UI — sauf si le design l'exige explicitement.
2. **Pas de placeholders** ("TODO", "coming soon") sans validation explicite du user.
3. **i18n obligatoire** : `t('key')` pour tout texte visible. JAMAIS de string hardcodee.
4. **Template literal bug** : pas de `${}` dans les fonctions standalone .jsx (utiliser concatenation).
5. **Tailwind v4** : classes utilitaires, pas de CSS custom sauf necessaire.
6. **Composants Red Team** : `frontend/src/components/redteam/` — toutes les vues du lab.
7. **Pas de librairies non approuvees** sans en parler au user.

## Go (Backend futur / outils)

1. **Pas de `fmt.Println` en production** — logger structure.
2. **Pas de chemins hardcodes** — variables d'environnement ou flags.
3. **Tests** : tout nouveau package doit avoir un `_test.go`.
4. **Pas de `panic` sauf en initialisation** — retourner des erreurs.

## Python (Backend actuel — port 8042)

1. **FastAPI** avec routes dans `backend/routes/`.
2. **Pas de `print()` en production** — utiliser `logging`.
3. **Docstrings en anglais**, commentaires FR OK pour la recherche.
4. **Type hints** sur les fonctions publiques.
5. **Pas de secrets dans le code** — `.env` (gitignore).
6. **Secrets via `backend/.env` + `backend/env_loader.py`** — source unique pour `GROQ_API_KEY` etc. `load_backend_env()` fait `os.environ.setdefault`. Tout script standalone (`run_*.py`, `benchmark_*.py`, `experiments/*.py`) DOIT importer `env_loader` en tete (sinon les cles ne sont chargees qu'en mode uvicorn).
7. **Avant de conclure qu'une cle API est absente, verifier `backend/.env`**. Les worktrees n'heritent PAS de `.env` (gitignore) → `env_loader.py` fait un walk-up vers le main tree. Lister sans exposer : `awk -F= '{print $1}' backend/.env`. Failure mode documente (SESSION-P0) : conclusion "GROQ_API_KEY manquante" apres check du shell env seul.

## General

1. **ZERO emoticon** sauf demande explicite du user.
2. **ZERO placeholder** sans validation explicite.
3. **ZERO import inutile** — nettoyer apres refactoring.
4. **ZERO fichier orphelin** — supprimer si plus utilise.
5. **Chaque fichier cree doit etre reference** quelque part.

## File size — 800 lines max

**Aucun fichier source ne doit depasser 800 lignes.** Cette regle s'applique a TOUS les types : `.py`, `.jsx`, `.js`, `.ts`, `.tsx`, `.go`, `.md` (sauf manuscrit these), `.json` (sauf datasets), `.yaml`.

**Why:** Les fichiers > 800 lignes deviennent illisibles, casse-tete a maintenir, impossibles a auditer en revue de code, et violent la regle "ne JAMAIS lire" du content filter (un fichier de 3616 lignes a forcement du contenu sensible quelque part). Les agents Claude (orchestrator + subagents) consomment beaucoup de contexte pour les lire, ce qui sature la fenetre.

**How to apply:**
- Quand un fichier approche 700 lignes : commencer a planifier sa decomposition
- Quand il atteint 800 : decomposer OBLIGATOIRE en modules logiques
- Decomposition par responsabilite, pas par ligne arbitraire (un module = une responsabilite)
- Pour les .jsx/.tsx : extraire les sub-components, hooks customs, constants, types
- Pour les .py : extraire les classes, fonctions utilitaires, schemas
- Pour les .md : decomposer par section avec un index a la racine
- **Exceptions autorisees** :
  - Fichiers generes automatiquement (lockfiles, dist/, build/)
  - Datasets JSON (chroma_db dumps)
  - Manuscrit de these (`research_archive/manuscript/`) — exception explicite
- Un hook `.claude/hooks/file_size_check.cjs` enforce la regle au moment de l'edit (PreToolUse Edit/Write)

**Refactoring existant :**
- `frontend/src/components/redteam/ScenarioHelpModal.jsx` : DONE — decompose en 7 modules `helpData/` (thesis/agentic/rag/advanced/chains/solo/campaigns) + barrel `index.js`. Composant = 164 lignes, max chunk = 690 lignes.
- Verifier periodiquement : `find . -name '*.jsx' -o -name '*.py' | xargs wc -l | sort -rn | head -20`
