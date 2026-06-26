---
name: apex
description: Methodologie structuree APEX (Analyze-Plan-Execute-eXamine) pour implementer des features de facon systematique avec 10 etapes autonomes, validation, review adversariale, tests, et creation de PR. Mode Integration (-i) pour porter du code externe avec tracker exhaustif, diagrammes Mermaid, recovery session, et suivi element par element. Utiliser quand une tache necessite plus de 2 etapes, touche plusieurs fichiers, presente des risques, ou integre du code externe. Se declenche sur "apex", "plan d'attaque", "implemente cette feature", "workflow structure", "integre ce repo", "porte ce code".
---

# APEX - Analyze, Plan, Execute, eXamine

Pipeline systematique en 10 etapes pour toute tache non-triviale dans LIA-SEC.
Inspire de Codelynx APEX, Explore-Plan-Execute (Upsun), Everything-Claude-Code, et Trail of Bits.

### Model Policy

| Agent / Etape | Model | Justification |
|---|---|---|
| ETAPE 01 (ANALYZE) — Explore agent | **haiku** | Lecture seule, Glob/Grep/Read |
| ETAPE 05 (EXAMINE) — review adversariale | **sonnet** | Analyse critique, patterns OWASP |
| Mode `-rc` — 6 agents recette (C-01 a C-65) | **haiku** | Verifications simples (grep, curl, comptages) |
| Mode `-rc` — aggregation scorecard | **sonnet** | Consolidation, calcul de scores |
| Subagents custom (cve-research, recipe-tester) | **sonnet** | Taches standards de code/recherche |

## Syntaxe

```
/apex [flags] <description de la tache>
```

## Flags

| Flag | Description |
|------|-------------|
| `-a` / `--auto` | Skip confirmations, auto-approve plans |
| `-x` / `--examine` | Active la review adversariale (etape 05) |
| `-s` / `--save` | Sauvegarde chaque etape dans `.claude/output/apex/` |
| `-t` / `--test` | Inclut creation + execution de tests (etapes 07-08) |
| `-b` / `--branch` | Verifie qu'on n'est pas sur main, cree une branche si besoin |
| `-pr` / `--pull-request` | Cree une PR a la fin (active -b automatiquement) |
| `-e` / `--economy` | Pas de subagents, economise les tokens |
| `-r <id>` / `--resume <id>` | Reprend depuis une tache precedente |
| `-i` / `--integrate` | Mode Integration : tracker exhaustif, inventaire source, Mermaid, recovery session |
| `-rc` / `--recette` | Mode Recette : remplace ETAPE 04 (Validate) par le cycle PDCA-C complet (65 checks, swarm 6 agents, scorecard /100) |

**Par defaut (sans flags) :** confirmation a chaque etape, pas de tests, pas de PR.

## Les 10 etapes

### ETAPE 00 : INIT
- Parser les flags et la description
- Creer le dossier output si `-s` (`_alire/temp/apex/{task-id}/`)
- Verifier l'etat git (branche, uncommitted changes)
- Si `-b` : verifier qu'on n'est pas sur main/master, creer branche `feat/{task-slug}`

### ETAPE 00b : PRE-FLIGHT CHECK (BLOQUANT)

> **Note : APEX couvre deux projets distincts avec des ports differents.**
> - **LIA-SEC** (Go backend + sigma-react-frontend) : port **8081**, build via `build_secure_lia.sh`
> - **poc_medical / AEGIS** (Python/FastAPI backend + React frontend/) : port **8042**, build via `npm run build`
> Le pre-flight ci-dessous cible LIA-SEC. Le mode `-rc` a son propre pre-flight cible poc_medical (port 8042).
> Adapter selon le projet de la tache courante.

Avant toute analyse, verifier que l'environnement est operationnel :

```bash
# --- LIA-SEC (port 8081, Go backend) ---
curl -s -o /dev/null -w "%{http_code}" http://localhost:8081/api/health
# -> 200 = OK | autre = STOP, fixer d'abord

# PostgreSQL (LIA-SEC)
psql -U lia_admin -d lia_scan -c "SELECT 1" 2>/dev/null
# -> OK | FAIL = STOP, auth/service a fixer

# Frontend build LIA-SEC (si tache frontend)
cd sigma-react-frontend && node node_modules/.bin/vite build 2>&1 | tail -1
# -> "built in" = OK | erreurs = STOP, fixer d'abord

# Go build LIA-SEC (si tache backend)
bash cmd/sigma_web/build_secure_lia.sh 2>&1 | grep "Build réussi"
# -> OK | FAIL = STOP, fixer d'abord

# --- poc_medical / AEGIS (port 8042, Python backend) ---
# Si la tache courante concerne poc_medical, utiliser a la place :
# curl -s -o /dev/null -w "%{http_code}" http://localhost:8042/api/redteam/scenarios
# python -m py_compile backend/server.py
# cd frontend && npm run build 2>&1 | tail -1
```

**Si un pre-flight echoue :**
1. Informer l'utilisateur du blocage
2. Proposer de fixer le pre-requis d'abord
3. NE PAS continuer sur une base cassee (le smoke test final echouera de toute facon)

**Exception :** si la tache EST de fixer le pre-requis qui echoue, continuer.

### ETAPE 01 : ANALYZE (comprendre, pas coder)

Exploration pure du code existant. ZERO ligne de code produite.

1. **Lire les fichiers concernes** : Glob + Grep + Read
2. **Cartographier les dependances** : qui appelle quoi, imports, routes API
3. **Triage d'usage (OBLIGATOIRE pour fichiers existants)** :
   ```bash
   # Pour chaque symbole public du fichier (fonctions, types, constantes) :
   # Go — chercher dans tous les .go
   grep -rn "SymbolName" *.go | grep -v le_fichier_lui_meme.go

   # Pour projets hybrides Go+Python+React : etendre la recherche cross-language
   # (une fonction Go peut etre appelee via route API depuis JSX ou Python)
   grep -rn "SymbolName\|/api/route-correspondante" --include="*.go" --include="*.py" --include="*.jsx" --include="*.tsx" .

   # 0 resultats = DEAD CODE -> proposer .disabled, NE PAS corriger
   # N resultats = ACTIF -> corriger/activer
   ```
   Classer chaque fichier : **ACTIF** (appele) / **DEAD** (0 appels) / **PROTOTYPE** (code propre, routes commentees)
   Presenter le triage a l'utilisateur AVANT d'investir du temps a corriger du dead code.
