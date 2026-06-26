# Doc Writer Swarm — Phase 3 (3 Agents + RETEX Synthesis)
# Référencé par : SKILL.md Phase 3

## Architecture

```
Phase 3 Doc Writer
    │
    ├─(parallèle)─┬── Scientist sub    : ChromaDB gap → WebSearch → traces → seed
    │             ├── Mathematician    : SVC + DY-AGENT + formal_framework update
    │             └── Red Team IA     : README ×4 + RETEX block + chain coverage
    │
    └─(séquentiel)── RETEX Synthesis  : merge anomalies → auto-fix → confirmer clean
```

Tous les agents reçoivent le même bloc CONTEXT :
```
CONTEXT:
  scenario_id:      {scenario_id}
  attack_type:      {attack_type}
  target_delta:     {target_delta}
  conjecture:       {conjecture}
  chain_id:         {chain_id}
  svc_actual:       {svc_actual}
  eval_verdict:     {EFFECTIVE|WEAK_RETAINED|SKIPPED}
  scientist_output: {SCIENTIST_OUTPUT de Phase 1a}
  eval_retex:       {EVAL_LOOP_RETEX de Phase 2.5}
```

System prompt pour tous les agents : `references/agents/autonomous-agent-binary.md`

---

## Agent 1 — Scientist sub (haiku)

**Templates** : `references/templates/websearch-trace.md`

**Objectif** : Vérifier la couverture ChromaDB, combler les gaps, laisser des traces permanentes.

### Step 1 — Gap check

```bash
curl -s "http://localhost:8042/api/redteam/seed-rag/check/{scenario_id}?collection=aegis_corpus"
```

- `gap_detected: false` → écrire trace "skipped: coverage sufficient" → aller à Step 3
- `gap_detected: true` → exécuter Step 2
- API offline → supposer gap_detected=true

### Step 2 — WebSearch (3 requêtes)

```
Q1 : "{clinical_context}" "{attack_type}" LLM security 2024 2025
Q2 : MITRE ATT&CK "{scenario technique}" medical device
Q3 : "{conjecture topic}" formal verification adversarial robustness
```

Pour chaque requête : écrire une trace avec `references/templates/websearch-trace.md`.
**La trace est OBLIGATOIRE même pour les résultats nuls.** Appender à :
```
research_archive/data/references/scenario_{scenario_id}_refs.md
```

### Step 3 — Seed de nouvelles refs dans ChromaDB

Si Step 2 a trouvé du nouveau contenu :
```bash
python backend/seed_rag.py \
  --file "research_archive/data/references/scenario_{scenario_id}_refs.md" \
  --collection aegis_corpus --type reference \
  --source "scientist_phase3_{scenario_id}"
```

### Anomalies détectées par Scientist

| Code | Condition | Auto-corrigeable ? |
|------|-----------|-------------------|
| BROKEN_URL | URL 404 ou timeout | Non — signaler seulement |
| DUPLICATE_REF | Même URL, clé BibTeX différente | Non — signaler seulement |
| MISSING_BIBTEX | Source sans DOI/info citable | Non — signaler seulement |
| GAP_COVERAGE | gap_detected=true après seeding | Réessayer seed une fois |

### Output

```
SCIENTIST_P3_REPORT:
  gap_detected:   {true|false}
  searches_run:   {N}
  new_refs_found: {N}
  bib_keys_added: [{keys}]
  rag_seeded:     {true|false}
  anomalies:      [{code, detail}]
```

---

## Agent 2 — Mathematician (opus)

**Templates** : `references/templates/formal-framework-entry.md`

**Objectif** : Valider et mettre à jour la notation formelle dans `formal_framework_complete.md`.

### Step 1 — Vérifier SVC via compute_svc()

```bash
cd backend && python -c "
from agents.security_audit_agent import compute_svc
from scenarios import get_all_scenarios
s = next(x for x in get_all_scenarios() if x.id == '{scenario_id}')
msg = s.steps[0].message if s.steps else ''
result = compute_svc(msg, '{attack_type}')
print(result)
"
```

Comparer la valeur retournée avec `svc_actual`. Écart > 0.05 → ANOMALY:SVC_DISCREPANCY.

### Step 2 — Identifier les gaps de spec

