---
name: bibliography-maintainer
description: "Scientific bibliography management system using a 9-agent swarm for the AEGIS doctoral thesis (ENS, 2026). Discovers new papers on prompt injection (2023-2026+), analyzes them (FR resumes, formulas, threat models, red-team playbooks), organizes into filesystem with indexes, builds math curriculum, performs cross-analysis for research axes, and prepares RAG chunks for ChromaDB ingestion. Use when: update bibliography, new papers, recherche bibliographique, mise a jour biblio, add papers, scan literature, bibliography maintenance, weekly update, analyse croisee."
---

# bibliography-maintainer -- AEGIS Doctoral Thesis Bibliography System

Multi-agent scientific bibliography management with 9 specialized agents running the
autonomous agentic loop (DECOMPOSE -> PLAN -> ACT -> OBSERVE -> EVALUATE -> REPLAN -> COMPLETE).

## Modes

| Mode | Trigger | Description |
|------|---------|-------------|
| `full_search` | Default, or "full", "complete" | Run all 9 agents end-to-end |
| `incremental` | "incremental", "update", "weekly" | COLLECTOR only searches last 7 days, other agents process new papers only |
| `analyze_only` | "analyze", "analyse" | Skip COLLECTOR, run ANALYST+ on existing unprocessed papers |
| `curriculum_update` | "curriculum", "math", "modules" | Run MATHEUX + MATHTEACHER only |
| `research_axes` | "axes", "synthesis", "analyse croisee" | Run SCIENTIST only on all existing data |
| `rag_refresh` | "rag", "chunks", "chromadb" | Run CHUNKER only, regenerate all chunks |
| `scoped` | "scoped", "verification ciblee", "verifie cette reference", HUMILITY GATE | Verification ciblee d'une ou plusieurs references precises via COLLECTOR uniquement (existence, titre, auteurs, annee, venue, chiffre cite, attribution). STEP 0 anti-doublon + HUMILITY GATE. Aucun des 9 agents complets, ZERO mutation du corpus. Produit un rapport scoped. |
| `methodology_refresh` | "methodology", "method_papers", "methodo" | Refresh de la collection aegis_methodology_papers (separee d'aegis_bibliography). Agents actifs : COLLECTOR (arXiv methodo), ANALYST (resume FR), CHUNKER (ingest via ingest_methodology_paper.py). Agents skips : MATHEUX, CYBERSEC, WHITEHACKER, MATHTEACHER, SCIENTIST. Frequence : trimestrielle. |

### Mode `methodology_refresh` -- detail

**Declencheur** : "methodology", "method_papers", "methodo"

**Collection cible** : `aegis_methodology_papers` -- JAMAIS `aegis_bibliography`.

**Source unique des fiches** : `research_archive/doc_references/{YEAR}/methodology/M*.md`

Format canonique : **P006 long** (H2 titre `## [Authors, YEAR] — Title` + metadonnees
`**Reference** : arXiv:XXXX` / `**Revue/Conf** : ...` + sections H3 `### Abstract original`,
`### Resume`, `### Analyse critique`, `### Mecanismes algorithmiques formalises`,
`### Pertinence these AEGIS`, `### Citations cles`, `### Classification`).

Le repertoire historique `research_archive/methodology_corpus/` a ete **supprime**
le 2026-04-11 pour eliminer la duplication de source. Tout nouveau paper de
methodologie DOIT etre ajoute sous `doc_references/{YEAR}/methodology/Mxxx_*.md`
au format P006 complet (verifie via pypdf + tag `[ARTICLE VERIFIE]`).

**Agents actifs** :

| Agent | Role dans methodology_refresh |
|-------|-------------------------------|
| COLLECTOR | Recherche de nouveaux papers methodologie sur arXiv (autonomy, multi-agent research, iterative LLM, agentic benchmarks). Verifie dedup via `check_corpus_dedup.py --title`. |
| ANALYST | Produit le resume FR et remplit les sections obligatoires de la fiche (Resume FR, Contributions, Mecanismes repris dans AEGIS, Limites, Citations). |
| CHUNKER | Ingere la fiche dans `aegis_methodology_papers` via `ingest_methodology_paper.py`. |

**Agents SKIPS** : MATHEUX, CYBERSEC, WHITEHACKER, MATHTEACHER, SCIENTIST
(hors-sujet sur les papers de methodologie agentique).

**Frequence recommandee** : trimestrielle (4 papers/an maximum -- corpus quasi-statique).

**Output** :
- Fiche markdown P006 dans `research_archive/doc_references/{YEAR}/methodology/Mxxx_Slug_YYYY_Topic.md`
- Chunks ingeres dans la collection ChromaDB `aegis_methodology_papers`

**Scripts** :
```
python .claude/skills/aegis-research-lab/scripts/ingest_methodology_paper.py --all
python .claude/skills/aegis-research-lab/scripts/retrieve_methodology_paper.py "query test"
```

### Mode `scoped` -- detail

**Declencheur** : "scoped", "verification ciblee", "verifie cette/ces reference(s)", "resoudre les dettes [A VERIFIER]", appel depuis le HUMILITY GATE (Phase 6b) ou depuis un audit de la skill `anti-confabulation`.

**Objet** : confirmer l'existence et l'exactitude (titre, auteurs, annee, venue, chiffre cite, attribution) d'une ou plusieurs references precises fournies en entree. Ne decouvre PAS de nouveaux papiers, ne reorganise PAS le filesystem, ne touche PAS a ChromaDB.

**Agents actifs** : COLLECTOR uniquement (role verification d'URL via WebSearch). Tous les autres agents (ANALYST, MATHEUX, CYBERSEC, WHITEHACKER, LIBRARIAN, MATHTEACHER, SCIENTIST, CHUNKER, DIRECTOR) sont SKIPS.

**Garde-fous (non negociables)** :
- STEP 0 anti-doublon OBLIGATOIRE sur tout arXiv ID : `python backend/tools/check_corpus_dedup.py <id>`. Si `[DUPLICATE] as PXXX` -> referencer PXXX, ne pas re-verifier. Limite connue : si la ligne MANIFEST ne contient pas l'arXiv ID, completer par `--title "<needle >= 12 chars>"` (cas reel : P018 manquait son arXiv 2406.05946, manque par le check arXiv seul).
- HUMILITY GATE applique a toute claim de primaute ou d'absence portee par la reference ("premier", "seul", "aucune taxonomie", "first", "only"). Reformuler avec scope + date si aucune contre-preuve.
- ZERO mutation du corpus : pas de P-ID attribue, pas d'injection ChromaDB, pas d'edition MANIFEST. Les corrections (re-attribution, ajout de papier, fix metadonnees) sont PROPOSEES dans le rapport, jamais appliquees en mode scoped.
- Content filter safety : ne jamais lire les fichiers sensibles (cf. CLAUDE.md).

**Entree** : liste de references a verifier (texte libre, ou pointeur vers les items `[A VERIFIER]` d'un audit anti-confabulation ou d'une fiche).

**Procedure** :
1. Pour chaque reference, extraire (titre suppose, auteurs, annee, venue, chiffre cite).
2. STEP 0 anti-doublon (arXiv ID puis fallback `--title`) -> si deja dans le corpus, pointer le P-ID.
3. WebSearch (COLLECTOR) : confirmer existence + titre/auteurs/annee/venue exacts + chiffre cite.
4. Classer chaque reference : `[SOURCE]` confirme | `[SOURCE -- qualite inferieure]` (blog/editeur, non peer-reviewed) | erreur d'attribution | erreur de date | `[A VERIFIER]` (introuvable).
5. Appliquer le HUMILITY GATE aux claims de primaute.
6. Lister les lacunes corpus reperees (auteurs "Unknown", arXiv ID manquant) et les candidats a l'ajout (NEW, dedup-clean).

**Output** : `research_archive/research_notes/AEGIS-SCOPED-VERIF_<sujet>_<date>.md` -- tableau verdict par reference, constats d'attribution, lacunes corpus, candidats a l'ajout, items hors-perimetre (les ASR relevent d'une campagne experimentale, pas de la biblio). Aucun fichier `_staging/` des 9 agents n'est produit.

**Frequence** : a la demande (declenche par un audit anti-confabulation, le HUMILITY GATE, ou une relecture de fiche).

**Reference d'execution** : premiere execution documentee le 2026-05-21 sur les 6 dettes de la fiche #08 (`research_notes/AEGIS-SCOPED-VERIF_fiche08-refs_2026-05-21.md`). A revele l'erreur d'attribution "Wei et al." -> Qi et al. (papier "Safety Alignment... Tokens Deep" = corpus P018).

## Inter-Session Memory (Continuity System)

**CRITICAL**: This skill maintains state between executions via THREE systems:

1. **`_staging/memory/MEMORY_STATE.md`** — Single source of truth for all agents
   - Last execution metadata (run_id, date, mode, status)
   - Cumulative counters (papers, formulas, techniques, axes, modules, chunks)
   - Per-agent version tracking (what was produced, what's pending)
   - Incremental mode rules (what to ADD vs REWRITE vs SKIP)
   - User feedback registry (for MATHTEACHER improvement)
   - Quality metrics tracked across runs

2. **`_staging/memory/EXECUTION_LOG.jsonl`** — Append-only history of all runs
   - One JSON line per execution with full stats
   - Used for trend analysis and regression detection

3. **`research_archive/discoveries/`** — Living scientific discoveries repository
   - `DISCOVERIES_INDEX.md` — Master index of all discoveries (classified by impact)
   - `TRIPLE_CONVERGENCE.md` — Major discovery: δ⁰/δ¹/δ² simultaneously vulnerable
   - `CONJECTURES_TRACKER.md` — Evolution of C1-C7 confidence scores across RUNs
   - `THESIS_GAPS.md` — Opportunities for original contribution (gaps in literature)

### Agent Memory Protocol

**BEFORE starting work**, every agent MUST:

**STEP 0 — MANDATORY anti-doublon pre-check** (added 2026-04-09 after RUN-008 Crescendo incident)

For any paper / reference with an arXiv ID that the agent is about to verify, analyze, inject, or attribute a P-ID to, **run the dedup check first**:

```bash
python backend/tools/check_corpus_dedup.py <arxiv_id> [<arxiv_id> ...]
```

- Exit 0 `[NEW]` → proceed with full verification and analysis pipeline
- Exit 1 `[DUPLICATE] as PXXX` → **STOP**. The corpus version PXXX is authoritative. Reference PXXX directly. Do NOT re-verify via WebFetch. Do NOT create a new P-ID. Do NOT re-inject into ChromaDB.
- Exit 2 `[ERROR]` → diagnose (MANIFEST missing, needle too short) before proceeding.

For papers without an arXiv ID (conference proceedings, non-preprint journals), use the `--title` fallback: `python backend/tools/check_corpus_dedup.py --title "<distinctive substring, >= 12 chars>"`.

This step is required for COLLECTOR, ANALYST, LIBRARIAN, and any scoped verification sub-agent. Skipping it caused a real incident on 2026-04-09 where Crescendo (arXiv:2404.01833, already P099) was re-verified in a scoped bibliography-maintainer run.

Then proceed with the standard protocol:
1. Read `MEMORY_STATE.md` to understand current state
2. Read `discoveries/DISCOVERIES_INDEX.md` to know current discoveries
3. Read the specific discovery files relevant to their role (see Discoveries Protocol below)
4. Check its own version section (what was done last time)
5. Identify what's NEW since last run (papers_pending, new feedback, etc.)
6. Decide: CREATE (first run) or UPDATE (subsequent runs)

**AFTER completing work**, every agent MUST:
1. Update its section in `MEMORY_STATE.md` (new counts, version, next-run instructions)
2. Append a DIFF section to its report (Added/Modified/Removed/Unchanged)
3. Log the run to `EXECUTION_LOG.jsonl`
4. Update `discoveries/` if any discovery was added, modified, or invalidated (see below)

### Discoveries Protocol (MANDATORY for ALL agents)

**Every agent** interacts with the discoveries repository:

| Agent | MUST READ before work | MUST UPDATE after work |
|-------|----------------------|----------------------|
| COLLECTOR | DISCOVERIES_INDEX, THESIS_GAPS | Flag if new paper addresses a known gap |
| ANALYST | All 4 discovery files | Update CONJECTURES_TRACKER (evidence for/against), propose new discoveries |
| MATHEUX | CONJECTURES_TRACKER | Update if new formula changes a conjecture's mathematical basis |
| CYBERSEC | TRIPLE_CONVERGENCE, THESIS_GAPS | Update TRIPLE_CONVERGENCE if new threat affects δ-layer analysis, update THESIS_GAPS with new defense gaps |
| WHITEHACKER | TRIPLE_CONVERGENCE, THESIS_GAPS | Update if new technique confirms/invalidates a discovery, update THESIS_GAPS with new attack gaps |
| LIBRARIAN | DISCOVERIES_INDEX | Validate all discovery file references are consistent with MANIFEST |
| MATHTEACHER | CONJECTURES_TRACKER | Ensure math curriculum covers formulas underlying active conjectures |
| SCIENTIST | All 4 discovery files (PRIMARY OWNER) | Update ALL discovery files — add new discoveries, modify confidence scores, close gaps |
| CHUNKER | DISCOVERIES_INDEX | Chunk discovery files for RAG (high priority, tag as chunk_type: "discovery") |

**Discovery lifecycle**:
1. **PROPOSED** → Agent identifies a pattern supported by >= 2 papers
2. **ACTIVE** → SCIENTIST validates and assigns confidence score + ID (D-XXX)
3. **VALIDATED** → Confidence >= 8/10, supported by >= 4 papers across >= 2 agents
4. **INVALIDATED** → Contradicted by >= 3 strong papers, confidence drops below 3/10
5. **ARCHIVED** → No longer relevant (domain shifted) but kept for record

**Rules**:
- Discoveries can go UP or DOWN in confidence — they are NEVER static
- Every RUN must check if existing discoveries are still valid
- New papers can STRENGTHEN or WEAKEN any discovery
- SCIENTIST is the primary owner but ANY agent can propose changes
- Changes must be documented with: paper IDs, reasoning, old score → new score

### Incremental Behavior per Agent

| Agent | First Run | Subsequent Runs |
|-------|-----------|-----------------|
| COLLECTOR | Search all years | Search only since `last_search_date` |
| ANALYST | Analyze all papers | Analyze only `papers_pending` list |
| MATHEUX | Extract all formulas | ADD new formulas to existing glossaire |
| CYBERSEC | Threat-model all | MERGE new papers into existing analysis |
| WHITEHACKER | Extract all techniques | ADD new techniques (T19+, E13+) |
| LIBRARIAN | Build full filesystem | ADD new papers, UPDATE indexes |
| MATHTEACHER | Create 7 modules | IMPROVE existing (add exercises, update refs, refine explanations) |
| SCIENTIST | Create 8 axes | UPDATE axes with new evidence, adjust confidence scores |
| CHUNKER | Chunk everything | Only chunk new/modified files, APPEND to JSONL |

### User Feedback Loop

When user says "je ne comprends pas X" or provides feedback:
1. Feedback is logged in `MEMORY_STATE.md` → User Feedback Registry
2. Next MATHTEACHER run reads the registry and addresses each item
3. MATHTEACHER marks feedback as "addressed" after improving the module

## Agent Map

```
Orchestrator (this skill)
    |
    +-(P1)------------- COLLECTOR    : WebSearch 6 queries, metadata extraction, dedup
    |
    +-(P2 parallel)-+-- ANALYST      : FR resumes, delta-tags, glossaire, research gaps
    |               +-- MATHEUX      : Formula extraction, dependency graph, glossaire
    |               +-- CYBERSEC     : Threat models, MITRE ATT&CK, AEGIS 66 taxonomy
    |               +-- WHITEHACKER  : Red-team playbook, PoC code, exploitation guide
    |
    +-(P3)------------- LIBRARIAN    : Filesystem org, MANIFEST, INDEX_BY_DELTA, GLOSSAIRE
    |
    +-(P4 parallel)-+-- MATHTEACHER  : FR curriculum (5-7 modules), exercises, quiz
    |               +-- SCIENTIST    : Cross-analysis, research axes, thesis positioning
    |
    +-(P5)------------- CHUNKER      : RAG chunks (JSONL), ChromaDB ingestion script
    |
    +-(P6)------------- DIRECTOR     : Consolidated briefing for thesis director skill
```

Gates:
- P1 -> P2: COLLECTOR must report SUCCESS or PARTIAL before analysts start
- P2 -> P3: All 4 analysts must complete before LIBRARIAN organizes
- P3 -> P4: LIBRARIAN must create indexes before SCIENTIST can cross-analyze
- P3 -> P4: MATHEUX must produce MATH_DEPENDENCIES.md before MATHTEACHER starts
- P4 -> P5: SCIENTIST + MATHTEACHER must complete before CHUNKER processes all outputs
- P5 -> P6: ALL agents must complete before DIRECTOR BRIEFING is generated

## Agentic System Prompt (injected into all 9 agents)

All agents use the autonomous agentic binary from:
`../add-scenario/references/agents/autonomous-agent-binary.md`

Each agent receives:
1. The agentic loop (OBJECTIVE -> DECOMPOSE -> PLAN -> ACT -> OBSERVE -> EVALUATE -> REPLAN -> COMPLETE)
2. Working Memory + Action Journal (append-only, auditable)
3. Role-specific objectives, tools, output formats, success criteria, failure signals
4. Content filter safety rules (NE LIS JAMAIS les fichiers sensibles)

## Directory Structure

```
research_archive/
  _staging/
    collector/      # papers_phase1.json, papers_phase2_2026.json, reports
    analyst/        # P001_analysis.md ... P046_analysis.md, report
    matheux/        # GLOSSAIRE_DETAILED.md, MATH_DEPENDENCIES.md, report
    cybersec/       # THREAT_ANALYSIS.md, DEFENSE_COVERAGE_ANALYSIS.md, report
    whitehacker/    # RED_TEAM_PLAYBOOK.md, EXPLOITATION_GUIDE.md, report
    mathteacher/    # Module_01..07.md, GLOSSAIRE_SYMBOLES.md, NOTATION_GUIDE.md, quiz
    scientist/      # AXES_DE_RECHERCHE.md, ANALYSE_CROISEE.md, POSITIONNEMENT_THESE.md, ...
    chunker/        # chunks_for_rag.jsonl, ingest_to_chromadb.py, manifest
    librarian/      # (working area)
    memory/         # (cross-session persistence)
  discoveries/                          # ** LIVING SCIENTIFIC DISCOVERIES **
    DISCOVERIES_INDEX.md                # Master index: all discoveries by impact (CRITICAL/HAUTE/MOYENNE)
    TRIPLE_CONVERGENCE.md               # D-001: δ⁰/δ¹/δ² simultaneously vulnerable, δ³ sole survivor
    CONJECTURES_TRACKER.md              # C1-C7 confidence evolution across RUNs (graph + history)
    THESIS_GAPS.md                      # G-001→G-021: opportunities for original contribution
  articles/                             # ** PUBLICATIONS AND DRAFTS **
    ARTICLES_INDEX.md                   # Master index: all articles by status (DRAFT/REVIEW/SUBMITTED)
    triple_convergence_paper.md         # A-001: Workshop paper on D-001
  doc_references/
    {year}/{domain}/  # Organized paper files
    MANIFEST.md       # Central table of all papers
    INDEX_BY_DELTA.md # Papers indexed by δ⁰ to δ³
    GLOSSAIRE_MATHEMATIQUE.md  # Unified math glossary
```

## Agent Specifications

### 1. COLLECTOR
- **Objective**: Discover academic papers via WebSearch
- **Queries**: 6 parallel searches (attacks, defenses, embeddings, RLHF, separation, medical)
- **Output**: `_staging/collector/papers_phaseN.json` (JSONL with metadata)
- **Success**: >= 20 unique papers per full run
- **Dedup**: By title + arxiv_id + DOI against existing MANIFEST
- **Discoveries**: Read THESIS_GAPS.md before searching — prioritize queries that address known gaps (G-001 to G-012). Flag in report if a new paper directly addresses a gap.

### 2. ANALYST
- **Objective**: Generate French resume (500 mots), extract formulas, identify gaps, assign delta-tags
- **Output**: `_staging/analyst/PXXX_analysis.md` per paper
- **Success**: All sections filled, resume >= 400 words, >= 2 research gaps
- **Language**: 100% FRANCAIS (technical terms in English OK)
- **Discoveries**: Read ALL 4 discovery files. For each paper: check if it supports/weakens any conjecture (C1-C7), check if it addresses/creates a gap (G-XXX), check if it confirms/invalidates a discovery (D-XXX). Update CONJECTURES_TRACKER.md with evidence.

### 3. MATHEUX
- **Objective**: Detailed formula glossaire + dependency graph
- **Output**: `GLOSSAIRE_DETAILED.md` + `MATH_DEPENDENCIES.md`
- **Success**: >= 20 formulas with numerical examples, DAG complete
- **Audience**: bac+2 level (no advanced math assumed)
- **Discoveries**: Read CONJECTURES_TRACKER.md. Flag if a new formula changes the mathematical basis of any conjecture. Ensure formulas underlying active conjectures are in the glossaire.

### 4. CYBERSEC
- **Objective**: Threat models, MITRE ATT&CK mapping, AEGIS 66-technique coverage, gap analysis
- **Output**: `THREAT_ANALYSIS.md` + `DEFENSE_COVERAGE_ANALYSIS.md`
- **Success**: All papers mapped, delta-layer coverage matrix complete
- **Discoveries**: Read TRIPLE_CONVERGENCE.md + THESIS_GAPS.md. Update TRIPLE_CONVERGENCE if new threats affect δ-layer analysis. Update THESIS_GAPS with new defense gaps identified.

### 5. WHITEHACKER
- **Objective**: Attack techniques, exploitability assessment, PoC code, red-team playbooks
- **Output**: `RED_TEAM_PLAYBOOK.md` + `EXPLOITATION_GUIDE.md`
- **Success**: >= 15 techniques with reproducible PoC, delta-bypass assessed
- **Discoveries**: Read TRIPLE_CONVERGENCE.md + THESIS_GAPS.md. Update if new technique confirms/invalidates a discovery. Map PoC to known gaps (e.g., G-011 triple convergence test).

### 6. LIBRARIAN
- **Objective**: Filesystem organization, central indexes, deduplication, validation, and frontend portal synchronization
- **Output**: `doc_references/{year}/{domain}/` + MANIFEST.md + INDEX_BY_DELTA.md + GLOSSAIRE_MATHEMATIQUE.md + `frontend/src/components/thesis/bibliography_data.js` (via python sync script)
- **Success**: All papers indexed, zero duplicates, zero orphans, and React frontend data fully synchronized with MANIFEST.md
- **Discoveries**: Read DISCOVERIES_INDEX.md. Validate that all paper references in discovery files (D-XXX) exist in MANIFEST. Flag broken references.
- **Frontend Sync**: After updating `MANIFEST.md`, run `python research_archive/scripts/update_bibliography_data.py` to regenerate the React frontend data source.

### 7. MATHTEACHER
- **Objective**: Personalized French math curriculum (5-7 modules), exercises, quiz
- **Output**: `Module_01..07.md` + `GLOSSAIRE_SYMBOLES.md` + `NOTATION_GUIDE.md` + `SELF_ASSESSMENT_QUIZ.md`
- **Success**: All modules complete, 100% FR, exercises with full solutions
- **Feedback loop**: Accepts user signals ("je ne comprends pas X") and iterates
- **Discoveries**: Read CONJECTURES_TRACKER.md. Ensure math curriculum covers ALL formulas underlying active conjectures (C1-C7). Prioritize exercises on formulas with high-confidence conjectures.

### 8. SCIENTIST
- **Objective**: Cross-analysis of all data, research axes, thesis positioning, conjecture validation
- **Output**: `AXES_DE_RECHERCHE.md` + `ANALYSE_CROISEE.md` + `POSITIONNEMENT_THESE.md` + `CONJECTURES_VALIDATION.md` + `CARTE_BIBLIOGRAPHIQUE.md`
- **Success**: >= 5 research axes with evidence from >= 2 papers each, SWOT complete
- **Discoveries**: **PRIMARY OWNER** of all discovery files. Read ALL 4 files. Update ALL after work:
  - DISCOVERIES_INDEX.md: add new discoveries, update confidence scores, track history
  - TRIPLE_CONVERGENCE.md: update with new evidence for/against δ-layer vulnerabilities
  - CONJECTURES_TRACKER.md: update ALL conjecture scores, add new conjectures if warranted
  - THESIS_GAPS.md: add new gaps, close gaps if addressed by new papers, update priorities

### 9. CHUNKER
- **Objective**: Prepare all outputs as RAG chunks for ChromaDB ingestion
- **Output**: `chunks_for_rag.jsonl` + `ingest_to_chromadb.py` + `CHUNKS_MANIFEST.md`
- **Success**: 200-400 chunks, metadata complete, ingestion script tested
- **Chunk config**: 400-600 tokens, 50-token overlap, semantic boundaries
- **Discoveries**: Read DISCOVERIES_INDEX.md. Chunk ALL discovery files with HIGH PRIORITY. Tag chunks as `chunk_type: "discovery"` with metadata including `discovery_id` (D-XXX) and `confidence_score`. Discovery chunks must be retrievable by RAG queries about thesis findings.

## Constraints (inherited from CLAUDE.md)

1. **ZERO placeholder** -- every output must be from real API/WebSearch calls
2. **Content filter safety** -- never read full content of sensitive files
3. **Unicode notation** -- δ⁰ to δ³ (never "δ⁰")
4. **Trilingual docs** -- README updates in FR/EN/BR
5. **Git conventions** -- Co-Authored-By: Claude Opus 4.6, no houyi in filenames
6. **Statistical validity** -- Sep(M) requires N >= 30 per condition

## Scheduling

For recurring maintenance, use:
```
/schedule bibliography-maintainer incremental --cron "0 9 * * 1"
```

This runs every Monday at 9am, searching only last 7 days of papers.

## Completion Protocol

When all agents complete, the Orchestrator:
1. Verifies all output files exist and are non-empty
2. Verifies `discoveries/` files are updated (DISCOVERIES_INDEX timestamp matches current RUN)
3. Runs `ingest_to_chromadb.py --dry-run` to validate chunks, THEN executes `python _staging/chunker/ingest_to_chromadb.py --execute` to physically ingest all data into the active ChromaDB instance (aegis_bibliography/aegis_corpus).
4. Runs the automated frontend database synchronizer via `python research_archive/scripts/update_bibliography_data.py` to ensure the portal frontend `bibliography_data.js` is fully synchronized with the new `MANIFEST.md` and literature PDFs.
5. Reports: papers found, analyses created, formulas extracted, axes identified, chunks prepared
6. Reports: discoveries added/modified/invalidated, conjecture score changes, gaps opened/closed
7. **Generates DIRECTOR_BRIEFING** (Phase 6 — MANDATORY, see below)
8. **Runs WIKI SYNC** (Phase 7 — MANDATORY, see below) via `python wiki/build_wiki.py`
   followed by `python -m mkdocs build`. The semantic search widget at `/semantic-search/`
   remains live because it queries ChromaDB directly — no additional action required.
9. Proposes git commit if changes are significant (including `wiki/docs/research/bibliography/`
   updates from Phase 7)

### Phase 6: DIRECTOR BRIEFING (MANDATORY)

**After every RUN**, generate: `_staging/briefings/DIRECTOR_BRIEFING_RUN{XXX}.md`

> **CRITICAL PATH**: briefings live in the `briefings/` subdirectory, NOT at the
> root of `_staging/`. This is non-negotiable — the staging root is reserved for
> active signals and a single README; placing briefings there pollutes the root
> and breaks the apex snapshot scanner. If the `briefings/` directory does not
> exist, create it (`mkdir -p research_archive/_staging/briefings`).

This file is the **SINGLE DELIVERABLE** consumed by the **director skill** to orchestrate thesis actions.
It MUST contain ALL of the following sections:

```markdown
# DIRECTOR BRIEFING — Post RUN-XXX Review

## 1. État des Conjectures
| Conj | Score | Statut | Ce qui manque pour fermer |

## 2. Carte de Maturité par Thème
| # | Thème | Papers | Formules | Maturité (SATURÉ/EN COURS/ÉMERGENT/CRITIQUE) | Action |

## 3. Gaps Critiques — Actions Immédiates
### P0 — Bloquants pour la thèse
### P1 — Importants
### P2 — Souhaitables

## 4. Découvertes — Bilan
### Validées (>= 9/10)
### Actives (7-8/10)
### Potentielles (à valider)

## 5. Résultats Expérimentaux
| Expérience | Gap | Résultat | Implication |

## 6. Plan RUN-(XXX+1)
### Papers à chercher par thème
### Expériences à mener
### Chapitres à rédiger

## 7. Carte de Maturité de la Thèse
| Chapitre | Maturité (%) | Données disponibles | Données manquantes |

## 8. Fichiers de Référence
[Pointers to all relevant files for this RUN]
```

**Source data**: The DIRECTOR BRIEFING is synthesized from:
- SCIENTIST: REVIEW_COMPLETE_CORPUS.md (or PHASE4 report if no review)
- MATHEUX: REVIEW_COMPLETE_FORMULAS.md (or PHASE2 report if no review)
- CYBERSEC + WHITEHACKER: latest phase reports
- DISCOVERIES: all 4 files
- MEMORY_STATE.md: cumulative counters

### Phase 6b: HUMILITY GATE — Primacy Claims Verification (MANDATORY, BLOCKING)

**Added 2026-04-12 after audit-these claims revealed D-021 false positive.**

**Rule**: every new discovery (D-XXX) proposed by SCIENTIST or ANALYST that contains
ANY of the following keywords in its description is **BLOCKED from promotion**
(PROPOSED → ACTIVE) until a WebSearch verification passes:

**Trigger keywords** (case-insensitive, FR + EN):
`premier`, `premiere`, `seul`, `seule`, `aucun autre`, `aucun papier`,
`contribution originale`, `first`, `only`, `no other`, `novel contribution`,
`unique`, `unprecedented`, `never been`, `no prior`, `we are the first`.

**Procedure when triggered**:

1. **STOP** — do NOT assign the D-ID yet.
2. **WebSearch** (via COLLECTOR agent or direct WebSearch tool) with:
   - The core claim reformulated as a search query
   - At least 2 variant queries (synonyms, different phrasing)
   - Date range: 2020-present
3. **If competitor found** (paper, framework, blog post, GitHub repo):
   - Reformulate discovery: replace "premier/seul" with "parmi les premiers" or
     "extends the work of [competitor]"
   - Add the competitor to the corpus via standard pipeline (pre-check dedup first)
   - Lower confidence by 1 point (reflects loss of primacy)
   - Proceed with D-ID assignment using the reformulated text
4. **If NO competitor found**:
   - Qualify the claim with scope + date: "aucun travail identifie par WebSearch
     (YYYY-MM-DD) dans le corpus AEGIS (P001-PXXX)"
   - NEVER state absolute primacy ("le premier au monde", "the only one")
   - Proceed with D-ID assignment using the qualified text

**Failure mode documented (2026-04-12)**: D-021 claimed "premier exemple de red team
autonome avec memoire persistante" but AutoRedTeamer (OpenReview 2025) implements
exactly this with memory-based attack selection + lifelong/incremental attack library.
The SCIENTIST assigned D-021 without WebSearch → false positive in the thesis.

**Philosophical principle** (user directive, 2026-04-12):
> "Il y a tres peu de chance que personne ait vu avant nous ces decouvertes. Soyons humbles."
> The default assumption is that someone has seen it before us. The burden of proof
> is on AEGIS to demonstrate novelty, not on the reviewer to find prior art.

**This gate is BLOCKING**: the DIRECTOR BRIEFING cannot be marked COMPLETE if any
unverified primacy claim exists in the new discoveries of the current RUN.

### Phase 7: WIKI SYNC (MANDATORY — auto-publish)

After the DIRECTOR BRIEFING is generated, the Orchestrator MUST sync the MkDocs wiki so that
new papers and discoveries become visible in:

1. **Static wiki pages** (`wiki/docs/research/bibliography/{year}/...`) — regenerated by
   `wiki/build_wiki.py` from `research_archive/doc_references/` sources
2. **Semantic search** (`/semantic-search/`) — already live via ChromaDB, no rebuild needed
3. **GitHub Pages** — triggered on next commit/push via `.github/workflows/deploy.yml`

**Mandatory step** — run at the end of every RUN:

```bash
# From repo root, via the wiki-publish skill or directly:
python wiki/build_wiki.py
cd wiki && python -m mkdocs build
```

Or equivalently (preferred — uses the skill that handles errors gracefully):

```
/wiki-publish update
```

**Rules**:
- This step is NON-NEGOTIABLE. The skill is NOT complete until wiki sync succeeds.
- If `build_wiki.py` fails, log the error in the DIRECTOR BRIEFING and STOP (do not commit).
- If `mkdocs build` emits new WARNINGS (not pre-existing), flag them in the briefing.
- The semantic search widget at `/semantic-search/` automatically reflects new ChromaDB chunks
  without any rebuild — no additional action required for that path.
- If the user has not committed yet, the skill MUST announce the wiki has been rebuilt locally
  and remind the user to commit + push to propagate to GitHub Pages.

**Post-sync verification**:

```bash
# Verify new papers appear in wiki source tree
ls wiki/docs/research/bibliography/{year}/

# Verify ChromaDB chunks >= 5 per new P-ID
python backend/tools/verify_chromadb_chunks.py --p-ids P131 P132 ...
```

If either check fails → report FAILURE in the briefing.

**Rules**:
- The briefing must be ACTIONABLE — every item must have an action and a responsible agent/skill
- Gaps must be PRIORITIZED (P0/P1/P2) — P0 = blocks the thesis, P1 = important, P2 = nice to have
- Themes must have a MATURITY STATUS — so the director knows what to focus on
- The file must be SELF-CONTAINED — readable without opening other files
- Naming: `DIRECTOR_BRIEFING_RUN{XXX}.md` (matches the RUN ID)
- Location: `research_archive/_staging/briefings/` — NEVER at the staging root

### Discoveries Summary (mandatory in completion report)
```
DISCOVERIES:
  New: D-XXX (description, confidence)
  Updated: D-XXX (old_score → new_score, reason)
  Invalidated: D-XXX (reason)
CONJECTURES:
  C1: X/10 (±N), C2: X/10 (±N), ... C7: X/10 (±N)
GAPS:
  Opened: G-XXX (description)
  Closed: G-XXX (closed by paper PXXX)
  Priority changes: G-XXX (old → new priority)
```

---

## Collections ChromaDB gerees

Ce skill interagit avec deux collections ChromaDB distinctes selon le mode d'execution.
Ne jamais melanger les collections -- les requetes RAG cote securite ne doivent pas
etre polluees par les papers methodologiques, et vice versa.

| Collection | Mode(s) | Source | Contenu |
|-----------|---------|--------|---------|
| `aegis_bibliography` | full_search, incremental, analyze_only, rag_refresh | `research_archive/doc_references/{YEAR}/{domain}/` (hors `methodology/`) | ~46 papers securite LLM, prompt injection, robot chirurgical Da Vinci Xi |
| `aegis_methodology_papers` | methodology_refresh | `research_archive/doc_references/{YEAR}/methodology/M*.md` | Papers de methodologie agentique au format P006 (Agent Laboratory, AI Scientist v1/v2, AI co-scientist, ScienceAgentBench, Tongyi DeepResearch, SAGA, Securing MCP, ...) |

Scripts associes :
- `aegis_bibliography` -> `research_archive/_staging/chunker/ingest_to_chromadb.py` (genere par CHUNKER)
- `aegis_methodology_papers` -> `.claude/skills/aegis-research-lab/scripts/ingest_methodology_paper.py`

---

## Epilogue — Dream audit

Apres le DIRECTOR BRIEFING, lancer `/dream audit`. Si le verdict est NEEDS_CONSOLIDATION ou CRITICAL, lancer `/dream consolidate`.

---

## Bibliographie méthodologique (mapping agent → paper)

Ce skill est lui-meme une implementation d'architecture multi-agent inspiree de la
litterature des systemes scientifiques autonomes. Le swarm de 9 agents est a la fois
l'outil qui maintient la collection `aegis_methodology_papers` ET l'objet d'etude dont
les fiches M* formalisent les methodes.

Source unique de verite des fiches : `research_archive/doc_references/{2025,2026}/methodology/M*.md` (format P006).

### Mapping agent ↔ papers methodologiques

| Agent | Role | Paper(s) source | Pertinence |
|-------|------|-----------------|------------|
| COLLECTOR | Recherche arXiv 46 articles, boucle auto-corrective si <20 | M002 AI Scientist v1 (Lu et al. 2024, arXiv:2408.06292) + M007 MLR-Copilot (Li et al. 2024, arXiv:2408.14033) | End-to-end idea -> code -> experiment |
| ANALYST | 34 resumes FR P006 | M001 Agent Laboratory (Schmidgall et al. 2025, arXiv:2501.04227) | Mecanisme literature_review |
| MATHEUX | Extraction 22 formules | - | Specificite AEGIS (pas de source methodo directe) |
| CYBERSEC | 34 modeles de menaces | M014 Securing MCP (Errico, Ngiam, Sojan 2025, arXiv:2511.20920) | Threat model canonique MCP (C1-C5) |
| WHITEHACKER | 18 techniques + 12 PoC | M014 + corpus offensif AEGIS | Translation threat -> PoC |
| LIBRARIAN | Organisation FS + index + purge doublons | M005 agentRxiv (Schmidgall & Moor 2025, arXiv:2503.18102) | Partage cumulatif structure |
| MATHTEACHER | 7 modules de cours FR | - | Specificite pedagogique AEGIS |
| SCIENTIST | 8 axes de recherche + SWOT | M004 AI co-scientist (Gottweis et al. 2025, arXiv:2502.18864) | Reflection / ranking / evolution multi-agent |
| CHUNKER | 290 chunks RAG -> ChromaDB | M005 agentRxiv + infrastructure partage | Embeddings all-MiniLM-L6-v2 local, zero API |

### Mode `methodology_refresh` — cas particulier

Ce mode traite exclusivement les fiches M* du repertoire `research_archive/doc_references/{YEAR}/methodology/`
et les indexe dans la collection dediee `aegis_methodology_papers` (disjointe de `aegis_bibliography`).
Le CHUNKER utilise `ingest_methodology_paper.py` au lieu du pipeline CHUNKER standard.

Script : `.claude/skills/aegis-research-lab/scripts/ingest_methodology_paper.py --all`

Etat courant de la collection (2026-04-11) : 17 fiches P006 indexees, 136 chunks, couvrant
les 5 categories fondatrices (systemes end-to-end, benchmarks, infrastructure, deploiements
industriels, taxonomies de limites).

### Contraintes issues du safety floor S1-S6 (herite de research-director §5quater)

- **S1** — Mandat these AEGIS non negociable : toute recherche hors scope (securite LLM Da Vinci Xi) est refusee par SCIENTIST.
- **S5** — Pas de modification des SKILL.md par le swarm : seul research-director avec autorisation supervisee peut modifier les skills.
- **S6** — Si le COLLECTOR utilise un outil externe via MCP (ex. arXiv API), les controles C2/C3 de aegis-research-lab §4.4 s'appliquent.

### Collections ChromaDB (rappel)

| Collection | Mode | Source | Nb fiches |
|------------|------|--------|-----------|
| `aegis_bibliography` | full_search, incremental, analyze_only, rag_refresh | `doc_references/{YEAR}/{domain}/` hors methodology | ~46 papers securite LLM |
| `aegis_methodology_papers` | methodology_refresh | `doc_references/{YEAR}/methodology/M*.md` | 17 fiches P006 |

### Visualisation web

- Page pipeline (9 agents + gates + modes) : `/thesis/bibliography-pipeline` (`frontend/src/components/thesis/BibliographyPipelineView.jsx`)
- Page corpus 17 papers methodologiques : `/thesis/academic-agents` (`frontend/src/components/thesis/AcademicAgentsView.jsx`)
- Page workflow integre AEGIS (4 skills + references biblio inline) : `/thesis/aegis-workflow` (`frontend/src/components/thesis/AegisWorkflowView.jsx`)

### References croisees

- Analyse de gap formelle phase (c) : `research_archive/research_notes/SESSION-001_phase_c_gap_analysis_methodology_vs_skills_2026-04-11.md`
- Tracker de conjectures : `research_archive/discoveries/CONJECTURES_TRACKER.md` (MC1-MC13)