4. **Identifier les patterns existants** : conventions, nommage, architecture en place
5. **Consulter la documentation** : `_alire/01_DOCUMENTATION/`, CLAUDE.md, skills
6. **Verifier les contraintes LIA-SEC** : MUI v7, ConfigurationService, fetchWithConfig, logger custom, R1-R10

Output (si `-s`) : `01-analyze.md`
```
FICHIERS CONCERNES : [liste avec lignes]
DEPENDANCES : [qui appelle quoi]
PATTERNS EXISTANTS : [conventions detectees]
CONTRAINTES : [MUI v7, logger, fetchWithConfig, etc.]
RISQUES : [ce qui peut casser]
```

Gate : presenter l'analyse a l'utilisateur. Attendre validation sauf si `-a`.

### ETAPE 02 : PLAN (architecturer avant d'implementer)

Strategie fichier par fichier avec ordre d'implementation.

1. **Decomposer en etapes atomiques** : 1 etape = 1 fichier ou 1 fonction
2. **Ordonner par dependance** : ce qui doit exister avant le reste
3. **Identifier les gates entre etapes** : compilation, tests, validation
4. **Estimer le blast radius** : fichiers impactes, routes, composants
5. **Definir le rollback** : comment revenir en arriere
6. **Budget de taille par fichier (BLOQUANT)** : pour CHAQUE fichier que le plan
   va creer ou agrandir, estimer son nombre de lignes final. Si l'estimation
   depasse 600 lignes, le plan DOIT prevoir une decomposition modulaire DES LE
   DEPART (package + modules par responsabilite), jamais un fichier monolithe a
   decouper apres coup. Regle absolue : aucun fichier source `.py/.js/.jsx/.ts/.tsx/.go/.md`
   ne depasse 800 lignes (cf. `.claude/rules/programming.md`). Conception modulaire
   = decision de la phase PLAN, pas une dette de refactoring post-implementation.
   Le plan liste explicitement, pour chaque fichier > 600 lignes anticipees, les
   modules cibles et leur responsabilite unique.

Format du plan :
```
ETAPE 1 : [action] -> [fichier:ligne] -> [gate: go build / npm run build / validate_rules_ALL.sh]
ETAPE 2 : [action] -> [fichier:ligne] -> [gate: ...]
...
ROLLBACK : git stash / git checkout -- [fichiers]
CRITERES DE SUCCES : [quand c'est "done"]
```

Technique avancee : demander a un subagent de critiquer le plan comme s'il etait ecrit par quelqu'un d'autre (pattern "adversarial review du plan").

Output (si `-s`) : `02-plan.md`

Gate : presenter le plan a l'utilisateur. Attendre validation sauf si `-a`.

### ETAPE 03 : EXECUTE (implementer avec discipline)

Implementation guidee par le plan. Chaque changement est tracke.

Regles :
1. **1 etape a la fois** : pas de multi-fichier sans validation
2. **Gate apres chaque etape** : compilation, lint, tests unitaires
3. **Pas de drift** : si un probleme emerge, revenir au PLAN, pas improviser. Si 2+ etapes echouent consecutivement, INVOQUER `/replan` (boucle OBSERVE -> COMPARE -> DECIDE -> AJUSTE) au lieu de replanifier implicitement. La replanification produit un nouveau `PLAN_*_REPLAN_*.md` dans `_alire/tracking/`.
3b. **Garde-fou taille fichier (BLOQUANT)** : apres chaque etape qui cree ou
   agrandit un fichier, verifier `wc -l`. Si un fichier atteint 700 lignes,
   STOPPER, revenir au PLAN et le decomposer en modules AVANT de continuer.
   Ne JAMAIS laisser un fichier franchir 800 lignes. Ne JAMAIS contourner le
   hook `file_size_check.cjs` via heredoc, `python -c`, ou ecriture binaire :
   le contournement produit des fichiers monolithes non audites (incident
   reference : `run_g058_campaign.py` derive a 966 lignes faute de ce garde-fou).
4. **Logger les decisions** : ecrire dans `_alire/02_LOGS/Journals/decision_log.jsonl` pour chaque choix d'architecture ou replanification (format JSONL, voir `.claude/rules/agentic-traceability.md`)

   Format journal d'action obligatoire par entree :
   ```jsonl
   {"ts":"{YYYY-MM-DDTHH:MM:SS}","phase":"EXECUTE","step":N,"action":"{verbe}","file":"{fichier:ligne}","decision":"{pourquoi}","gate":"{PASS|FAIL|N/A}","status":"{success|partial|failure}"}
   ```

5. **Silent Drift Detection (a chaque gate)** : verifier que l'objectif de la session
   n'a pas derive par rapport a la description originale de `/apex`.
   Si une suite de corrections corrige des problemes non demandes ou eloigne de l'objectif initial :
   STOP → signaler le drift → reprendre depuis le PLAN.
   Logger `"drift_detected": true` dans decision_log.jsonl si applicable.
5. **Conventions LIA-SEC strictes** :
   - Go : `logger.LogSystemEvent()`, pas `fmt.Println()`
   - React : `fetchWithConfig()`, pas `fetch()` brut
   - MUI v7 : `<Grid size={{ xs: 12 }}>`, pas `<Grid item xs={12}>`
   - ConfigurationService : `getBackendUrl()`, pas `http://localhost:8081`
   - Zero emoji, zero TODO, zero placeholder, zero mock