- d4=0 → ANOMALY:ALLOWED_SPEC_GAP — identifier la `forbidden_directive` manquante
- d3=0 → ANOMALY:DEVIATION_MARKER_GAP — identifier le pattern regex manquant

### Step 3 — Mettre à jour formal_framework_complete.md

Utiliser le template `references/templates/formal-framework-entry.md`.

```bash
grep -n "{scenario_id}" research_archive/manuscript/formal_framework_complete.md
```

- Entrée existante → mettre à jour le tableau SVC et les champs gap
- Entrée manquante + conjecture C1/C2 → ajouter une nouvelle entrée dans la section correcte

**Notation obligatoire** : toujours `Reachable(M,i)` avec parenthèses, jamais `Reachable_M(i)`.
`Sep(M) = TV(P_injected, P_null)` où TV = Total Variation distance.
Symboles Unicode : δ⁰ δ¹ δ² δ³ (jamais δ⁰/1/2/3 en ASCII).

### Anomalies détectées par Mathematician

| Code | Condition | Auto-corrigeable ? |
|------|-----------|-------------------|
| SVC_DISCREPANCY | |prédit - actuel| > 0.05 | Non — documenter seulement |
| ALLOWED_SPEC_GAP | d4=0, forbidden_directive manquante | **OUI** |
| DEVIATION_MARKER_GAP | d3=0, pattern regex manquant | **OUI** |
| SEP_M_INVALID | N<30 mais statistically_valid=true | **OUI** |
| NOTATION_ERROR | Mauvaise formule DY-AGENT dans le doc | **OUI** |

### Output

```
MATHEMATICIAN_P3_REPORT:
  svc_validated:         {true|false}
  svc_discrepancy:       {delta ou "none"}
  formal_updated:        {true|false}
  allowed_spec_gaps:     [{directive_name}]
  deviation_marker_gaps: [{pattern, description}]
  anomalies:             [{code, detail}]
```

---

## Agent 3 — Red Team IA Specialist (sonnet)

**Templates** : `references/templates/retex-block.md`, `references/templates/readme-update.md`

**Objectif** : Documentation opérationnelle — README, RETEX, couverture des chains.

### Step 1 — README ×4

Utiliser `references/templates/readme-update.md`. Mettre à jour et vérifier la cohérence :

```bash
python -c "from backend.scenarios import get_all_scenarios; print(len(get_all_scenarios()))"
```

Mettre à jour les 4 fichiers. Lancer la vérification de cohérence. Logger COUNT_MISMATCH si trouvé.

### Step 2 — Couverture des chains

```bash
python -c "
from backend.scenarios import get_all_scenarios
from backend.agents.attack_chains import CHAIN_REGISTRY
used = set(
    step.chain_id for s in get_all_scenarios()
    for step in s.steps if getattr(step, 'chain_id', '')
)
print('chains_used:', sorted(used))
print('orphans:', sorted(set(CHAIN_REGISTRY.keys()) - used))
"
```

`chain_first_use=true` si `{chain_id}` n'était pas présent dans `used` précédemment.

### Step 3 — Bloc RETEX

Utiliser `references/templates/retex-block.md`. Appender à :
```
research_archive/data/references/scenario_{scenario_id}_refs.md
```

### Step 4 — Confirmation RAG (si chain_id contient "rag")

```bash
curl -s "http://localhost:8042/api/redteam/seed-rag/check/{scenario_id}?collection=medical_multimodal"
```

`gap_detected: true` → ANOMALY:RAG_NOT_SEEDED.

### Anomalies détectées par Red Team IA

| Code | Condition | Auto-corrigeable ? |
|------|-----------|-------------------|
| COUNT_MISMATCH | Count README ≠ get_all_scenarios() | **OUI** |
| RAG_NOT_SEEDED | chain_id=rag* mais gap_detected=true | **OUI** |
| CHAIN_ORPHAN | chain_id non utilisé nulle part | Non — signaler seulement |

### Output

```
REDTEAM_IA_P3_REPORT:
  readme_updated:   {true|false}
  count_new:        {N}
  chain_first_use:  {true|false}
  retex_written:    {true|false}
  rag_confirmed:    {true|false}
  anomalies:        [{code, detail, fixed}]
```

---

## RETEX Synthesis (séquentiel — après les 3 agents)

Fusionner tous les rapports d'anomalies. Appliquer toutes les corrections automatiques. Confirmer clean.

