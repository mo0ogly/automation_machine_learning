# Research Cycle — Référence Opérationnelle

Consommé par le research-director pendant la phase PLAN.
Contient les détails opérationnels que le SKILL.md référence mais ne répète pas.

---

## 1. Critères de priorisation — Protocole de décision

Les critères sont évalués dans l'ordre strict ci-dessous.
**Le premier qui discrimine l'emporte** — ne pas passer au suivant si le précédent a tranché.

### Critère 1 — Impact sur les conjectures (poids dominant)

**Règle** : prioriser les conjectures à confiance < 10/10 ou les candidates non encore validées.
Une conjecture fermée (10/10) ne génère plus de priorité de recherche.

| Conjecture | Confiance | Statut | Requests qui la font avancer |
|-----------|-----------|--------|------------------------------|
| C1 — Insuffisance δ¹ | 10/10 | FERMÉE | Aucune priorité — déjà prouvée |
| C2 — Nécessité δ³ | 10/10 | FERMÉE | Aucune priorité — déjà prouvée |
| C3 — {description} | {X}/10 | ACTIVE | {liste RR} |
| C4 — {description} | {X}/10 | ACTIVE | {liste RR} |
| C5 — {description} | {X}/10 | ACTIVE | {liste RR} |
| C6 — Défenses intra-LLM vs extra-LLM | {X}/10 | CANDIDATE | RR-004 (CSV code injection), RR-005 (hybridation) |
| C7 — {description} | {X}/10 | CANDIDATE | {liste RR} |

> **Mise à jour** : ce tableau est maintenu par SCIENTIST (bibliography-maintainer)
> dans `discoveries/CONJECTURES_TRACKER.md`. Le research-director lit le tracker,
> pas ce fichier, pour les scores courants.

**Application** :
- Si deux requests impactent des conjectures différentes :
  choisir celle dont la conjecture a le score le plus bas (le plus à améliorer)
- Si même score : choisir la conjecture candidate sur la conjecture active
- Si même statut : passer au Critère 2

### Critère 2 — Dépendances entre requests

**Règle** : traiter d'abord les requests qui en débloquent d'autres.

**Format de dépendance dans `research_requests.json`** :
```json
{
  "id": "RR-001",
  "blocks": ["RR-022"],
  "blocked_by": []
}
```

