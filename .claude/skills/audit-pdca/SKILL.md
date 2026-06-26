---
name: audit-pdca
description: Audit PDCA universel - Cycle Plan-Do-Check-Act avec benchmark externe, recette securite/unitaire, scoring automatique et amelioration continue. Orchestre prompt-builder, brainstorming N agents paralleles, plan mode, et toutes les skills de recette. Applicable a tout module. Se declenche sur "/audit-pdca", "audit module", "PDCA", "amelioration continue", "benchmark", "score qualite".
---

# AUDIT-PDCA -- Cycle d'amelioration continue universel

Orchestre les skills existantes (prompt-builder, analyze-repo, review, test-first,
react-recette, commit-check, debug-go, debug-react, deploy) dans un cycle PDCA
iteratif avec apprentissage entre chaque tour.

### Model Policy

| Phase | Agent | Model | Justification |
|---|---|---|---|
| P.2 | explore-codebase | **haiku** | Cartographie read-only (Glob, Grep, comptages) |
| D.1 | benchmark websearch | **sonnet** | Recherche web + analyse |
| D.2 | brainstorming x N | **sonnet** | Analyse de gaps, bon ratio cout/qualite |

## Syntaxe

```
/audit-pdca <perimetre> [--benchmark=<repo_ou_produit>] [--cycle=N] [--fix] [--score-only]
```

| Argument | Description | Exemple |
|----------|-------------|---------|
| `<perimetre>` | Module, repertoire, ou domaine | `grc`, `discovery`, `etl`, `frontend`, `cmd/sigma_web/smsi_*` |
| `--benchmark` | Produit ou repo a comparer | `ciso-assistant`, `eramba`, `wazuh`, `openvas` |
| `--cycle=N` | Numero du cycle (auto-detecte si omis) | `--cycle=2` |
| `--fix` | Executer les remediations | |
| `--score-only` | Score sans audit complet | |
| `--domains` | Domaines specifiques | `security,testing,architecture` |

## Repertoire de travail

```
pdca/{perimetre}/
  SCORING_CONFIG.json           # Poids et checks par domaine (evolue a chaque ACT)
  DASHBOARD.md                  # Vue multi-cycles (progression, tendances)
  cycle_001/
    P_PLAN.md                   # Objectifs, perimetre, prompts generes
    D_INVENTORY.json            # Inventaire code
    D_BENCHMARK.json            # Benchmark externe
    D_BRAINSTORM/               # Rapports des N agents paralleles
    C_GAP_REPORT.md             # Gaps consolides
    C_SECURITY.md               # Recette securite
    C_TESTS.md                  # Couverture tests
    C_SCORECARD.json            # Score /100 par domaine
    A_REMEDIATION/              # Plans par priorite
    A_RETEX.md                  # Retrospective du cycle
    A_IMPROVEMENTS.md           # Ameliorations pour cycle N+1
  cycle_002/                    # Herite des ameliorations cycle 001
```

**IMPORTANT :** Le repertoire `pdca/` est a la racine du projet, PAS dans `_alire/`.

---

## PHASE P -- PLAN (4 etapes)

**Objectif :** Verifier l'environnement, charger le contexte du cycle precedent, cartographier le perimetre, generer les prompts d'audit.

### P.0 : PRE-FLIGHT CHECK (BLOQUANT)

> **Note : audit-pdca couvre deux projets distincts avec des ports differents.**
> - **LIA-SEC** (Go backend + sigma-react-frontend) : port **8081**, build via `build_secure_lia.sh`
> - **poc_medical / AEGIS** (Python/FastAPI + React frontend/) : port **8042**, build via `npm run build`
> Adapter les commandes ci-dessous selon le perimetre de l'audit.

Avant toute analyse, verifier que l'environnement est operationnel :