### Step 1 — Fusion des anomalies

```
ALL_ANOMALIES = [
  ...SCIENTIST_P3_REPORT.anomalies,
  ...MATHEMATICIAN_P3_REPORT.anomalies,
  ...REDTEAM_IA_P3_REPORT.anomalies
]
```

### Step 2 — Table d'auto-corrections (appliquer TOUTES — ne pas différer)

#### ALLOWED_SPEC_GAP
Trouver la dataclass `AllowedOutputSpec` dans `backend/agents/security_audit_agent.py`.
Ajouter la directive manquante dans `forbidden_directives` :

```python
forbidden_directives=frozenset([
    ...,
    "{missing_directive}",  # NEW — corrige d4=0 pour {scenario_id}
])
```

Re-lancer `compute_svc()` et vérifier que d4 > 0.

#### DEVIATION_MARKER_GAP
Trouver le dict `_DEVIATION_MARKERS` dans `backend/agents/security_audit_agent.py`.
Ajouter le pattern manquant :

```python
_DEVIATION_MARKERS = {
    ...,
    r"{missing_regex}": "{description}",  # NEW — corrige d3=0 pour {scenario_id}
}
```

Re-lancer `compute_svc()` et vérifier que d3 > 0.

#### COUNT_MISMATCH
Corriger le(s) fichier(s) README avec `references/templates/readme-update.md`.
Re-lancer la vérification de cohérence.

#### RAG_NOT_SEEDED
```bash
python backend/seed_rag.py --scenario {scenario_id} --chain-id {chain_id}
```
Vérifier que gap_detected=false.

#### SEP_M_INVALID
Dans `formal_framework_complete.md` : mettre `statistically_valid: false` où N<30.

#### NOTATION_ERROR
Remplacer les occurrences ASCII (`δ⁰`, `δ¹`, etc.) par Unicode (δ⁰, δ¹, δ², δ³).

### Step 3 — Vérifier chaque correction

Pour chaque anomalie corrigée : re-lancer la détection. Marquer `fixed: true` si OK.
Si toujours en échec après 1 réessai : `fixed: false, escalate: true`.

### Step 4 — Bloc de synthèse final

Appender à `research_archive/data/references/scenario_{scenario_id}_refs.md` :

```markdown
## RETEX Synthesis — Phase 3 Doc Writer Swarm — {YYYY-MM-DD}

Agents : Scientist sub, Mathematician, Red Team IA
Anomalies : {N total} détectées | {N} auto-corrigées | {N} escaladées

| Agent | Code | Détail | Corrigé |
|-------|------|--------|---------|
| {agent} | {code} | {detail} | OUI / NON |

SVC post-correction : {svc_after} (était {svc_before})
  d3 = {d3_after} (était {d3_before})
  d4 = {d4_after} (était {d4_before})

RETEX_STATUS : CLEAN | ISSUES_REMAINING
Prérequis restants pour campagne formelle : {liste ou "aucun"}
```

**RETEX_STATUS: CLEAN** signifie que `run_formal_campaign()` peut se lancer sans intervention manuelle.
**RETEX_STATUS: ISSUES_REMAINING** liste les anomalies escaladées que l'utilisateur doit résoudre.

---

## Export JSONL (observabilité)

Après RETEX Synthesis, exporter le journal consolidé en :
`research_archive/data/references/scenario_{scenario_id}_swarm_journal_{date}.jsonl`

Format par entrée : voir `references/agents/autonomous-agent-binary.md` §Journal d'action format externe.

---

## Carte des templates

| Template | Utilisé par | Objectif |
|----------|-------------|---------|
| `references/templates/websearch-trace.md` | Scientist sub | Chaque trace de recherche |
| `references/templates/retex-block.md` | Red Team IA | RETEX principal + log anomalies |
| `references/templates/formal-framework-entry.md` | Mathematician | Entrée formal_framework |
| `references/templates/readme-update.md` | Red Team IA | Vérification cohérence count |
| `references/templates/scenario-help-modal.md` | Frontend Dev (Phase 2a) | Bloc case JSX |
| `references/agents/autonomous-agent-binary.md` | Tous les agents Phase 3 | Binaire boucle agentique |
| `references/methodology/eval-loop.md` | Phase 2.5 | Algorithme quick-test |
