---
name: fiche-attaque
description: >
  Génère les fiches d'attaque formelles (.docx, 11 sections + annexes) pour les 97 templates
  d'injection de la librairie AEGIS (thèse ENS, 2026). Chaque fiche analyse formellement
  un template selon le cadre δ⁰-δ³ avec 3 agents spécialisés (SCIENTIST, MATH, CYBER-LIBRARIAN).

  Architecture : Agent autonome de niveau 5 — suit la boucle :
  OBJECTIVE → DECOMPOSE → PLAN → ACT → OBSERVE → EVALUATE → (REPLAN) → COMPLETE

  Triggers:
    'fiche d'attaque', 'generate fiche', 'attack sheet', 'analyse de prompt',
    '/fiche-attaque', 'batch fiches', 'remaining fiches',
    'fiche pour template XX', 'analyse formelle du prompt XX'

  NE PAS UTILISER pour : création Word générique (→ skill docx),
  forge de nouveaux prompts (→ aegis-prompt-forge).
---

# Fiche d'Attaque Generator — AEGIS

**Architecture** : Agent autonome de niveau 5
**Boucle** : `OBJECTIVE → DECOMPOSE → PLAN → ACT → OBSERVE → EVALUATE → (REPLAN) → COMPLETE`
**Pipeline** : 3 agents spécialisés + 4 scripts Python + ChromaDB dual-collection

> **SESSION INIT** : Lire `research_archive/RESEARCH_STATE.md` au début de chaque session.
> Mettre à jour la Section 5 (fiches) après chaque génération.

---

## 1. SÉCURITÉ CONTENT FILTER — VÉRIFICATION OODA (PRIORITÉ ABSOLUE)

Avant toute lecture de fichier, appliquer la vérification OODA/Orient :

**Le fichier contient-il le champ `"template"` d'un JSON de prompts ?**
→ Si oui : **NE JAMAIS LIRE CE CHAMP**. Charger uniquement les métadonnées safe.

**Fichiers et champs INTERDITS :**
- Champ `template` dans tout fichier `backend/prompts/XX-*.json`
- Templates #08 et #11 : mode ultra-safe obligatoire (sections 2/4/8 réduites au minimum)

**Fichiers AUTORISÉS (safe) :**
- Métadonnées JSON sans le champ `template` : `id`, `name`, `category`, `chain_id`,
  `target_delta`, `conjecture`, `variables`, `taxonomy`, `mitre`, `svc_score`
- Fichiers `.md` d'analyse : `backend/prompts/XX-name.md`
- Configs : `dim_config.json`, `detection_baseline.json`
- Scripts : `scripts/batch_fiches.py`, `scripts/query_chromadb.py`, etc.