```bash
# --- LIA-SEC (port 8081, Go backend) ---
bash cmd/sigma_web/build_secure_lia.sh 2>&1 | grep "Build réussi"
# -> OK | FAIL = STOP, fixer d'abord

# PostgreSQL (LIA-SEC)
psql -U lia_admin -d lia_scan -c "SELECT 1" 2>/dev/null
# -> OK | FAIL = STOP, auth/service a fixer

# Frontend LIA-SEC (si perimetre inclut React)
cd sigma-react-frontend && node node_modules/.bin/vite build 2>&1 | tail -1
# -> "built in" = OK | erreurs = STOP, fixer d'abord

# Backend health LIA-SEC (si service up)
curl -s -o /dev/null -w "%{http_code}" http://localhost:8081/api/health
# -> 200 = OK | autre = warning (pas bloquant si audit offline)

# --- poc_medical / AEGIS (port 8042, Python backend) ---
# Si le perimetre concerne poc_medical, utiliser a la place :
# python -m py_compile backend/server.py
# cd frontend && npm run build 2>&1 | tail -1
# curl -s -o /dev/null -w "%{http_code}" http://localhost:8042/api/redteam/scenarios
```

**Si un pre-flight echoue :** STOP. Fixer le pre-requis AVANT de lancer les agents. Un audit sur une base cassee produit des findings faux et gaspille des tokens.

**Exception :** si le perimetre de l'audit EST le composant casse (ex: `--fix` sur un build Go broken).

### P.1 : Chargement cycle precedent

- SI cycle > 1 : LIRE `A_IMPROVEMENTS.md`, `A_RETEX.md`, `C_SCORECARD.json` du cycle N-1. Extraire nouveaux checks, checks a retirer, poids a ajuster, focus areas. Definir objectif = score_precedent + delta_realiste.
- SI cycle 1 : Definir objectif = "baseline". Creer `SCORING_CONFIG.json` avec poids par defaut.

> **See** `references/scoring-config.md` pour le JSON SCORING_CONFIG par defaut et les types de checks.

### P.2 : Detection du perimetre

Lancer un agent `explore-codebase` (rapide, read-only, **model: haiku**) pour cartographier : fichiers Go/React avec LOC, migrations SQL, tables PostgreSQL, endpoints API (HandleFunc patterns), services frontend, composants React. Haiku suffit pour cette cartographie read-only (Glob + Grep + comptages).

Output : `D_INVENTORY.json`

### P.3 : Generation des prompts d'audit (SKILL: prompt-builder)

Pour chaque domaine du SCORING_CONFIG, APPELER `/prompt-builder` en mode CREATE. Chaque prompt doit couvrir : benchmark (preuves web), etat actuel LIA-SEC (fichiers, lignes, comptages), gaps, acquis, score /100. Score prompt >= 4/5 requis.

Output : `P_PLAN.md` avec objectifs + prompts generes

---

## PHASE D -- DO (2 etapes)

**Objectif :** Collecter les donnees d'audit via benchmark externe et brainstorming multi-agents.

### D.1 : Benchmark externe (SKILL: analyze-repo + websearch)

- SI `--benchmark` est un repo GitHub : APPELER `/analyze-repo` Phase 1 (inventaire) + Phase 2 (analyse fonctionnelle).
- SINON (produit commercial) : Agent websearch pour architecture, features, modele de donnees, API, integrations.

Output : `D_BENCHMARK.json`

### D.2 : Brainstorming N agents paralleles