**Graphe de dépendances connu (mise à jour dynamique) :**
- RR-001 (MSBE) → bloque → fiche #22 (Sep(M) vectoriel)
- RR-002 (self-query multi-framework) → bloque → généralisation fiche #19
- RR-005 (hybridation #13 × #15) → nécessite → fiches #13 ET #15 complètes

**Application** : si RR-A bloque RR-B et que RR-B est critique, traiter RR-A en priorité
même si son propre impact sur les conjectures est moindre.

### Critère 3 — Coût vs bénéfice

**Règle** : à impact conjecture égal, préférer le type le moins coûteux.

| Type | Coût estimé | Skills impliquées | Bénéfice |
|------|------------|------------------|---------|
| `literature_search` | ~5 min | bibliography-maintainer | Papers + RAG chunks + références |
| `experiment` | ~15 min | aegis-prompt-forge + backend | Données empiriques (ASR, Sep(M), SVC) |
| `fiche_update` | ~20 min | fiche-attaque (3 agents) | Fiche enrichie + nouveaux gaps identifiés |
| `fiche_generation` | ~25 min | fiche-attaque (3 agents + assemblage) | Nouvelle fiche complète (11 sections) |

**Application** : si deux requests ont même impact et aucune dépendance bloquante,
choisir le type le moins coûteux — literature_search avant experiment avant fiche_update avant fiche_generation.

### Critère 4 — Maturité des chapitres

**Règle** : si critères 1-3 ne discriminent pas, prioriser les chapitres à maturité < 50%.
Un chapitre à 40% non comblé avant la deadline bloque la soutenance.

| Chapitre | Maturité actuelle | Actions prioritaires |
|---------|-----------------|---------------------|
| Ch.1 | {X}% | {liste RR} |
| Ch.2 | {X}% | {liste RR} |
| Ch.3 | {X}% | {liste RR} |
| Ch.4 | {X}% | {liste RR} |
| Ch.5 | {X}% | {liste RR} |
| Ch.6 | {X}% | {liste RR} |

> **Mise à jour** : maturité lue depuis `_staging/briefings/DIRECTOR_BRIEFING_RUN{XXX}.md` §7.

---

## 2. Format complet des research requests

```json
{
  "id": "RR-XXX",
  "source_fiche": 22,
  "type": "literature_search | experiment | fiche_update | fiche_generation",
  "query": "Description précise de ce qu'on cherche",
  "priority": "critique | haute | moyenne | basse",
  "status": "pending | in_progress | resolved | partial | blocked",
  "conjecture_impact": ["C3", "C6"],
  "blocks": ["RR-022"],
  "blocked_by": [],
  "attempts": 0,
  "created": "YYYY-MM-DD",
  "last_updated": "YYYY-MM-DD",
  "resolved_by": null,
  "notes": "Contexte supplémentaire, résultats partiels, approches échouées"
}
```

### Cycle de vie d'un statut

```
pending
  ↓ (delegation émise)
in_progress
  ↓ (critères de complétion atteints)     ↓ (résultats insuffisants)     ↓ (4 tentatives échouées)
resolved                                   partial                         blocked
                                            ↓
                                     sous-request RR-{XXX+1} créée
```

**Définitions strictes :**
- `pending` : pas encore traité — dans la file, aucune action engagée
- `in_progress` : délégation émise, résultat en attente
- `resolved` : **tous** les critères de complétion du type atteints (cf. §3)
- `partial` : résultats non nuls mais insuffisants — au moins un critère non atteint
- `blocked` : 4 tentatives échouées, toutes avec approche différente — escalade obligatoire

---

## 3. Critères de complétion — Définition de "resolved"

Un gap est `resolved` **uniquement** quand **tous** les critères ci-dessous sont atteints.
Un seul critère manquant = `partial`, pas `resolved`.

### `literature_search` → resolved si :
1. ≥ 2 chunks pertinents dans ChromaDB (`query_chromadb.py --multi-collection`)
2. Les chunks proviennent de **papers différents** (pas 2 chunks du même paper)
3. Distance cosinus < 1.5 pour chaque chunk retenu
4. Les chunks sont sémantiquement pertinents pour la query de la request (évaluation EVALUATE)

**Vérification** : `query_chromadb.py "{query}" --multi-collection`
**Signal d'échec** : 0 chunk, ou tous les chunks du même paper, ou distance > 1.5

### `experiment` → resolved si :
1. Un template ou scénario a été créé dans le backend AEGIS
2. L'expérience peut être exécutée (endpoint API accessible et répond 200)
3. Les résultats sont **mesurables** : ASR défini, Sep(M) calculable (N ≥ 30), SVC scorable

**Vérification** : `batch_fiches.py list` + appel endpoint `/api/redteam/attack`
**Signal d'échec** : endpoint inaccessible, métriques non mesurables, template incomplet

### `fiche_update` → resolved si :
1. La fiche a été regénérée avec le nouveau contexte RAG
2. La Section 11 cite ≥ 1 nouvelle référence (arXiv ID ou DOI) absente de la version précédente
3. `fiche_index.json` affiche `last_updated` postérieur à la date de création de la RR

**Vérification** : Read `fiche_index.json` → champ `last_updated` et `section_11_refs`
**Signal d'échec** : date inchangée, Section 11 identique à l'ancienne version

### `fiche_generation` → resolved si :
1. Le fichier `.docx` existe dans le répertoire des fiches
2. Les 11 sections sont non-vides (pas de placeholder `[À COMPLÉTER]`)
3. `fiche_index.json` affiche le statut `done` pour cette fiche
4. La fiche est seedée dans ChromaDB (`seed_fiches_to_rag.py` exécuté avec succès)

**Vérification** : Read `fiche_index.json` → `status: "done"` + `seeded: true`
**Signal d'échec** : sections vides, fichier manquant, non seedé

---

## 4. Mapping skills → commandes — Référence complète

### bibliography-maintainer

| Mode | Quand | Commande exacte |
|------|-------|----------------|
| `incremental` | Chercher des papers récents sur un sujet spécifique | `/bibliography-maintainer incremental` + termes de recherche |
| `research_axes` | Regénérer les axes de recherche globaux après ajout massif | `/bibliography-maintainer research_axes` |
| `rag_refresh` | Après ajout massif de papers (> 10 nouveaux) | `/bibliography-maintainer rag_refresh` |
| `analyze_only` | Analyser des papers déjà téléchargés sans nouvelle recherche | `/bibliography-maintainer analyze_only` |

**Paramètres de recherche à fournir pour `incremental` :**
```
Termes principaux  : {2-4 mots-clés précis en anglais}
Termes alternatifs : {2-3 synonymes ou formulations proches}
Plage temporelle   : {YYYY} à {YYYY}
Conjecture cible   : {C_N}
Gap cible          : {G-XXX}
```

### aegis-prompt-forge

| Mode | Quand | Paramètres requis |
|------|-------|------------------|
| `FORGE` | Créer un nouveau prompt d'attaque pour une expérience | `attack_type` + `chain_id` + `target_delta` + `conjecture` + `clinical_context` |
| `AUDIT` | Évaluer et améliorer un prompt existant | Fichier `.md` ou `.json` du prompt à auditer |
| `RETEX` | Analyser les résultats d'une campagne | Fichier `campaign_*.json` |
| `SYSTEM` | Améliorer le system prompt de la cible | System prompt actuel + `target_sep_range` |

**Pour une délégation FORGE, fournir :**
```
attack_type    : injection | rule_bypass | prompt_leak
chain_id       : {identifiant dans le registre backend}
objective      : {violation cible précise}
target_delta   : delta1 | delta2 | delta3
conjecture     : C{N} | null
clinical_context: {scénario chirurgical}
turn_position  : single | multi
```

### fiche-attaque

| Commande | Quand | Paramètres |
|---------|-------|-----------|
| `/fiche-attaque {num}` | Générer ou régénérer une fiche spécifique | Numéro de la fiche (1-97) |
| `/fiche-attaque remaining` | Générer toutes les fiches manquantes | Aucun |
| `/fiche-attaque status` | Vérifier la progression sans action | Aucun |

---

## 5. Gestion des échecs — Protocole de REPLAN

**Règle absolue** : ne jamais retenter la même action identiquement.
Changer au moins un paramètre substantiel à chaque tentative.

| Tentative | Résultat | Action obligatoire |
|-----------|---------|-------------------|
| 1ère | FAILURE | Déléguer avec les paramètres initiaux |
| 2ème | FAILURE | **Changer les termes** (synonymes, langue, niveau d'abstraction) |
| 3ème | FAILURE | **Changer de type** (ex: `experiment` si `literature_search` échoue 2 fois) |
| 4ème | FAILURE | **Changer de skill** + reformuler l'objectif depuis les bases |
| 5ème | — | `blocked` — escalade obligatoire avec diagnostic complet des 4 tentatives |

> **Note** : le champ `attempts` dans `research_requests.json` trace le compteur.
> Un `blocked` sans `attempts: 4` est invalide — vérifier avant de marquer.

**Alternatives valides pour chaque type :**

Pour `literature_search` qui échoue :
- Tentative 2 : termes anglais alternatifs + plage temporelle élargie
- Tentative 3 : passer à `experiment` (créer la preuve empirique si la littérature manque)
- Tentative 4 : passer à `fiche_update` (enrichir depuis les papers déjà indexés)

Pour `experiment` qui échoue :
- Tentative 2 : changer `target_delta` ou `attack_type`
- Tentative 3 : passer à `literature_search` (chercher des approches alternatives)
- Tentative 4 : passer à `fiche_generation` (documenter le gap comme découverte)

**Format diagnostic BLOCKED :**
```
BLOCKED — RR-{XXX} — {date}
Tentative 1 : {type} — {commande} — Résultat : {ce qui s'est passé}
Tentative 2 : {type} — {commande} — Résultat : {ce qui s'est passé}
Tentative 3 : {type} — {commande} — Résultat : {ce qui s'est passé}
Tentative 4 : {type} — {commande} — Résultat : {ce qui s'est passé}
Hypothèse   : {pourquoi ce gap résiste — manque de littérature ? problème de spec ?}
Recommandation utilisateur : {action suggérée — reformuler le gap, attendre nouveaux papers, etc.}
Impact thèse : {si ce gap reste bloqué, quel chapitre ou conjecture est affecté ?}
```

---

## 6. Gestion des conjectures candidates

Une conjecture candidate (ex: C6) suit un cycle de validation formel.

### Cycle de vie

```
HYPOTHÈSE (< 7/10, aucune evidence formelle)
    ↓ (≥ 1 paper ou expérience → score ≥ 7/10)
CANDIDATE (7-8/10, evidence partielle)
    ↓ (≥ 2 papers convergents ou réplication expérimentale → score ≥ 9/10, SUPERVISED)
ACTIVE (9/10, forte evidence)
    ↓ (preuve formelle + réplication → 10/10, SUPERVISED)
FERMÉE (10/10, prouvée)
    OU
    ↓ (≥ 3 papers contredisent, score < 5/10, SUPERVISED)
INVALIDÉE (archivée, explications conservées)
```

### Règles de transition

| Transition | Condition | Autonomie |
|-----------|-----------|-----------|
| HYPOTHÈSE → CANDIDATE | ≥ 1 paper `[ARTICLE VÉRIFIÉ]` ou `[EXPERIMENTAL]` supportant | AUTONOMOUS |
| CANDIDATE → ACTIVE | ≥ 2 sources indépendantes convergentes, cross-validées par SCIENTIST | SUPERVISED |
| ACTIVE → FERMÉE | Preuve formelle publiée + réplication expérimentale AEGIS | SUPERVISED |
| Toute → INVALIDÉE | ≥ 3 papers contradictoires, score < 5/10 après évaluation | SUPERVISED |
| Modification ±1 | Evidence additionnelle d'un paper | AUTONOMOUS |
| Modification ±2 ou plus | Changement majeur de statut | SUPERVISED |

### Actions research-director par statut

| Statut conjecture | Action prioritaire |
|-----------------|-------------------|
| CANDIDATE sans validation | Créer RR de type `literature_search` pour chercher evidence convergente |
| CANDIDATE avec 1 paper | Créer RR de type `experiment` pour réplication |
| ACTIVE sans réplication | Créer RR de type `experiment` pour confirmer |
| FERMÉE | Aucune priorité — vérifier si des papers la contredisent |
| INVALIDÉE | Documenter dans THESIS_GAPS.md les implications pour la thèse |

---

## 7. Intégration moteur génétique AEGIS

Quand un gap suggère une hybridation entre deux fiches (type `experiment` avec `hybridation`) :

### Protocole de croisement

```
OBJECTIVE : croisement {parent_A} × {parent_B}

DECOMPOSE :
  Sous-tâche 1 — Vérification parents
    Type       : observation
    Action     : lire fiche_index.json → SVC de #A et #B
    Critère    : les deux fiches statut "done" et SVC > 0.5
    Autonomie  : AUTONOMOUS
    Coût       : ~2 min

  Sous-tâche 2 — Forge du template hybride
    Type       : experiment
    Action     : /aegis-prompt-forge FORGE
    Paramètres : attack_type hérité du parent dominant
                 chain_id : "{A}x{B}"
                 clinical_context : fusion des contextes parents
    Autonomie  : AUTONOMOUS
    Coût       : ~15 min

  Sous-tâche 3 — Analyse du résultat hybride
    Type       : fiche_update
    Action     : /fiche-attaque {num_nouveau}
    Critère    : SVC hybride calculé
    Autonomie  : AUTONOMOUS
    Coût       : ~20 min

  Sous-tâche 4 — Comparaison SVC
    Type       : évaluation
    Action     : comparer SVC hybride vs max(SVC_A, SVC_B)
    Critère    : SVC hybride > max(parents) = émergence confirmée
    Autonomie  : AUTONOMOUS
    Coût       : ~2 min

  Sous-tâche 5 — Mise à jour conjectures
    Type       : mise à jour CONJECTURES_TRACKER
    Action     : si SVC hybride > max(parents) → supporte C{N} [EXPERIMENTAL]
    Autonomie  : SUPERVISED si |Δ score| ≥ 2

PLAN : séquence 1→2→3→4→5 (dépendances strictes)
```

### Critère de succès du croisement

```
Émergence confirmée : SVC_hybride > max(SVC_parent_A, SVC_parent_B)
Émergence neutre    : SVC_hybride ≈ max(parents) ± 0.1
Régression          : SVC_hybride < min(SVC_parent_A, SVC_parent_B)
```

L'émergence confirmée supporte les conjectures sur la composabilité des vecteurs d'attaque.
La régression supporte les conjectures sur l'interférence entre familles d'attaque.
Les deux sont des résultats valides scientifiquement — les logguer avec `[EXPERIMENTAL]`.

---

## 8. Audit des rapports sous-skills — Protocole systématique

À chaque ouverture de session, avant DECOMPOSE, auditer les rapports non traités.

### Rapports à auditer

| Source | Fichier | Fréquence | Action si non traité |
|--------|---------|-----------|---------------------|
| bibliography-maintainer | `_staging/briefings/DIRECTOR_BRIEFING_RUN{XXX}.md` | Après chaque RUN | Créer RR pour chaque action P0/P1 non enregistrée |
| aegis-prompt-forge | `_staging/PROMPT_FORGE_BRIEFING_{date}.md` | Après chaque campagne | Créer RR pour patterns à explorer, prompts à reforger |
| fiche-attaque | `fiche_index.json` Section 11 | Après chaque fiche générée | Créer RR pour les gaps Section 11.4 non enregistrés |

### Format de log d'audit

```
AUDIT RAPPORT — {filename} — {date d'audit}
Date rapport   : {date de production du rapport}
Actions totales: {N} recommandations dans le rapport
Déjà en file   : {M} déjà dans research_requests.json
Nouvelles RR   : {N-M} créées cette session
  → RR-{XXX} : {description courte} — {priorité}
  → RR-{YYY} : {description courte} — {priorité}
Conjectures    : {liste des scores modifiés ou AUCUN}
Gaps           : {liste des gaps ouverts/clos ou AUCUN}
```

### Règle de non-duplication

Avant de créer une RR depuis un rapport, vérifier dans `research_requests.json` :
- Même `query` ou `source_fiche` déjà présente ? → ne pas dupliquer, noter dans le log
- Même objectif sous formulation différente ? → fusionner en enrichissant les `notes`
- Action déjà `resolved` ? → vérifier si le résultat couvre bien la recommandation

---

## 9. Scripts disponibles — Référence

| Script | Phase | Usage | Chemin |
|--------|-------|-------|--------|
| `query_chromadb.py "{query}" --multi-collection` | OBSERVE | Vérifier chunks dans les 2 collections | `.claude/skills/fiche-attaque/scripts/` |
| `query_chromadb.py "{query}" --collection aegis_corpus` | OBSERVE | Corpus fiches uniquement | idem |
| `query_chromadb.py "{query}" --collection aegis_bibliography` | OBSERVE | Bibliographie uniquement | idem |
| `batch_fiches.py list` | OBSERVE | Lister fiches pending/done | idem |
| `batch_fiches.py prepare --num XX` | PLAN | Préparer métadonnées fiche | idem |
| `seed_fiches_to_rag.py --also-bibliography` | ACT | Seeder fiches dans ChromaDB | idem |

### Requête LITREVIEW — ChromaDB direct (sous-phase §5bis)

Utilisée pendant la sous-phase LITREVIEW, avant DECOMPOSE. Ne pas substituer par `query_chromadb.py` (cible multi-collection) ni par `retrieve_similar_notes.py` (cible `aegis_research_notes`).

```python
import chromadb
from chromadb.utils import embedding_functions

client = chromadb.PersistentClient(path="backend/chroma_db")
emb_fn = embedding_functions.DefaultEmbeddingFunction()
col = client.get_collection("aegis_bibliography", embedding_function=emb_fn)
hits = col.query(query_texts=[rr_title + " " + rr_keywords], n_results=5)
```

Seuils d'interprétation : sim ≥ 0.80 → DUPLICATE (HALT), 0.55 ≤ sim < 0.80 → BUILDS_ON_EXISTING, < 0.40 → NEW_GROUND.

### Tool-hits log — lecture avant RR

Avant de lancer une nouvelle RR, lire les 20 dernières lignes de `.claude/skills/research-director/memory/tool_hits.jsonl`. Si un pattern similaire (même `tool`, requête proche) affiche `hit_quality: "high"`, réutiliser la query-template avec substitution des keywords. Durée max : 10 % du budget RR.

**Format de sortie `query_chromadb.py`** (utilisé dans OBSERVE) :
```
Query: "{query}"
Collection: multi (aegis_corpus + aegis_bibliography)
Results: {N} chunks found

[1] distance=1.05 | paper=arXiv:2403.XXXXX | chunk_type=analysis
    {extrait du chunk}

[2] distance=1.23 | paper=arXiv:2405.XXXXX | chunk_type=formula
    {extrait du chunk}
```

Critère de pertinence : distance < 1.5 ET chunk_type pertinent pour la query.