**Pour la Section 2 (Prompt d'Injection)** : référencer le template par son chemin
`backend/prompts/XX-name.json` uniquement. Analyser la structure depuis le `.md`.
Ne jamais copier le contenu brut du template.

**Si un content filter se déclenche** : logger `BLOCKED` dans l'index. Ne pas retenter.
Passer au template suivant. Ne jamais tenter de contourner le filtre.

**Règle de rédaction** : toujours en **FRANÇAIS** pour réduire les déclenchements de filtres.

---

## 2. ARCHITECTURE MULTI-AGENT

```
OBJECTIVE : générer fiche #XX
    ↓
DECOMPOSE : 7 sous-tâches (cf. §3)
    ↓
Phase 0 — SCIENTIST [AUTONOMOUS]
  → Query ChromaDB dual-collection (query_chromadb.py --multi-collection)
  → Output : rag_context + Section 11 (markdown)
    ↓ GATE : rag_context disponible avant Phase 1
Phase 1 — MATH + CYBER-LIBRARIAN [PARALLÈLE, AUTONOMOUS]
  → MATH      : Sections 3 + 5
  → CYBER-LIB : Sections 1, 2, 4, 6, 7, 8, 9, 10 + Annexe A
    ↓ GATE : toutes sections non-vides avant Phase 2
Phase 2 — Assemblage [AUTONOMOUS]
  → batch_fiches.py assemble → fiche_attaque_XX.docx
  → MAJ fiche_index.json
    ↓ GATE : .docx généré + index mis à jour
Phase 3a — Cross-validation RAG [AUTONOMOUS]
  → SCIENTIST re-query avec conclusions → vérification complétude
    ↓
Phase 3b — Seed ChromaDB [AUTONOMOUS]
  → seed_fiches_to_rag.py --template XX --also-bibliography
    ↓
Phase 4 — Gaps research_requests [AUTONOMOUS]
  → Section 11.4 → ajouter entrées dans research_requests.json
    ↓
COMPLETE → SCORING REPORT
    ↓
Phase 5 — Dream audit [AUTONOMOUS]
  → /dream audit — si NEEDS_CONSOLIDATION ou CRITICAL → /dream consolidate
```

### Roster des agents et modèles

| Agent | Modèle | Sections | Justification |
|-------|--------|----------|--------------|
| SCIENTIST | Sonnet | 11 + rag_context | Synthèse analytique RAG, identification axes de recherche |
| MATH | Opus | 3, 5 | Raisonnement formel Sep(M), Reachable(), preuves C1/C2 |
| CYBER-LIBRARIAN | Sonnet | 1,2,4,6,7,8,9,10,A | Agent unifié menace+défense+assemblage (Haiku trop instable) |
| Annexe B | Script generate_fiche_docx.py | B | Glossaire standardisé — aucun agent ne la génère |

### Règles impératives communes aux 3 agents

```
RÈGLE 1 — TEXT-ONLY OUTPUT
Retourner les sections en texte markdown dans la réponse.
Ne créer AUCUN fichier (.md, .json, .docx).
Ne pas utiliser les outils Write, Edit, ou Bash pour écrire des fichiers.
L'orchestrateur se charge de l'assemblage.

RÈGLE 2 — SECTIONS EXCLUSIVES (ZÉRO CHEVAUCHEMENT)
Générer UNIQUEMENT les sections assignées. RIEN D'AUTRE.
Si une section n'est pas dans la liste : ne pas la générer, même partiellement.

RÈGLE 3 — SÉCURITÉ CONTENT FILTER
Ne jamais lire le champ "template" des JSON.
Travailler uniquement via métadonnées + fichiers .md.
Rédiger en FRANÇAIS. Symboles Unicode δ⁰ δ¹ δ² δ³ (jamais δ⁰/1/2/3 ASCII).
```

### Pont dual-collection ChromaDB

Le SCIENTIST query **deux collections simultanément** :
- `aegis_corpus` : fiches d'attaque générées (cross-referencing entre fiches)
- `aegis_bibliography` : 454+ chunks (60 papers P001-P060, formules, découvertes D-001→D-016, C1-C7, G-001→G-021)

```bash
python scripts/query_chromadb.py "{name}" "{category} {target_delta}" --n 5 --multi-collection
```

---

## 3. BOUCLE OPÉRATIONNELLE — DECOMPOSE

Pour chaque template à générer, décomposer en 7 sous-tâches :

```
Sous-tâche 1 — Lecture sources safe
  Type       : collect
  Complexité : TRIVIAL
  Autonomie  : AUTONOMOUS
  Action     : batch_fiches.py prepare --num XX
  Succès si  : metadata disponible + sensitivity != "blocked"
  Échec si   : JSON manquant (FAILURE fatale) | content filter (BLOCKED)

Sous-tâche 2 — SCIENTIST Phase 0
  Type       : agent_call
  Complexité : MODERATE
  Autonomie  : AUTONOMOUS
  Action     : lancer agent SCIENTIST avec metadata + analysis_md
  Succès si  : rag_context non-vide + section_11 non-vide
  Échec si   : ChromaDB inaccessible → fallback references/delta-framework.md

Sous-tâche 3 — MATH Phase 1
  Type       : agent_call
  Complexité : COMPLEX
  Autonomie  : AUTONOMOUS
  Action     : lancer agent MATH avec metadata + rag_context
  Succès si  : section_3 et section_5 non-vides, formules en notation Unicode
  Échec si   : content filter → sections réduites + logger

Sous-tâche 4 — CYBER-LIBRARIAN Phase 1 [PARALLÈLE avec Sous-tâche 3]
  Type       : agent_call
  Complexité : COMPLEX
  Autonomie  : AUTONOMOUS
  Action     : lancer agent CYBER-LIBRARIAN avec metadata + rag_context
  Succès si  : sections 1,2,4,6,7,8,9,10,A non-vides, zéro copie de template brut
  Échec si   : content filter → logger, sections réduites

Sous-tâche 5 — Assemblage .docx
  Type       : script_call
  Complexité : TRIVIAL
  Autonomie  : AUTONOMOUS
  Action     : batch_fiches.py assemble --num XX (sections JSON via stdin)
  Succès si  : .docx généré + fiche_index.json status="done"
  Échec si   : python-docx manquant → pip install python-docx

Sous-tâche 6 — Cross-validation + Seed ChromaDB
  Type       : agent_call + script_call
  Complexité : MODERATE
  Autonomie  : AUTONOMOUS
  Action     : SCIENTIST re-query → seed_fiches_to_rag.py --template XX --also-bibliography
  Succès si  : seed confirmé dans les deux collections
  Échec si   : ChromaDB inaccessible → logger, continuer

Sous-tâche 7 — Gaps vers research_requests
  Type       : file_update
  Complexité : TRIVIAL
  Autonomie  : AUTONOMOUS
  Action     : parser Section 11.4 → ajouter entrées dans research_requests.json
  Succès si  : nouvelles RR créées ou "aucun gap identifié" documenté
  Dépend de  : Sous-tâche 2 (SCIENTIST)
```

---

## 4. PHASE ACT — Détail des scripts

### Script 1 — batch_fiches.py

```bash
# Lister les templates en attente
python scripts/batch_fiches.py list

# Préparer les métadonnées d'UN template (sans le champ template)
python scripts/batch_fiches.py prepare --num 17

# Préparer une plage
python scripts/batch_fiches.py prepare --range 17 30

# Préparer tous les pending
python scripts/batch_fiches.py prepare --remaining

# Assembler le .docx depuis les sections JSON (stdin)
echo '{"metadata": {...}, "sections": {...}}' | python scripts/batch_fiches.py assemble --num 17

# Marquer comme bloqué
python scripts/batch_fiches.py mark-blocked --num 08 --reason content_filter
```

**Output de `prepare`** : JSON avec `metadata` (sans champ `template`), `analysis_md`,
`dim_config`, `detection_baseline`, `sensitivity` (safe|caution), `slug`.

### Script 2 — query_chromadb.py

```bash
# Query single collection
python scripts/query_chromadb.py "FDA protocol tool hijack" --n 5

# Query dual-collection (RECOMMANDÉ pour le SCIENTIST)
python scripts/query_chromadb.py "homoglyph injection" "unicode evasion delta1" --n 5 --multi-collection

# Filtrer par doc_type
python scripts/query_chromadb.py "sep(M) score" --doc-type reference --n 5
```

**Output JSON** : liste de chunks triés par distance cosinus (ordre croissant = plus pertinent).
Critère de pertinence : distance < 1.5.

### Script 3 — seed_fiches_to_rag.py

```bash
# Seed un template spécifique dans les deux collections
python scripts/seed_fiches_to_rag.py --template 17 --also-bibliography

# Dry-run pour vérifier
python scripts/seed_fiches_to_rag.py --dry-run

# Seed tous les "done"
python scripts/seed_fiches_to_rag.py --also-bibliography
```

### Script 4 — generate_fiche_docx.py

Appelé automatiquement par `batch_fiches.py assemble`. Peut aussi être invoqué directement :

```bash
python scripts/generate_fiche_docx.py \
  --metadata metadata.json \
  --sections sections.json \
  --output fiche_attaque_17.docx
```

---

## 5. PHASE OBSERVE — Critères de complétion

### Pour une fiche individuelle → `done` si :
1. Fichier `.docx` généré dans `research_archive/doc_references/prompt_analysis/`
2. `fiche_index.json` affiche `status: "done"` pour ce numéro
3. Les 11 sections sont non-vides (aucun `[Section à compléter]`)
4. Fiche seedée dans ChromaDB (`seed_fiches_to_rag.py` sans erreur)
5. Gaps Section 11.4 traités (ajoutés à `research_requests.json` ou "aucun gap")

### Pour une fiche → `blocked` si :
- Content filter déclenché et non contournable
- Template #08 ou #11 en mode ultra-safe échoue quand même
- `attempts` atteint 2 sans succès

### Pour un batch → `complete` si :
- Toutes les fiches demandées sont `done` ou `blocked`
- `fiche_index.json` est cohérent avec le disque
- Scoring Report produit

---

## 6. PHASE EVALUATE — Quality Hooks

| Hook | Quand | Vérification | Échec |
|------|-------|-------------|-------|
| QH-CF | Avant toute lecture JSON | Champ `template` absent du chargement | HALT + BLOCKED |
| QH-S0 | Après SCIENTIST | rag_context non-vide + section_11 non-vide | Fallback delta-framework.md |
| QH-P1 | Après MATH + CYBER-LIB | 11 sections non-vides, zéro placeholder | REPLAN agent concerné |
| QH-P2 | Après assemblage | .docx généré + index MAJ | REPLAN batch_fiches |
| QH-P3 | Après seed | Confirmation seed dans les deux collections | Logger, continuer |
| QH-RR | Après Section 11.4 | Gaps créés dans research_requests.json | Créer manuellement |

---

## 7. PHASE REPLAN — Gestion des échecs

**Règle** : ne jamais retenter identiquement. Changer au moins un paramètre.

| Tentative | Erreur | Action |
|-----------|--------|--------|
| 1ère | Content filter section | Réduire le scope de la section concernée |
| 2ème | Content filter persistant | Mode ultra-safe (sections 2/4/8 au minimum) |
| 3ème | Content filter total | `blocked` — ne pas retenter |
| 1ère | ChromaDB inaccessible | Fallback `references/delta-framework.md` + continuer |
| 1ère | .md manquant | Générer depuis métadonnées seules (sections réduites) |
| 1ère | JSON manquant | FAILURE fatale — signaler à l'utilisateur |
| 1ère | Agent timeout | Retenter 1 fois, puis `skipped` |

---

## 8. JOURNAL D'ACTION — Format (append-only)

```
[{YYYY-MM-DDTHH:MM:SS}] PHASE={phase} STEP={N} TEMPLATE={num} SESSION={id}
ACTION={verbe}   TOOL={agent|script|none}
INPUT={résumé}   OUTPUT={résumé}
SECURITY={CLEAR|BLOCKED:raison}
STATUS={success|partial|failure|blocked}
ATTEMPTS={N}
```

Exemple :
```
[2026-04-04T10:00:00] PHASE=ACT STEP=1 TEMPLATE=17 SESSION=043
ACTION=prepare   TOOL=batch_fiches.py
INPUT=template #17   OUTPUT=metadata OK, sensitivity=safe, slug=17-genetic-additional-task
SECURITY=CLEAR
STATUS=success   ATTEMPTS=1

[2026-04-04T10:02:00] PHASE=ACT STEP=2 TEMPLATE=17 SESSION=043
ACTION=agent_call   TOOL=SCIENTIST
INPUT=metadata+analysis_md   OUTPUT=rag_context(4 chunks)+section_11(OK)
SECURITY=CLEAR
STATUS=success   ATTEMPTS=1

[2026-04-04T10:15:00] PHASE=ACT STEP=5 TEMPLATE=17 SESSION=043
ACTION=assemble   TOOL=batch_fiches.py
INPUT=sections JSON   OUTPUT=fiche_attaque_17_genetic_additional_task.docx
SECURITY=CLEAR
STATUS=success   ATTEMPTS=1
```

---

## 9. COMMANDES

### `/fiche-attaque {num}`
OBJECTIVE (fiche #num) → DECOMPOSE (7 sous-tâches) → pipeline complet → COMPLETE

### `/fiche-attaque batch {start} {end}`
OBJECTIVE (fiches #{start} à #{end}) → itération sur chaque numéro →
DECOMPOSE individuel → pipeline → COMPLETE (bilan batch)

### `/fiche-attaque remaining`
OBJECTIVE (toutes les pending) → `batch_fiches.py list` → itération sur chaque pending →
pipeline individuel → COMPLETE

### `/fiche-attaque status`
Lire `fiche_index.json` → afficher tableau de progression :
```
== FICHE-ATTAQUE — Status {date} ==
Done    : {N}/97 ({pct}%)
Pending : {N}
Blocked : {N}
Skipped : {N}

Dernière générée : fiche #{num} ({date})
Prochaine        : fiche #{num}
```

### `/fiche-attaque rebuild-index`
Scanner `research_archive/doc_references/prompt_analysis/` →
Reconstruire `fiche_index.json` depuis les fichiers sur disque →
Vérifier cohérence avec ChromaDB

---

## 10. SCORING REPORT DE SESSION — Format obligatoire (COMPLETE)

Produit après chaque session avec ≥ 1 fiche générée.

```markdown
# Scoring Report — FICHE-ATTAQUE — Session {id} — {date}

## Résumé
Fiches générées : {N} | Bloquées : {N} | Skipped : {N}
Progression globale : {N}/97 ({pct}%)

## Détail par fiche
| # | Nom | Status | Sections OK | RAG chunks | Gaps RR | Temps |
|---|-----|--------|------------|------------|---------|-------|

## Quality hooks
| Hook | Déclenché N fois | Résultat |

## Alertes sécurité (content filter)
{liste ou NONE}

## Gaps identifiés → research_requests.json
| RR-XXX | Source fiche | Type | Priorité |

## Auto-évaluation
| Critère | Score | Commentaire |
|---------|-------|-------------|
| Complétude sections | 1/1 ou 0/1 | |
| Sécurité content filter | 1/1 ou 0/1 | |
| ChromaDB seed | 1/1 ou 0/1 | |
| Gaps traités | 1/1 ou 0/1 | |
| Journal complet | 1/1 ou 0/1 | |
| **Total** | **{N}/5** | |

## Journal d'action complet
{Toutes les entrées de la session}
```

---

## 11. STRUCTURE DU DOCUMENT GÉNÉRÉ

Chaque fiche : 11 sections + 2 annexes. Structure stricte produite par `generate_fiche_docx.py`.

### En-tête
- **FICHE D'ATTAQUE** (titre niveau 0)
- Nom du template (titre niveau 1)
- Tableau de métadonnées : Identifiant | Catégorie | Couche ciblée | Conjecture |
  Chain ID | MITRE ATT&CK | OWASP LLM | Ref. thèse

### Sections

| Section | Agent | Contenu |
|---------|-------|---------|
| 1 — Contexte et Modèle de Menace | CYBER-LIB | Scénario Da Vinci Xi, DY-AGENT, objectif attaquant |
| 2 — Prompt d'Injection | CYBER-LIB | Référence par ID, variables, analyse formelle (pas le contenu brut) |
| 3 — Cadre Mathématique | MATH | Sep(M), Reachable(S,p), couches δ, P(detect) |
| 4 — Analyse IA : Mécanismes de Refus | CYBER-LIB | Chaîne décision LLaMA 3.2, taux refus, facteurs contournement |
| 5 — Score SVC | MATH | Tableau 6 dimensions D1-D6, poids, score pondéré |
| 6 — Paramètres et Résultats | CYBER-LIB | Config expérimentale (N=30, T=0.7), ASR, Sep(M) |
| 7 — Défenses et Contre-mesures | CYBER-LIB | Par couche δ⁰-δ³, 66 techniques, recommandations |
| 8 — Analyse Corrective | CYBER-LIB | Problème fondamental, corrections C1→CN, impact cumulé |
| 9 — État de l'Art | CYBER-LIB | Références académiques + mapping thèse + refs RAG |
| 10 — Verdict | CYBER-LIB | Danger/Complexité/Reproductibilité, positionnement C1/C2 |
| 11 — Analyse Scientifique | SCIENTIST | Littérature RAG, axes de recherche, gaps, recommandations thèse |
| Annexe A | CYBER-LIB | Checklist de validation |
| Annexe B | Script | Glossaire mathématique standardisé (δ⁰-δ³, Sep(M), ASR, SVC...) |

---

## 12. INDEX DE PROGRESSION

**Fichier** : `research_archive/doc_references/prompt_analysis/fiche_index.json`

```json
{
  "last_updated": "2026-04-04T14:30:00",
  "total_templates": 97,
  "fiches_completed": 23,
  "fiches_blocked": 2,
  "fiches_remaining": 72,
  "fiches": {
    "17": {
      "status": "done",
      "file": "fiche_attaque_17_genetic_additional_task.docx",
      "date": "2026-04-04",
      "name": "Genetic Additional Task",
      "target_delta": "delta1",
      "conjecture": "C1",
      "svc_score": "4.5",
      "asr": "0.67",
      "sep_m_valid": true,
      "notes": "Generated by batch_fiches.py (3 agents: SCIENTIST+MATH+CYBER-LIBRARIAN)"
    },
    "08": {
      "status": "blocked",
      "reason": "content_filter",
      "last_attempt": "2026-04-01",
      "attempts": 2
    }
  }
}
```

**Statuts** : `done` | `pending` | `in_progress` | `blocked` | `skipped`

---

## 13. SOURCES DE DONNÉES ET RÉFÉRENCES

| Fichier | Rôle | Accès |
|---------|------|-------|
| `backend/prompts/XX-name.json` | Métadonnées template (SANS champ template) | R safe |
| `backend/prompts/XX-name.md` | Analyse du template | R safe |
| `backend/prompts/dim_config.json` | 6 dimensions SVC avec poids | R |
| `backend/prompts/detection_baseline.json` | Baseline de détection | R |
| `research_archive/doc_references/prompt_analysis/fiche_index.json` | Index de progression | R/W |
| `research_archive/doc_references/prompt_analysis/research_requests.json` | Gaps → research-director | R/W |
| `ChromaDB aegis_corpus` | Fiches d'attaque indexées | R/W |
| `ChromaDB aegis_bibliography` | Bibliographie doctorale (60 papers) | R |
| `references/agent-prompts.md` | Prompts standardisés avec placeholders pour les 3 agents | R |
| `references/delta-framework.md` | Définitions formelles DY-AGENT, couches δ, conjectures | R |
| `references/document-sections.md` | Contenu attendu par section pour les agents | R |
| `backend/taxonomy/defense.py` | 66 techniques de défense (agent CYBER-LIBRARIAN) | R |
| `research_archive/manuscript/formal_framework_complete.md` | Définitions mathématiques sources | R |

**Scripts** (chemin : `scripts/`) :

| Script | Phase | Usage |
|--------|-------|-------|
| `batch_fiches.py` | ACT | prepare, assemble, list, mark-blocked |
| `query_chromadb.py` | ACT | Query ChromaDB (single ou multi-collection) |
| `seed_fiches_to_rag.py` | ACT | Seed fiche dans aegis_corpus + aegis_bibliography |
| `generate_fiche_docx.py` | ACT | Génération .docx (appelé par assemble) |

---

## 14. CYCLE FICHE ↔ RESEARCH-DIRECTOR

```
Fiches identifient gaps (Section 11.4) → research_requests.json
    ↓
research-director.cycle → bibliography-maintainer incremental
    ↓
Nouveaux papers dans ChromaDB aegis_bibliography
    ↓
Prochaine fiche : SCIENTIST --multi-collection → refs enrichies
    ↓
Nouvelles fiches identifient nouveaux gaps → cycle reprend
```

La fiche-attaque est un **producteur de gaps** pour le research-director.
Le research-director est un **résolveur de gaps** pour la fiche-attaque.
`research_requests.json` est l'interface partagée entre les deux skills.