Lancer N agents en PARALLELE (un seul message, N tool calls Agent, `run_in_background: true`, **model: sonnet**). Un agent par domaine SCORING_CONFIG, chacun avec le prompt de P.3 + contexte D_INVENTORY + D_BENCHMARK. Sonnet offre le meilleur ratio analyse/cout pour le brainstorming multi-agents (pas besoin d'Opus pour de l'audit, Haiku trop leger pour l'analyse de gaps).

**Regles :** Agents independants, rapports auto-suffisants, pas de code (recherche/audit uniquement), si un echoue les autres continuent.

**Policy gates a injecter dans chaque prompt agent (OBLIGATOIRE) :**
- **NO STUB** : ne jamais recommander de creer des stubs, handlers 501, ou fichiers placeholder
- **NO MOCK** : ne jamais recommander de donnees fictives ou mock data
- **USAGE TRIAGE** : avant de signaler un bug dans un fichier, verifier que ses symboles publics sont appeles ailleurs (`grep -rn "SymbolName" *.go | grep -v le_fichier.go`). Si 0 resultats = dead code, le signaler comme tel (pas comme un bug a corriger)
- **NO DISABLE** : ne jamais recommander de commenter, renommer en .disabled, ou ajouter `//go:build ignore`

Ces gates evitent que les agents investissent du temps a auditer du dead code ou proposent des remediations qui violent les regles LIA-SEC.

Output : `D_BRAINSTORM/{domaine}.md`

---

## PHASE C -- CHECK (4 etapes)

**Objectif :** Filtrer le dead code, valider securite, tests, et consolider les scores.

### C.0 : DEAD CODE FILTER (triage d'usage -- OBLIGATOIRE)

Avant de scorer, filtrer le dead code du perimetre pour ne pas penaliser du code inactif.

Pour chaque fichier du perimetre (D_INVENTORY), grep les symboles publics :

```bash
# Go : extraire fonctions/types publics
grep "^func \|^type " fichier.go | awk '{print $2}' | cut -d'(' -f1

# Chercher les appels hors du fichier -- cross-language obligatoire
# (un handler Go peut etre appele depuis .tsx via route API)
grep -rn "SymbolName" \
  --include="*.go" --include="*.py" --include="*.tsx" --include="*.ts" \
  . | grep -v fichier.go | wc -l
# 0 appels sur TOUS les langages = dead code certain
```

Classer chaque fichier :

| Categorie | Critere | Action scoring |
|-----------|---------|----------------|
| **ACTIF** | Symboles appeles ailleurs | Inclure dans le scoring |
| **PROTOTYPE** | Code propre, routes commentees, 0 appels | Exclure du scoring, signaler comme "a activer ou desactiver" |
| **DEAD** | 0 appels, code obsolete | Exclure du scoring, signaler dans C_GAP_REPORT |

**Pourquoi :** RETEX 2026-03-18 -- un audit de 14 fichiers a revele que 10 etaient du dead code. Sans triage, les agents ont corrige les 14 (stubs + renommages inutiles), gaspillant du temps et violant les policy gates.

Output : `C_USAGE_TRIAGE.md` (tableau fichier/categorie/symboles/appels)

### C.1 : Recette securite (SKILLS: improve-hook + review + frontend-design + create-ui-help)

1. **Checks automatiques SEC-01 a SEC-10** (grep/count sur le perimetre)
2. **Hook securite** : APPELER `/improve-hook` en mode audit si disponible (gosec + semgrep)
3. **Code review** : APPELER `/review` sur les fichiers du perimetre
4. **Design quality** : APPELER `/frontend-design` en mode audit sur les composants React
5. **UI Help audit (BLOQUANT)** : HelpButton par tab, entrees EN+FR en base, parite bilingue
6. **UI Help manquant** : APPELER `/create-ui-help` en mode audit

> **See** `references/check-queries.md` pour le detail de chaque check (SEC-01 a SEC-10), queries SQL UI Help, et checks design quality.

Output : `C_SECURITY.md` + `C_UI_HELP.md`

### C.1b : Recette visuelle (SKILL: webapp-testing -- BLOQUANT)

**Pourquoi :** L'audit par code seul detecte les bugs de mapping mais PAS leur impact visuel.
Un endpoint qui retourne des donnees correctes peut quand meme afficher "Error" si le frontend
lit les mauvais champs. Seul un screenshot reel le detecte.

**Procedure OBLIGATOIRE si le perimetre inclut des composants React :**

1. Demarrer le backend (`./cleanup_services.sh backend`)
2. Builder le frontend (`npm run build`)
3. Pour chaque ecran/tab du perimetre, APPELER `/webapp-testing` :
   - Naviguer vers l'ecran
   - Prendre un screenshot
   - Verifier : aucun "Error", "unknown", "Loading..." permanent, "0%" suspect, donnees manquantes
   - Verifier que les donnees affichees correspondent a ce que le backend retourne
4. Si un ecran affiche des donnees incoherentes : **BLOQUANT** -- corriger avant de continuer

Output : `C_VISUAL_RECETTE.md` (screenshots + verdicts par ecran)

### C.2 : Recette tests (SKILLS: test-first + react-recette)

1. **Backend Go** : `go build`, `go vet`, chercher `*_test.go`, `go test -v -cover`, `/test-first` audit
2. **Frontend React** : `npm run build`, chercher `*.test.ts*`, `npm test --coverage`, `/react-recette`
3. **Recette LIA-SEC** : `/recette-lia-rule` si regles dans le perimetre

> **See** `references/check-queries.md` pour les commandes backend/frontend detaillees.

Output : `C_TESTS.md`

### C.3 : Scorecard (consolidation)

Pour chaque domaine : lire `D_BRAINSTORM/{domaine}.md`, extraire le score, croiser avec C_SECURITY et C_TESTS. Appliquer penalites. Calculer score global pondere. Si cycle > 1 : calculer delta, detecter regressions (> 5 points), determiner tendance.

> **See** `references/check-queries.md` section "Formule de scoring" pour le calcul detaille.

Output : `C_SCORECARD.json` + `C_GAP_REPORT.md`

### C.4 : Replanification conditionnelle (SKILL: /replan)

**Declenchement automatique** si la phase Check revele :
- Score global < 50/100 (objectif initial rate)
- 3+ domaines avec regressions (delta < -5 points)
- Ecarts majeurs entre D_BENCHMARK et le code actuel

**Interface /replan -- parametres a passer :**

```
/replan
  context  : "PDCA cycle {N} -- {perimetre}"
  trigger  : "{score_global < 50 | 3+ regressions | ecart benchmark majeur}"
  observe  : "Score actuel {XX}/100, objectif {YY}/100. Domaines en regression : {liste}."
  compare  : "Ecart vs objectif : {delta}. Causes probables : {liste findings C.1/C.2/C.3}."
  decide   : "Replanifier les phases A.1-A.2 pour focus sur {domaines critiques}."
  ajuste   : "Nouveau plan : {description ajustement}."
```

Si declenchee, `/replan` produit :
1. Un fichier `C_REPLAN.md` dans le cycle en cours (OBSERVE -> COMPARE -> DECIDE -> AJUSTE)
2. Une entree dans `_alire/02_LOGS/Journals/decision_log.jsonl` (format P3 ci-dessus)
3. Un ajustement du plan de remediation (Phase A) base sur les ecarts reels

Si non declenchee, continuer normalement vers Phase A.

---

## PHASE A -- ACT (4 etapes)

**Objectif :** Remedier, documenter, cloturer le cycle, et preparer le suivant.

### A.1 : Plan de remediation (SKILL: plan mode)

ENTRER en Plan Mode. Consolider C_GAP_REPORT + C_SECURITY + C_TESTS. Prioriser par matrice impact x effort :

| Priorite | Contenu | Fichier |
|----------|---------|---------|
| CRITIQUE | securite + build casse | `phase_1_critical.md` |
| HAUTE | gaps architecturaux | `phase_2_high.md` |
| MOYENNE | features manquantes | `phase_3_medium.md` |
| BASSE | polish, docs | `phase_4_low.md` |

SORTIR du Plan Mode. Output : `A_REMEDIATION/phase_*.md`

### A.2 : Execution (si --fix)

Pour chaque phase (1 -> 4), pour chaque tache :
1. Executer le code
2. `/commit-check` apres chaque fichier modifie
3. `/test-first` (Go) ou `/react-recette` + `/react-best-practices` (React)
4. `/create-ui-help` EN+FR pour chaque composant React cree/modifie (gate bloquante)
5. `/frontend-design` review si React
6. `/review` -> findings CRITICAL/HIGH = BLOQUANT
7. Si erreur : `/debug-go` ou `/debug-react`
8. Commit conventionnel (R1)

### A.2b : VERIFICATION GATE (BLOQUANT apres chaque batch de fixes)

**CETTE ETAPE EST OBLIGATOIRE.** Elle a ete ajoutee apres un incident ou des agents de remediation
ont casse 188 fichiers (alpha/useTheme imports manquants) sans detection avant la prod.

**Apres CHAQUE agent de remediation ou batch de fixes, AVANT de commiter :**

```bash
# 1. BUILD GATE (BLOQUANT) -- le code doit compiler
# Go backend :
bash cmd/sigma_web/build_secure_lia.sh
# React frontend :
cd sigma-react-frontend && node node_modules/.bin/vite build

# 2. TEST GATE (BLOQUANT) -- les tests existants ne doivent pas casser
cd sigma-react-frontend && npx vitest run --reporter=verbose

# 3. IMPORT GATE (BLOQUANT) -- verifier que les agents n'ont pas oublie des imports
# Chercher alpha() sans import :
for f in $(grep -rl "alpha(" src/components/ src/pages/ | grep -v node_modules); do
  grep -q "import.*alpha.*from.*styles" "$f" || echo "MISSING alpha: $f"
done
# Chercher theme.palette sans useTheme :
for f in $(grep -rl "theme\.palette" src/components/ src/pages/ | grep -v node_modules | grep -v Theme.tsx); do
  grep -q "useTheme\|const theme" "$f" || echo "MISSING useTheme: $f"
done

# 4. RECOUNT GATE -- les violations doivent diminuer, jamais augmenter
# Compter violations AVANT et APRES dans les fichiers modifies
# Si violations_after >= violations_before : ROLLBACK avec git checkout

# 5. SMOKE TEST -- les endpoints critiques repondent
curl -s http://localhost:8081/api/health | grep -q '"ok"'
```

**Si une gate echoue :** STOP. Corriger le probleme. Re-executer la gate. Ne JAMAIS commiter du code qui ne passe pas les 5 gates.

**Apres la derniere phase de fix (BLOQUANT) :**
1. Build + deploy frontend (vite build + rsync + nginx reload)
2. `/webapp-testing` sur chaque ecran modifie : screenshot + verification visuelle (pas de "Error", "unknown", "ReferenceError", "Loading..." permanent)
3. Si un ecran crash ou affiche des donnees incoherentes : CORRIGER avant de continuer

Apres toutes les phases : mise a jour OBLIGATOIRE de la documentation (CLAUDE.md, api-reference, project-structure, guides) + UI Help pour chaque ecran modifie/cree.

### A.3 : Finalisation avec Plan Mode (OBLIGATOIRE)

ENTRER en Plan Mode. Generer le plan de cloture : fichiers modifies, commits logiques, documentation a mettre a jour, UI Help a verifier, tests a executer, deploy necessaire. SORTIR du Plan Mode. Executer le plan.

**Plan persistant obligatoire :** creer ou mettre a jour `_alire/tracking/PLAN_{perimetre}_PDCA_{YYYY-MM-DD}.md` avec le template `PLAN_TEMPLATE.md`.

**Journal de decisions obligatoire** : ecrire dans `_alire/02_LOGS/Journals/decision_log.jsonl` chaque choix majeur du cycle (replanification, regression detectee, gate echouee, exclusion dead code). Format JSONL strict :

```jsonl
{"ts":"{YYYY-MM-DDTHH:MM:SS}","cycle":N,"phase":"{P|D|C|A}","step":"{P.0|C.0|A.1...}","action":"{verbe}","perimetre":"{perimetre}","decision":"{pourquoi}","gate":"{PASS|FAIL|N/A}","drift_check":"{CLEAR|DETECTED:description}","status":"{success|partial|failure}"}
```

Exemples d'entrees obligatoires :
- Chaque declenchement de `/replan` (C.4)
- Chaque gate A.2b qui echoue + correction appliquee
- Chaque fichier classe DEAD exclu du scoring (C.0)
- Chaque regression detectee (score domaine baisse > 5 points)

### A.4 : RETEX + Ameliorations (SKILL: /retex-analyzer -- OBLIGATOIRE, meme sans --fix)

APPELER `/retex-analyzer` pour generer A_RETEX.md + A_IMPROVEMENTS.md. Si indisponible, generer manuellement. Mettre a jour SCORING_CONFIG.json et DASHBOARD.md.

> **See** `references/retex-template.md` pour les templates complets A_RETEX.md, A_IMPROVEMENTS.md, et DASHBOARD.md.

### A.5 : SCORING REPORT DE SESSION (obligatoire -- fin de chaque cycle)

Produire systematiquement apres A.4 :

```
== AUDIT-PDCA SESSION REPORT -- {perimetre} -- Cycle {N} -- {date} ==

Score global   : {XX}/100 (objectif : {objectif}) -- {ACHIEVED|MISSED|REGRESSION}
Score precedent: {XX}/100 (cycle N-1) | Delta : {+/-N pts}

Phases         :
  P.0 PRE-FLIGHT   : OK | FAIL + {composant bloque}
  P.1 Chargement   : OK | cycle 1 (baseline)
  P.2 Inventaire   : OK -- {N} fichiers, {N} endpoints
  P.3 Prompts      : OK -- {N} prompts >= 4/5
  D.1 Benchmark    : OK | SKIP (--score-only)
  D.2 Brainstorm   : OK -- {N} agents lances
  C.0 Dead code    : OK -- {N} ACTIF / {N} DEAD / {N} PROTOTYPE ({X}% dead)
  C.1 Securite     : OK | {N} violations -- {N} bloquantes
  C.1b Visuel      : OK | SKIP (pas de React) | FAIL {ecran}
  C.2 Tests        : OK | {N} manquants
  C.3 Scorecard    : OK -- {N} domaines, {N} regressions
  C.4 Replan       : TRIGGERED | NOT TRIGGERED
  A.1 Plan         : OK -- {N} tasks (CRITIQUE:{N} HAUTE:{N} MOYENNE:{N} BASSE:{N})
  A.2 Fix          : OK | SKIP (pas de --fix)
  A.2b Gates       : BUILD:{OK|FAIL} TEST:{OK|FAIL} IMPORT:{OK|FAIL} RECOUNT:{OK|FAIL} SMOKE:{OK|FAIL}
  A.3 Finalisation : OK
  A.4 RETEX        : OK

Gates A.2b     : {N}/5 PASS
Policy gates   : NO STUB:{OK|VIOLATION} NO MOCK:{OK|VIOLATION} USAGE:{OK|VIOLATION} NO DISABLE:{OK|VIOLATION}
Drift detecte  : NONE | {description + etape}

Scores par domaine :
  security        : {XX}/100 (delta {+/-N})
  testing         : {XX}/100 (delta {+/-N})
  architecture    : {XX}/100 (delta {+/-N})
  code_hygiene    : {XX}/100 (delta {+/-N})
  completeness    : {XX}/100 (delta {+/-N})
  documentation   : {XX}/100 (delta {+/-N})
  benchmark_parity: {XX}/100 (delta {+/-N})

Auto-evaluation :
  Score objectif atteint   : 1/1 ou 0/1
  Zero regression > 5pts   : 1/1 ou 0/1
  Policy gates respectees  : 1/1 ou 0/1
  Journal decisions complet: 1/1 ou 0/1
  Dead code < 10%          : 1/1 ou 0/1
  Total                    : {N}/5

Open items     : {liste ou "aucun"}
Prochain cycle : score cible {XX}/100, focus {domaines}

Dream audit    : /dream audit → {CLEAN|NEEDS_CONSOLIDATION|CRITICAL}
```

> **Epilogue obligatoire** : apres le scoring report, lancer `/dream audit`. Si le verdict n'est pas CLEAN, lancer `/dream consolidate` avant de clore le cycle.

---

## ORCHESTRATION DES SKILLS -- VUE PIPELINE

```
/audit-pdca {perimetre} --benchmark={X}
  |
  |-- [P.0] PRE-FLIGHT CHECK (BLOQUANT)
  |     build_secure_lia.sh + vite build + psql SELECT 1
  |     Si FAIL : STOP, fixer avant de lancer les agents
  |
  |-- [P.3] /prompt-builder CREATE
  |     Pour chaque domaine : generer le prompt de l'agent auditeur
  |     Score du prompt >= 4/5 requis, sinon iteration
  |
  |-- [D.1] /analyze-repo {benchmark}
  |     Phase 1 (inventaire) + Phase 2 (analyse fonctionnelle)
  |     OU websearch-agent si pas un repo
  |
  |-- [D.2] N x Agent general-purpose (PARALLELE)
  |     Brainstorming : 1 agent par domaine, prompts de P.3
  |     Pattern : lancer dans un seul message, run_in_background
  |
  |-- [C.0] DEAD CODE FILTER (triage d'usage)
  |     grep symboles publics -> compter appels externes
  |     ACTIF = scorer | DEAD/PROTOTYPE = exclure du scoring
  |     Output: C_USAGE_TRIAGE.md
  |
  |-- [C.1] /improve-hook (audit) + /review + /frontend-design (audit)
  |     Recette securite : gosec, semgrep, grep patterns
  |     Design quality : theme-aware, responsive, loading states
  |     UI Help audit : HelpButton par tab, entrees EN+FR en base
  |
  |-- [C.1b] /create-ui-help (audit mode)
  |     Lister ecrans/tabs sans contenu ui_help_content
  |     Verifier bilingue EN+FR complet
  |
  |-- [C.1c] /webapp-testing (recette visuelle -- BLOQUANT si React)
  |     npm run build + deploy frontend
  |     Pour chaque ecran : screenshot + verifier "no Error/unknown/0%"
  |     Detecte les bugs de mapping code<->UI invisibles au code review
  |
  |-- [C.2] /test-first (audit) + /react-recette + /react-best-practices
  |     Couverture tests : go test, npm test, recette LIA
  |     Performance React : memo, useCallback, lazy loading
  |
  |-- [A.1] EnterPlanMode -> plan par phase -> ExitPlanMode
  |     Generer les fichiers de remediation
  |
  |-- SI --fix :
  |     |-- Pour chaque tache :
  |     |     |-- Executer le code
  |     |     |-- /commit-check
  |     |     |-- /test-first OU /react-recette
  |     |     |-- /review -> fix CRITICAL/HIGH (BLOQUANT)
  |     |     |-- /frontend-design (si React) -> fix design quality
  |     |     |-- /create-ui-help (si ecran cree) -> EN+FR + HelpButton par tab
  |     |     |-- SI erreur : /debug-go OU /debug-react
  |     |     +-- git commit
  |     |
  |     |-- [A.2b] VERIFICATION GATE (BLOQUANT apres chaque batch)
  |     |     |-- build_secure_lia.sh (Go) + vite build (React)
  |     |     |-- vitest run (tests existants ne cassent pas)
  |     |     |-- Import check (alpha, useTheme, fetchWithConfig)
  |     |     |-- Recount violations (avant vs apres, jamais augmenter)
  |     |     |-- Smoke test curl endpoints critiques
  |     |     +-- SI gate echoue : STOP + corriger + re-gate
  |     |
  |     +-- /deploy status (verification VPS)
  |
  |-- [A.2b] DOCUMENTATION + UI HELP (OBLIGATOIRE)
  |     Mettre a jour CLAUDE.md, api-reference, project-structure
  |     /create-ui-help pour chaque ecran modifie (EN + FR)
  |     Verifier HelpButton dans chaque composant + chaque tab
  |
  |-- [A.3] EnterPlanMode -> plan de cloture -> ExitPlanMode
  |     Organiser commits, verifier documentation, checklist finale
  |
  +-- [A.4] /retex-analyzer (TOUJOURS)
        Generer A_RETEX.md + A_IMPROVEMENTS.md
        Analyser scores, regressions, prompts agents
        Mettre a jour SCORING_CONFIG.json + DASHBOARD.md
```

---

## BOUCLE PDCA VISUELLE

```
         PLAN                          DO
    +-------------+             +-------------+
    | Charger     |             | Inventaire  |
    | cycle N-1   |    ----->   | Benchmark   |
    | Gen prompts |             | Brainstorm  |
    | (prompt-    |             | N agents //  |
    |  builder)   |             |             |
    +------+------+             +------+------+
           ^                           |
           |                           v
    +------+------+             +------+------+
    | RETEX       |             | Recette     |
    | Ameliorer   |    <-----  | Securite    |
    | prompts     |             | Tests       |
    | scoring     |             | Scorecard   |
    | pipeline    |             |             |
    +-------------+             +-------------+
         ACT                          CHECK

    Chaque tour :
    - Les prompts s'ameliorent (prompt-builder + retex)
    - Le scoring evolue (nouveaux checks, poids ajustes)
    - Le pipeline s'affine (skills ajoutees/retirees)
    - Le score monte (ou les regressions sont detectees)
```

---

## EXEMPLES

```bash
# Premier audit GRC, benchmark CISO Assistant
/audit-pdca grc --benchmark=ciso-assistant

# Deuxieme tour (charge automatiquement les ameliorations du cycle 1)
/audit-pdca grc --benchmark=ciso-assistant

# Audit Discovery, benchmark OpenVAS
/audit-pdca discovery --benchmark=openvas

# Audit frontend seulement, focus secu+tests
/audit-pdca sigma-react-frontend/src/services/ --domains=security,testing

# Audit moteur de regles
/audit-pdca pkg/engine/ --domains=testing,architecture

# Score rapide sans audit complet
/audit-pdca grc --score-only

# Audit + remediation
/audit-pdca grc --benchmark=ciso-assistant --fix

# ETL pipeline
/audit-pdca cmd/sigma_web/etl_* --domains=security,architecture,testing
```

---

## REGLES

1. **prompt-builder AVANT les agents.** Chaque agent recoit un prompt score >= 4/5.
2. **Cycle 1 = baseline.** Score initial = reference, pas d'ameliorations a charger.
3. **Chaque cycle charge A_IMPROVEMENTS du precedent.** Sinon warning.
4. **Les prompts evoluent.** Le RETEX identifie les faiblesses des prompts -> prompt-builder les ameliore au cycle suivant.
5. **Le SCORING_CONFIG evolue.** Nouveaux checks, poids ajustes, domaines ajoutes/retires.
6. **Regressions = alerte.** Si score domaine baisse > 5 points, STOP et analyse cause.
7. **Recette secu + tests APRES chaque modification** (si --fix).
8. **RETEX obligatoire** meme si score = 100.
9. **Pas de code sans plan approuve** (plan mode pour A.1).
10. **Brainstorming = 1 message, N agents, run_in_background.** Pas de sequentiel.
11. **Agents background avec mode auto** pour les taches qui necessitent PostgreSQL (psql).
12. **Verifier chaque finding** avant de le declarer bug. Confirmer code dans build actif, fonction appelee, pas dead code.
13. **Documentation OBLIGATOIRE dans le plan de remediation.** Phase A.2 doit toujours inclure la mise a jour des CLAUDE.md, api-reference, project-structure, et UI Help.
14. **Tester les hooks modifies** avec des commandes reelles avant de les considerer comme termines.
15. **Commits reguliers (R1).** Ne jamais accumuler plus de 2h de modifications sans commiter.
16. **Repertoire pdca/ a la racine**, pas dans _alire/. Les rapports PDCA sont des artefacts de processus, pas de la documentation.
17. **VERIFICATION GATE OBLIGATOIRE (A.2b).** Apres chaque batch de fixes : build + test + import check + recount violations + smoke test. JAMAIS commiter sans passer les 5 gates. Incident de reference : 188 fichiers casses par alpha/useTheme imports manquants (2026-03-17).
18. **Re-verification post-agent.** Quand un agent de remediation modifie >10 fichiers, TOUJOURS verifier les imports (alpha, useTheme, fetchWithConfig) avec grep AVANT de commiter. Les agents oublient systematiquement les imports quand ils font des sed/replace en masse.
19. **Self-scoring obligatoire.** Apres Phase A.2 : re-executer l'audit (grep count) sur les fichiers modifies et comparer violations_before vs violations_after. Si violations_after >= violations_before : la remediation a echoue, rollback.
20. **PRE-FLIGHT OBLIGATOIRE (P.0).** Verifier build Go + React + PostgreSQL AVANT de lancer les agents. Un audit sur base cassee = findings faux + tokens gaspilles.
21. **DEAD CODE FILTER (C.0).** Trier ACTIF/DEAD/PROTOTYPE avant scoring. Ne pas penaliser du dead code dans le scorecard.
22. **POLICY GATES dans prompts agents (D.2).** Injecter NO STUB, NO MOCK, USAGE TRIAGE, NO DISABLE dans chaque prompt de brainstorm. RETEX 2026-03-18 : sans ces gates, les agents corrigent du dead code et creent des stubs. Ces gates sont directement implementees en C.0 (triage ACTIF/DEAD/PROTOTYPE) et mesurees par le check HYG-03 dans SCORING_CONFIG (dead code ratio < 10%). La chaine est : regle 22 (intent) → C.0 (execution) → HYG-03 (mesure).