6. **Policy gates (BLOQUANT, verifier AVANT d'ecrire du code)** :
   - **NO STUB** : JAMAIS creer de fichiers `*_stubs.go` ou handlers retournant 501/placeholder. Si une dependance manque, l'implementer reellement ou informer l'utilisateur.
   - **NO MOCK** : JAMAIS de donnees fictives, hardcodees ou inventees
   - **USAGE** : chaque fonction/type cree DOIT etre appele quelque part. Si on renomme une fonction, verifier que le nouveau nom est utilise -- sinon c'est du dead code deplace.
   - **NO DISABLE** : JAMAIS ajouter `//go:build ignore`, renommer en `.disabled`, ou commenter tout un fichier sans accord explicite

Gates obligatoires selon le contexte :
| Contexte | Gate |
|----------|------|
| Go backend | `go build ./cmd/sigma_web/` + `go vet` |
| React frontend | `npm run build` (zero TS errors) |
| Regles LIA | `validate_rules_ALL.sh` (145 checks) |
| ReportRule JSON | `validate_reportrules.sh` (8 checks) |
| Moteur | `bin/lia_scan_engine -multi -rules . -events test_data.json` |

Output (si `-s`) : `03-execute.md`

### VERIFICATION GATE (BLOQUANT)

Apres chaque modification de code, AVANT de declarer "termine" :

1. **BUILD GATE** : `bash cmd/sigma_web/build_secure_lia.sh` (Go) + `cd sigma-react-frontend && node node_modules/.bin/vite build` (React)
2. **TEST GATE** : `cd sigma-react-frontend && npx vitest run` (tests existants ne cassent pas)
3. **IMPORT GATE** : Verifier imports manquants (alpha, useTheme, fetchWithConfig, customLogger)
4. **REGRESSION GATE** : Le code modifie ne doit pas introduire de nouveaux bugs
5. **SMOKE TEST** : Verifier que les endpoints/pages fonctionnent

Si une gate echoue : STOP, corriger, re-gate. JAMAIS declarer "termine" sans les 5 gates vertes.
Incident de reference : 188 fichiers casses par imports manquants (2026-03-17).

**Re-verification apres agents :** Si un subagent (cve-research-agent, recipe-tester-agent, etc.) modifie des fichiers pendant l'execution, re-executer les 5 gates AVANT de continuer. Les agents ne verifient pas les builds.

### ETAPE 04 : VALIDATE (auto-verification)

Verification automatique de la qualite :

1. **Diff complet** : `git diff` -- relire TOUT ce qui a change
2. **Anti-patterns LIA-SEC** :
   - R4 : pas de mock, placeholder, donnees fictives
   - R6 : logger custom uniquement (pas console.log, fmt.Println)
   - R10 : zero emoji
   - fetch() brut interdit (fetchWithConfig obligatoire)
   - localhost hardcode interdit (ConfigurationService)
3. **Compilation/build** : tout doit passer
4. **Securite OWASP** : SQL injection, XSS, command injection, path traversal

Output (si `-s`) : `04-validate.md`

### ETAPE 05 : EXAMINE (review adversariale, optionnelle avec `-x`)

Review critique comme si le code etait ecrit par quelqu'un d'autre :

1. **Analyse critique** : qu'est-ce qui pourrait mal tourner en production ?
2. **Review securite** : OWASP top 10, inputs non valides, injection
3. **Review performance** : N+1 queries, boucles couteuses, pagination manquante
4. **Review maintenabilite** : SRP, DRY, nommage, complexite
5. **Verdict** : PASS / ISSUES_FOUND (avec liste)

Si ISSUES_FOUND -> passer a l'etape 06 (Resolve).

Output (si `-s`) : `05-examine.md`

### ETAPE 06 : RESOLVE (corriger les issues, si etape 05 en a trouve)

1. Corriger chaque issue identifiee par l'Examine
2. Re-valider (retour a l'etape 04)
3. Documenter les corrections

Output (si `-s`) : `06-resolve.md`

### ETAPE 07 : TESTS (creation de tests, optionnelle avec `-t`)

1. **Analyser** les tests existants pour le code modifie
2. **Creer** les tests manquants :
   - Go : `*_test.go` dans le meme package
   - React : `*.test.tsx` a cote du composant
   - Regles : `test_data.json` (14+ cas, ratio 60/40 vuln/safe)
3. **Verifier** que les tests echouent AVANT l'implementation (TDD si applicable)

Output (si `-s`) : `07-tests.md`

### ETAPE 08 : RUN TESTS (execution, optionnelle avec `-t`)

1. Executer tous les tests concernes
2. Si echec : corriger et re-executer (boucle jusqu'a vert)
3. Verifier la couverture

Output (si `-s`) : `08-run-tests.md`

### ETAPE 09 : FINISH (finalisation)

1. **Tracking** : mettre a jour le plan persistant `_alire/tracking/PLAN_*.md` avec le format :
   ```
   Status: TERMINE
   Date fin: YYYY-MM-DD HH:MM
   Score PDCA: XX/100 (si -rc) | N/A (sinon)
   Gates: BUILD [OK|FAIL] | TEST [OK|FAIL] | IMPORT [OK|FAIL] | REGRESSION [OK|FAIL] | SMOKE [OK|FAIL]
   ```
   Cocher toutes les etapes du plan. Remplir le champ Resultat par etape.
   Si pas de plan persistant : en creer un retroactivement avec `PLAN_TEMPLATE.md`.

2. **Evolutions** (Bloc 9 CLAUDE.md) :
   - Quick win (5 min)
   - Amelioration notable (30min-2h)
   - Refactor significatif (demi-journee+)

3. Si `-pr` : creer la Pull Request avec `gh pr create`
4. Si `-b` sans `-pr` : informer de la branche prete

5. **Scoring Report de session** (obligatoire, produit dans tous les modes) :

```
== APEX SESSION REPORT — {task-id} — {date} ==

Objectif   : {description originale de /apex}
Statut     : ACHIEVED | PARTIALLY_ACHIEVED | FAILED
Duree      : {HH:MM}

Etapes     :
  00 INIT        : OK
  00b PRE-FLIGHT : OK | SKIP (tache = fix du pre-requis)
  01 ANALYZE     : OK | SKIP
  02 PLAN        : OK | SKIP
  03 EXECUTE     : OK | REPLAN x{N}
  04 VALIDATE    : OK | FAIL + corrections
  05 EXAMINE     : OK | SKIP (pas de -x)
  06 RESOLVE     : OK | SKIP (pas d'issues)
  07 TESTS       : OK | SKIP (pas de -t)
  08 RUN TESTS   : OK | SKIP (pas de -t)
  09 FINISH      : OK

Gates      :
  BUILD        : PASS | FAIL
  TEST         : PASS | FAIL | SKIP
  IMPORT       : PASS | FAIL
  REGRESSION   : PASS | FAIL
  SMOKE        : PASS | FAIL

Drift      : NONE | DETECTED a etape {N} — {description et correction}
Policy gates:
  NO STUB    : OK | VIOLATION {fichier}
  NO MOCK    : OK | VIOLATION {fichier}
  USAGE      : OK | VIOLATION {symbole}
  NO DISABLE : OK | EXCEPTION BATCH (accord utilisateur)

Score PDCA : {XX/100 si -rc | N/A}
Open items : {liste ou "aucun"}

Auto-evaluation :
  Objectif atteint       : 1/1 ou 0/1
  Zero regression        : 1/1 ou 0/1
  Policy gates respectees: 1/1 ou 0/1
  Journal complet        : 1/1 ou 0/1
  Drift detecte/corrige  : 1/1 ou 0/1
  Total                  : {N}/5
```

Output (si `-s`) : `09-finish.md`

## Mode Resume

```
/apex -r <task-id>
```

1. Localiser le dossier dans `_alire/temp/apex/`
2. Lire `00-context.md` pour restaurer la tache, les flags, les criteres
3. Scanner les fichiers d'etapes existants pour determiner la derniere etape completee
4. Reprendre a l'etape suivante

## Mode Economy (`-e`)

Pas de subagents, tout se fait dans le contexte principal. Pour les plans limites en tokens.

## Mode Light (taches simples, 1-2 fichiers)

```
A: "Je modifie X dans Y, dependance Z"
P: "Etape 1: ..., Gate: compilation"
E: [code]
X: "Diff OK, anti-patterns OK, compile OK"
```

## Mode Batch (audit multi-fichiers)

Quand la tache concerne N fichiers a auditer/corriger (ex: "14 fichiers exclus du build") :

```
/apex --batch <description>
```

**Phase 1 : TRIAGE RAPIDE (5 sec/fichier)**

Pour chaque fichier, grep les symboles publics et compter les appels externes :
```bash
# Extraire fonctions/types publics du fichier
grep "^func \|^type " fichier.go | awk '{print $2}' | cut -d'(' -f1

# Pour chaque symbole, chercher les appels hors du fichier
grep -rn "SymbolName" *.go | grep -v fichier.go | wc -l
```

Classer chaque fichier :
| Categorie | Critere | Action |
|-----------|---------|--------|
| **ACTIF** | Symboles appeles ailleurs | Corriger/activer |
| **PROTOTYPE** | Code propre, routes commentees, 0 appels | Proposer activation ou disable |
| **DEAD** | 0 appels, code obsolete (ex: SQLite dans projet PostgreSQL) | Proposer .disabled |

Presenter le tableau de triage a l'utilisateur. Attendre validation.

**Phase 2 : ACTION (seulement sur ACTIF + PROTOTYPE approuves)**

Appliquer APEX Light sur chaque fichier ACTIF. Ne pas toucher aux DEAD.

**Phase 3 : CLEANUP (DEAD + PROTOTYPE refuses)**

> **Note : le mode Batch est la seule exception a la policy NO DISABLE.**
> La policy NO DISABLE interdit de renommer en `.disabled` dans ETAPE 03 sans accord explicite.
> En mode Batch, le triage est presente a l'utilisateur (Phase 1) et sa validation constitue l'accord explicite.
> JAMAIS renommer en `.disabled` directement en ETAPE 03 standard sans passer par le triage Batch.

En batch, apres validation du triage par l'utilisateur :
1. `cp fichier.go fichier.go.disabled` (backup — l'accord est acquis via le triage valide)
2. Retirer de `build_secure_lia.sh`
3. Build gate
4. Commit unique pour tout le batch cleanup

**Avantage** : evite d'investir du temps a corriger du code que personne n'appelle.
RETEX 2026-03-18 : 14 fichiers audites, 10 etaient dead code. Sans triage, l'agent a corrige les 14 (stubs + renommages inutiles).

## Mode Integration (`--integrate` / `-i`)

Quand la tache consiste a integrer du code provenant d'un repo externe (lib open-source, paper academique, PoC GitHub, etc.) dans le projet existant.

```
/apex -i <description> --source <repo_url_ou_path>
```

Ce mode ajoute des etapes specifiques et des gardes anti-oubli pour les integrations complexes.

### Principes fondamentaux

1. **LIRE AVANT DE CODER** : INTERDICTION absolue de commencer a ecrire du code tant que TOUS les fichiers du repo source n'ont pas ete lus et compris. Chaque fichier doit etre lu avec `Read`, pas survole.
2. **Ne pas reinventer la roue** : reprendre la logique exacte du repo source, mais la moderniser et l'adapter au contexte du projet cible.
3. **Tracking exhaustif** : chaque element (fonction, classe, template, constante) est suivi individuellement dans un fichier tracker. ZERO element zappe.
4. **Renommage systematique** : sauf instruction contraire, NE PAS utiliser le nom du repo source dans les noms de fichiers, modules, classes ou variables. Reference uniquement dans le tracker et le README.

### ETAPE 00i : Swarm Context Sheet (si 2+ agents en parallele)

En mode integration (`-i`), si la tache implique 2+ agents paralleles, generer un `SWARM_CONTEXT.md` (meme format que 04-RC.0b) dans le dossier de la tache. Adapter la section "Agents actifs" aux agents du mode integration. Chaque agent lit le fichier au demarrage et met a jour sa ligne en finissant.

### ETAPE 01i : INVENTAIRE SOURCE (BLOQUANT — avant ANALYZE)

Avant toute analyse, creer l'inventaire exhaustif du repo source :

1. **Lire CHAQUE fichier** du repo source (pas juste le README)
2. **Cataloguer** chaque element portable :

```markdown
## INVENTAIRE SOURCE — [nom du repo]

### Fonctions
| # | Fonction | Fichier source | Signature | Description | Portable ? |
|---|----------|----------------|-----------|-------------|------------|

### Classes / Dataclasses
| # | Classe | Fichier source | Attributs | Description | Portable ? |
|---|--------|----------------|-----------|-------------|------------|

### Templates / Constantes
| # | Nom | Fichier source | Valeur/Contenu | Description | Portable ? |
|---|-----|----------------|----------------|-------------|------------|

### Dependencies
| # | Package | Version source | Equivalent cible | Notes |
|---|---------|----------------|------------------|-------|
```

3. **Identifier les patterns obsoletes** : API deprecees, versions anciennes, hardcodes, anti-patterns
4. **Presenter l'inventaire** a l'utilisateur. Attendre validation.

Gate : ZERO code avant validation de l'inventaire complet.

### ETAPE 02i : INTEGRATION TRACKER (fichier persistant)

Creer un fichier `docs/INTEGRATION_TRACKER.md` qui sert de :
- **Registre d'etat** de chaque element a porter
- **Recovery point** si la session tombe
- **Preuve de completude** (rien n'est zappe)

Structure obligatoire du tracker :

```markdown
# INTEGRATION TRACKER — [Description]

> **Source** : [reference academique / URL repo]
> **Cible** : [projet cible]
> **Date de creation** : YYYY-MM-DD
> **Derniere MAJ** : YYYY-MM-DD

## LEGENDE STATUTS
| Icone | Statut |
|-------|--------|
| `[ ]` | TODO |
| `[~]` | EN COURS |
| `[x]` | FAIT |
| `[!]` | BLOQUE |

## A. ELEMENTS A PORTER

### A1. [Categorie 1] (ex: Data Structures)
| # | Source | Fichier source | Cible | Fichier cible | Statut | Date creation | Date MAJ | Amelioration vs source |
|---|--------|----------------|-------|---------------|--------|---------------|----------|----------------------|

### A2. [Categorie 2] (ex: Fonctions core)
| # | Source | Fichier source | Cible | Fichier cible | Statut | Date creation | Date MAJ | Amelioration vs source |
|---|--------|----------------|-------|---------------|--------|---------------|----------|----------------------|

[... autant de categories que necessaire ...]

## B. ORDRE D'EXECUTION (DEPENDANCES)
[DAG des dependances entre phases]

## C. MAPPING FICHIERS SOURCE -> CIBLE
[Table de correspondance complete]

## D. AMELIORATIONS vs SOURCE ORIGINALE
[Table justifiant chaque modernisation]

## E. SESSION RECOVERY
**Derniere etape completee** : [etape]
**Prochaine etape** : [etape]
**Commande de reprise** : "Continue l'integration depuis le tracker docs/INTEGRATION_TRACKER.md"
```

**Regles du tracker** :
- **MAJ apres chaque element termine** : passer `[ ]` -> `[x]`, remplir Date creation + Date MAJ
- **MAJ de la section E (Recovery)** apres chaque phase completee
- La colonne "Amelioration vs source" est OBLIGATOIRE : documenter ce qui a ete modernise
- Le tracker est le **single source of truth** — si le tracker dit `[ ]`, c'est pas fait

### ETAPE 02ii : DIAGRAMMES MERMAID (script Python)

Creer un script Python `docs/{nom}_architecture.py` qui genere les diagrammes Mermaid :

1. **Architecture globale** : comment le code integre s'articule avec l'existant
2. **Flux d'execution** : step-by-step du process porte
3. **Composantes** : les elements portes et leurs variantes
4. **Integration** : le nouveau code dans le pipeline existant

Le script doit etre executable (`python docs/{nom}_architecture.py`) et generer des fichiers `.mmd`.

### ETAPE 03i : EXECUTE avec suivi tracker

Pendant l'execution, respecter ces regles supplementaires :

1. **1 element a la fois** : porter element A1.1, mettre a jour le tracker, puis A1.2, etc.
2. **Gate par element** : chaque element porte doit compiler/fonctionner avant de passer au suivant
3. **Docstrings obligatoires** : chaque classe/fonction portee doit avoir un docstring avec :
   - Description
   - Reference source (ex: "Ported from Liu et al. (2023), strategy/separator_generation.py")
   - Ameliorations apportees
   - Args / Returns / Raises
4. **Pas de copier-coller brut** : adapter au contexte du projet (imports, conventions, API)
5. **Mise a jour tracker** : apres chaque element, mettre a jour INTEGRATION_TRACKER.md :
   ```
   Statut : [ ] -> [x]
   Date creation : YYYY-MM-DD
   Date MAJ : YYYY-MM-DD
   ```

### ETAPE 04i : VALIDATION COMPLETUDE

Avant de declarer l'integration terminee, verifier la completude :

```bash
# Compter les elements TODO restants dans le tracker
grep -c "\[ \]" docs/INTEGRATION_TRACKER.md
# -> 0 = COMPLET | N > 0 = STOP, il reste N elements
```

Verification croisee :
1. Chaque fichier source a un fichier cible correspondant (section C du tracker)
2. Chaque fonction/classe du repo source est soit portee, soit explicitement exclue avec justification
3. Tous les tests passent
4. Les diagrammes Mermaid sont a jour

### Mode Resume Integration

```
/apex -r <task-id> -i
```

1. Lire `docs/INTEGRATION_TRACKER.md`
2. Trouver la section E (Recovery) pour la derniere etape completee
3. Scanner les `[ ]` restants pour determiner le prochain element a porter
4. Reprendre l'execution depuis cet element
5. Ne PAS relire tout le repo source — le tracker contient deja l'inventaire

### Bonnes pratiques Integration

| Pratique | Description |
|----------|-------------|
| **Isolation** | Le code porte doit etre dans un sous-module isole (ex: `agents/genetic_engine/`) pour ne pas polluer l'existant |
| **Bridge pattern** | Creer des fonctions "bridge" entre le code porte et l'existant plutot que de modifier l'existant |
| **Tests d'abord** | Ecrire les tests unitaires du code porte AVANT de l'integrer dans le pipeline existant |
| **Incremental** | Valider chaque phase avant de passer a la suivante — pas de big bang |
| **Rollback clair** | Le rollback = supprimer le sous-module isole. L'existant n'est modifie qu'en derniere phase |

### Retex Integration

**RETEX 2026-03-27** : Integration de Liu et al. (2023) "Prompt Injection attack against LLM-integrated Applications" dans le lab Red Team medical. 52 elements a porter, 20 fichiers source -> 10 fichiers cible. Le tracker a permis de :
- Ne zapper aucune fonction (7 intentions, 10 separators, 6 disruptors, 2 framework generators)
- Documenter chaque amelioration vs la source (OpenAI v0.27 -> Ollama, threads -> async, etc.)
- Permettre la reprise de session apres interruption
- Generer 4 diagrammes Mermaid automatiquement

## Supervision adaptee au risque

| Risque | Supervision | Exemples |
|--------|-------------|----------|
| Faible | Autonome (`-a`) | UI cosmetic, typo, ajout champ |
| Moyen | Guidee | Nouveau composant, nouvelle route API |
| Eleve | Surveillee (`-x -t`) | Auth, securite, moteur, migrations DB |
| Critique | Full pipeline (`-x -t -pr`) | Compliance, donnees client, deploiement |
| Integration | Tracker obligatoire (`-i`) | Portage de code externe, lib, paper |
| Recette complete | Full PDCA-C (`-rc`) | Apres implementation majeure, release, audit qualite |

---

## Mode --recette (`-rc`)

Quand `-rc` est actif, **ETAPE 04 (VALIDATE)** est remplacee par un cycle **PDCA-C complet** orchestrant un swarm de 6 agents paralleles sur 65 checks repartis en 6 categories. A la fin, un scorecard /100 est produit et integre dans ETAPE 09 (FINISH).

### Declenchement

```
/apex -rc <description>           # recette seule, pas de PR
/apex -rc -pr <description>       # recette + PR si score >= 70
/apex -rc -x <description>        # recette + review adversariale
/apex -rc -a <description>        # recette autonome (pas de confirmation)
```

### Pipeline modifie avec -rc

```
00 INIT → 01 ANALYZE → 02 PLAN → 03 EXECUTE
                                      ↓
                             04-RC : PDCA-C (65 checks)
                             ├── C.1 : Build & Compile (10 checks)
                             ├── C.2 : API Consistency (10 checks)
                             ├── C.3 : Frontend Quality (10 checks)
                             ├── C.4 : Security (10 checks)
                             ├── C.5 : AEGIS-Specific (15 checks)
                             └── C.6 : Code Quality (10 checks)
                                      ↓
                             SCORECARD /100 + PDCA verdict
                                      ↓
                             05 EXAMINE (si -x) → 09 FINISH
```

---

### ETAPE 04-RC : RECETTE PDCA-C

#### 04-RC.0 : Pre-flight gate (BLOQUANT)

Avant de lancer le swarm, verifier que la base est stable :

```bash
# Frontend build
cd frontend && npm run build 2>&1 | tail -1
# -> "built in" = GO | erreurs = STOP, corriger d'abord (sinon C.1 echoue sur 5 checks)

# Backend syntax
python -m py_compile backend/server.py
# -> exit 0 = GO | sinon = STOP

# Backend health (si running)
curl -s -o /dev/null -w "%{http_code}" http://localhost:8042/api/redteam/scenarios
# -> 200 = GO | autre = WARNING (checks API marques N/A)
```

Si un pre-flight echoue : **corriger et re-EXECUTE avant de lancer la recette**.

#### 04-RC.0b : Swarm Context Sheet (OBLIGATOIRE — avant lancement du swarm)

Creer le fichier `_alire/temp/apex/{task-id}/SWARM_CONTEXT.md` AVANT de lancer les agents.
Ce fichier est le **tableau de bord partage** que chaque agent lit au demarrage et met a jour en terminant.

**L'orchestrateur genere le fichier initial :**

```markdown
# SWARM CONTEXT — {task-id}

> Derniere MAJ : {timestamp}
> Phase : 04-RC PDCA-C

## Objectif de la session
{description originale de /apex}

## Etat du projet (snapshot pre-swarm)
- Backend : {ONLINE port 8042 | OFFLINE}
- Frontend build : {OK | FAIL — detail}
- Branche : {nom}
- Derniers fichiers modifies : {git diff --name-only HEAD~3, max 15}

## Decisions architecturales en vigueur
{Extraites de ETAPE 02 PLAN — ex: "routes deplacees dans routes/", "i18n obligatoire", etc.}

## Agents actifs
| Agent | Categorie | Checks | Statut | Score | Bloquants trouves |
|-------|-----------|--------|--------|-------|--------------------|
| 1 | Build & Compile | C-01..C-10 | PENDING | -/10 | - |
| 2 | API Consistency | C-11..C-20 | PENDING | -/10 | - |
| 3 | Frontend Quality | C-21..C-30 | PENDING | -/10 | - |
| 4 | Security | C-31..C-40 | PENDING | -/10 | - |
| 5 | AEGIS-Specific | C-41..C-55 | PENDING | -/15 | - |
| 6 | Code Quality | C-56..C-65 | PENDING | -/10 | - |

## Decouvertes cross-agents
{Zone libre — chaque agent y consigne ce qui peut impacter les autres}
Exemple : "Agent 1 : build frontend FAIL sur import manquant dans RagView.jsx → Agent 3 impacte"

## Fichiers sensibles (ne pas modifier)
{Liste de fichiers critiques identifies par ETAPE 01 — les agents les lisent mais ne les modifient PAS}
```

**Regles du Swarm Context Sheet :**

1. **Chaque agent recoit le chemin** du fichier dans son prompt : `"Lis _alire/temp/apex/{task-id}/SWARM_CONTEXT.md au demarrage pour comprendre le contexte global."`
2. **Chaque agent met a jour sa ligne** dans le tableau "Agents actifs" en finissant (statut DONE, score, bloquants)
3. **Section "Decouvertes cross-agents"** : si un agent trouve un probleme qui impacte la categorie d'un autre (ex: build casse impacte frontend quality), il l'ecrit ici
4. **L'orchestrateur relit** le fichier apres completion de tous les agents pour l'aggregation (04-RC.2)
5. **En mode resume** (`-r`), le fichier permet de reprendre sans relancer les agents deja termines
6. **Hors mode `-rc`** : le Swarm Context Sheet est aussi genere pour les modes `-i` (integration) et batch, a chaque fois qu'il y a 2+ agents en parallele

---

#### 04-RC.1 : Swarm 6 agents paralleles (UN SEUL MESSAGE, 6 Agent tool calls, model: haiku)

**Avant de lancer le swarm**, l'orchestrateur substitue `<PROJECT_ROOT>` dans chaque prompt agent :

```bash
# Determiner PROJECT_ROOT automatiquement
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
echo "PROJECT_ROOT = $PROJECT_ROOT"
# Injecter cette valeur dans chaque prompt agent avant delegation
```

Si git non disponible ou hors repo : utiliser `pwd` et informer l'utilisateur.

Lancer tous les agents en meme temps avec `run_in_background: true, model: haiku`. Chaque agent regoit son catalogue de checks, explore le codebase, et produit un rapport structure. Haiku suffit largement pour ces verifications (grep, curl, comptages) et reduit le cout x6.

---

**AGENT 1 — Build & Compile** (10 checks)

```
Tu es un agent de recette Build & Compile pour le projet poc_medical (AEGIS Red Team Lab).
Project root: <PROJECT_ROOT>
Swarm Context: Lis d'abord _alire/temp/apex/<TASK_ID>/SWARM_CONTEXT.md pour le contexte global.
En finissant, mets a jour ta ligne (Agent 1) et consigne tes decouvertes cross-agents.
Execute les 10 checks suivants. Pour chaque check : resultat PASS/FAIL, valeur observee, detail si FAIL.

C-01 : npm run build dans frontend/ termine avec "built in" (zero erreurs)
C-02 : La sortie de build ne contient aucune ligne "error" ou "Error"
C-03 : Aucune TypeScript error dans la sortie build
C-04 : python -m py_compile sur tous les .py de backend/ (depth 1) — 0 erreur
C-05 : python -c "import sys; sys.path.insert(0,'backend'); import server" — exit 0
C-06 : Aucun fichier .jsx contient `${` suivi de '}' (template literal interdit, CLAUDE.md)
C-07 : Aucun console.log() dans les fichiers .jsx (hors commentaires)
C-08 : Aucun hardcoded "localhost" ou "127.0.0.1" dans les fichiers .jsx
C-09 : Aucun hardcoded "localhost" ou "127.0.0.1" dans les fichiers .py (hors commentaires/docstrings)
C-10 : Le fichier logs/ existe ou peut etre cree (aegis.ps1 et aegis.sh present)

Produis un rapport JSON : {"category": "Build", "checks": [{"id":"C-01","result":"PASS"|"FAIL","observed":"...","detail":"..."}], "score": N/10}
```

---

**AGENT 2 — API Consistency** (10 checks)

```
Tu es un agent de recette API Consistency pour le projet poc_medical.
Project root: <PROJECT_ROOT>
Swarm Context: Lis d'abord _alire/temp/apex/<TASK_ID>/SWARM_CONTEXT.md pour le contexte global.
En finissant, mets a jour ta ligne (Agent 2) et consigne tes decouvertes cross-agents.
Backend port: 8042 (si running). Si backend offline, marquer les checks HTTP comme N/A.

C-11 : GET /api/redteam/scenarios retourne HTTP 200 et une liste non-vide
C-12 : Le compte de scenarios dans la reponse == badge count dans ScenariosView.jsx
C-13 : GET /api/redteam/catalog retourne HTTP 200 avec 3 cles (injection, rule_bypass, prompt_leak)
C-14 : Total templates dans /catalog == total dans attack_catalog.py (get_catalog_by_category())
C-15 : GET /api/redteam/chains retourne HTTP 200 et une liste de chains
C-16 : Nombre de chains dans la reponse == len(CHAIN_REGISTRY) dans backend/agents/attack_chains/__init__.py
C-17 : POST /api/redteam/svc avec {"prompt":"test","attack_type":"injection"} retourne {"dimensions":{"d1":...,"d6":...}}
C-18 : POST /api/redteam/attack schema retourne les champs : target_response, scores, audit_analysis
C-19 : Aucun endpoint dans server.py retourne status_code=501 (stub interdit)
C-20 : Aucune donnee mockee hardcodee dans les endpoints (verifier les routes GET qui retournent des listes)

Produis un rapport JSON : {"category": "API", "checks": [...], "score": N/10, "backend_online": true|false}
```

---

**AGENT 3 — Frontend Quality** (10 checks)

```
Tu es un agent de recette Frontend Quality pour le projet poc_medical.
Project root: <PROJECT_ROOT>
Swarm Context: Lis d'abord _alire/temp/apex/<TASK_ID>/SWARM_CONTEXT.md pour le contexte global.
En finissant, mets a jour ta ligne (Agent 3) et consigne tes decouvertes cross-agents.

C-21 : AnalysisView.jsx ne contient pas de valeur hardcodee pour Sep(M) (ex: 0.140)
C-22 : AnalysisView.jsx fait un fetch vers '/api/redteam/campaign/latest' (pas localhost hardcode)
C-23 : CatalogTab.jsx a un mecanisme expand/collapse (state 'expanded', ChevronDown/ChevronRight)
C-24 : AttackView.jsx a un composant HelpModal et un state showHelp
C-25 : AttackView.jsx appelle /api/redteam/svc en parallele avec /api/redteam/attack (Promise.allSettled)
C-26 : ScenarioTab.jsx (ou ScenariosView.jsx) badge count correspond au nombre de scenarios dans backend/scenarios.py
C-27 : Tous les textes de l'UI sont en anglais (aucun mot francais hardcode dans .jsx — hors commentaires)
C-28 : ScenarioHelpModal.jsx a une entree HELP_DB pour chaque scenario ayant une help modal
C-29 : La taille du bundle Vite (dist/) est < 2 MB (chunk principal)
C-30 : Aucun import manquant dans les fichiers .jsx modifies recemment (git diff --name-only HEAD~3)

Produis un rapport JSON : {"category": "Frontend", "checks": [...], "score": N/10}
```

---

**AGENT 4 — Security** (10 checks)

```
Tu es un agent de recette Security pour le projet poc_medical (OWASP + AEGIS).
Project root: <PROJECT_ROOT>
Swarm Context: Lis d'abord _alire/temp/apex/<TASK_ID>/SWARM_CONTEXT.md pour le contexte global.
En finissant, mets a jour ta ligne (Agent 4) et consigne tes decouvertes cross-agents.

C-31 : Aucun pattern d'injection SQL dans les .py (f-string avec input user dans query)
C-32 : Aucun eval() ou exec() avec input non valide dans les .py
C-33 : Aucun pickle.loads() sans controle de source dans les .py
C-34 : Aucune cle API, mot de passe, ou secret hardcode dans le code versionne (grep "api_key\|password\|secret" hors tests)
C-35 : DEBUG=False ou absent dans la config de production (server.py, .env)
C-36 : AllowedOutputSpec dans security_audit_agent.py a forbidden_directives avec >= 6 entrees
C-37 : CORS n'est pas configure sur "*" sans restriction dans server.py
C-38 : Aucun subprocess ou os.system() avec input utilisateur non sanirise
C-39 : Le hook .claude/hooks/process_guard.sh existe, est executable, et bloque uvicorn direct (exit 2)
C-40 : research_archive/ est dans .gitignore ET aucun fichier research_archive/ n'est dans l'index git

Produis un rapport JSON : {"category": "Security", "checks": [...], "score": N/10}
```

---

**AGENT 5 — AEGIS-Specific** (15 checks)

```
Tu es un agent de recette AEGIS-Specific pour le projet poc_medical (these doctorale DY-AGENT).
Project root: <PROJECT_ROOT>
Swarm Context: Lis d'abord _alire/temp/apex/<TASK_ID>/SWARM_CONTEXT.md pour le contexte global.
En finissant, mets a jour ta ligne (Agent 5) et consigne tes decouvertes cross-agents.

C-41 : compute_separation_score() dans security_audit_agent.py flagge statistically_valid: false quand N < 30
C-42 : compute_svc() retourne un dict avec exactement les cles d1, d2, d3, d4, d5, d6 + svc total
C-43 : AllowedOutputSpec.forbidden_directives contient >= 10 entrees (including C1 RAG batch entries)
C-44 : score_response() retourne un dict avec la cle 'violation' de type bool
C-45 : run_formal_campaign() existe dans orchestrator.py et est appelable (pas un stub)
C-46 : Tous les chain_id dans CHAIN_REGISTRY ont un handler correspondant (pas de KeyError si appele)
C-47 : python backend/doc_librarian.py retourne "0 errors" dans la section METADATA
C-48 : pytest backend/tests/test_conjectures.py passe avec 10/10 tests (ou N/N si different)
C-49 : aegis.ps1 et aegis.sh existent a la racine du projet
C-50 : .claude/settings.local.json contient une entree hooks.PreToolUse pour process_guard.sh
C-51 : research_archive/ est dans .gitignore (verifier le fichier .gitignore)
C-52 : git ls-files research_archive/ retourne 0 fichiers (rien de tracke)
C-53 : Le pipeline SVC est branché bout en bout : compute_svc appelé dans server.py /api/redteam/svc
C-54 : scenarios.py a une fonction get_all_scenarios() qui retourne >= 48 scenarios
C-55 : Le frontend gere le mode offline (DEMO MODE banner quand backend inaccessible)

Produis un rapport JSON : {"category": "AEGIS", "checks": [...], "score": N/15}
```

---

**AGENT 6 — Code Quality** (10 checks)

```
Tu es un agent de recette Code Quality pour le projet poc_medical.
Project root: <PROJECT_ROOT>
Swarm Context: Lis d'abord _alire/temp/apex/<TASK_ID>/SWARM_CONTEXT.md pour le contexte global.
En finissant, mets a jour ta ligne (Agent 6) et consigne tes decouvertes cross-agents.

C-56 : Aucun scenario_id en doublon dans scenarios.py (compter les IDs uniques vs total)
C-57 : Aucun chain_id en doublon dans CHAIN_REGISTRY
C-58 : Tous les scenarios dans scenarios.py ont le champ 'allowed_output_spec' defini (pas None)
C-59 : Tous les templates dans attack_catalog.py ont le champ 'category' parmi {injection, rule_bypass, prompt_leak}
C-60 : Aucun template dans attack_catalog.py a un champ 'template' vide ou None
C-61 : CLAUDE.md contient la section "Process Management" (avec aegis.ps1/aegis.sh)
C-62 : Les fichiers modifies par la tache courante (git diff --name-only HEAD) ne contiennent pas de template literals ${} en .jsx
C-63 : git status ne liste aucun fichier .env ou credentials dans "Untracked files"
C-64 : La fonction Score SVC dans RETEX (RetexTab) affiche le score en temps reel (pas hardcode)
C-65 : doc_librarian.py retourne SUMMARY avec 0 errors (toutes categories confondues)

Produis un rapport JSON : {"category": "Quality", "checks": [...], "score": N/10}
```

---

#### 04-RC.2 : Aggregation + Scorecard PDCA

Apres completion des 6 agents, consolider :

```
PDCA SCORECARD
══════════════════════════════════════════════
Category               Score    Weight   Weighted
──────────────────────────────────────────────
C.1 Build & Compile    N/10     15%      X.X
C.2 API Consistency    N/10     20%      X.X
C.3 Frontend Quality   N/10     15%      X.X
C.4 Security           N/10     25%      X.X
C.5 AEGIS-Specific     N/15     15%      X.X
C.6 Code Quality       N/10     10%      X.X
──────────────────────────────────────────────
TOTAL                           100%     XX/100
══════════════════════════════════════════════

Verdict : PASS (>= 70) | CONDITIONAL (50-69) | FAIL (< 50)

FAILs critiques (bloquants pour PR) :
  - C-36 : AllowedOutputSpec forbidden_directives < 6  [Security]
  - C-47 : doc_librarian.py retourne des errors          [AEGIS]
  - C-48 : test_conjectures.py echec                     [AEGIS]
  - C-01 : Build frontend broken                         [Build]

FAILs non-bloquants (a corriger au prochain cycle) :
  - ...
```

Sauvegarder le scorecard dans `pdca/{task-id}/C_SCORECARD.json` et `C_SCORECARD.md`.

#### 04-RC.3 : Remediation immediate (si FAIL critique)

Pour chaque FAIL critique :
1. Corriger immediatement (retour en EXECUTE si necessaire)
2. Re-lancer l'agent concerne (1 seul check, pas tout le swarm)
3. Mettre a jour le scorecard

Si 3+ aller-retours sans resolution : documenter dans `C_BLOCKERS.md` et continuer avec CONDITIONAL.

#### 04-RC.4 : Integration dans ETAPE 09

Dans ETAPE 09 (FINISH), ajouter :
- Score PDCA dans le tracking plan (`Status: TERMINE | Score: XX/100`)
- Si score < 70 : ouvrir une issue "PDCA debt" avec la liste des FAILs non-bloquants
- Si `-pr` actif : n'ouvrir la PR que si score >= 70 (sinon CONDITIONAL warning dans le corps de la PR)

---

### Checks par categorie — reference rapide

| ID | Categorie | Check | Bloquant PR |
|----|-----------|-------|-------------|
| C-01 | Build | npm run build succeeds | OUI |
| C-04 | Build | py_compile 0 erreurs | OUI |
| C-06 | Build | No ${} in .jsx | OUI |
| C-11 | API | /scenarios HTTP 200 | NON |
| C-12 | API | scenario count sync | OUI |
| C-17 | API | /svc retourne d1-d6 | NON |
| C-19 | API | No 501 stubs | OUI |
| C-21 | Frontend | No hardcoded Sep(M) | OUI |
| C-25 | Frontend | SVC parallel call | NON |
| C-31 | Security | No SQL injection | OUI |
| C-34 | Security | No hardcoded secrets | OUI |
| C-36 | Security | AllowedOutputSpec >= 6 | OUI |
| C-39 | Security | process_guard hook active | OUI |
| C-40 | Security | research_archive gitignored | OUI |
| C-41 | AEGIS | Sep(M) validity flag | OUI |
| C-47 | AEGIS | doc_librarian 0 errors | NON |
| C-48 | AEGIS | test_conjectures 10/10 | OUI |
| C-54 | AEGIS | get_all_scenarios >= 48 | OUI |
| C-56 | Quality | No duplicate scenario IDs | OUI |
| C-65 | Quality | doc_librarian SUMMARY 0 errors | NON |

**Regles bloquant PR :** Si 1+ check "bloquant PR" = FAIL, la PR ne peut pas etre ouverte sans accord explicite de l'utilisateur.

---

## Epilogue — Dream audit

Apres ETAPE 09 (FINISH), lancer `/dream audit`. Si le verdict est NEEDS_CONSOLIDATION ou CRITICAL, lancer `/dream consolidate`.
