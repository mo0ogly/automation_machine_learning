# AEGIS Research Lab — Protocole Opérationnel Détaillé

Consommé par le skill `aegis-research-lab` (apex) pendant les phases
CORRELATE et SYNTHESIZE. Ce fichier est **lu à la demande**, pas chargé par défaut.

---

## 1. Matrices de corrélation — Cas d'usage AEGIS

### 1.1 — Matrice Résultats empiriques × Conjectures

**Objectif** : détecter quelles conjectures sont supportées/affaiblies par les
résultats empiriques du cycle.

**Sources d'entrée** :
- Campagnes dans `research_archive/data/raw/` (lire les 5 dernières)
- Rapports `/validation-pipeline` du cycle
- Rapports `/research-director` experiment du cycle

**Schéma** :
```
                    | C1 | C2 | C3 | C4 | C5 | C6 | C7 |
Campagne mass_N100 | ↑↑ |  = | ↑  |  = |  = |  = |  = |
THESIS-002 G-032   |  = |  = |  = | ↑↑ |  = |  = |  = |
Validation G-037   |  = |  = | ↑  |  = |  = |  = |  = |
Paper RUN-009 SEAL |  = | ↑  |  = |  = |  = |  = |  = |
```

**Règle de remplissage** :
- `↑↑` : ASR_AFTER < ASR_BEFORE × 0.2 (réduction ≥ 80%) ET la défense cible
  explicitement la conjecture
- `↑` : réduction 50-79%, OU paper convergent mais non empirique
- `=` : sans effet significatif ou non pertinent
- `↓` : résultat qui affaiblit la conjecture (ex: défense qui augmente l'ASR)
- `↓↓` : contradiction forte (preuve empirique qu'une conjecture est fausse)

**Seuil d'action** :
- ≥ 2 entrées `↑↑` convergentes sur la même conjecture → proposer transition
  de statut (CANDIDATE → ACTIVE, ou ACTIVE → FERMÉE) en SUPERVISED
- 1 entrée `↓↓` → **HALT** + escalade humaine, possible bug ou invalidation

### 1.2 — Matrice Gaps × Chapitres thèse

**Objectif** : détecter les chapitres qui avancent (ou pas).

**Entrées** :
- Lire `_staging/briefings/DIRECTOR_BRIEFING_RUN*.md` §7 pour la maturité par chapitre
- Lire THESIS_GAPS.md pour le mapping gap → chapitre
- Lire les fiches modifiées ce cycle

**Schéma** :
```
Gap      | Ch1 Intro | Ch2 δ-framework | Ch3 attaques | Ch4 défenses | Ch5 AEGIS | Ch6 eval |
G-032    |           |                 |      X       |      X       |           |          |
G-037    |           |                 |      X       |              |     X     |          |
G-041    |           |        X        |              |      X       |           |          |
G-045    |           |                 |              |              |     X     |          |
```

**Règle** :
- Si un gap est validé empiriquement (`aegis-validation-pipeline` verdict
  VALIDÉ) → les chapitres concernés gagnent en maturité
- Si aucun gap n'avance sur le chapitre le moins mature → c'est le trou
  prioritaire du prochain cycle

### 1.3 — Matrice Findings × Nouveaux gaps potentiels

**Objectif** : détecter des patterns d'intersection — gaps qui émergent de la
corrélation entre deux domaines.

**Exemple réel** :
```
Finding A (Campagne G-032) : CoT hijacking bloqué post-output mais CoT buried
                              reste visible dans <think>
Finding B (Paper P094)     : attention dilution scale avec long CoT
                              (Zhao et al. 2026)
----
Intersection : un attaquant peut bypass la défense en placant la payload
               à mi-<think> plutôt qu'en fin.
→ Nouveau gap candidat : G-0XX "mid-think payload placement evades
                                  post-output oracle"
```

**Process** :
1. Pour chaque paire (finding_A, finding_B) où A provient d'un bac différent de B
2. Demander : "Y a-t-il une attaque ou défense qui exploite *les deux* ?"
3. Si oui → candidat `G-XXX` à proposer (SUPERVISED via research-director)

---

## 2. Format complet de la note de recherche

### 2.1 — Structure

12 sections obligatoires (cf. SKILL.md §6.1). Aucune n'est optionnelle.
Si une section est vide, écrire "Aucun résultat ce cycle" — ne pas la supprimer.

### 2.2 — Règles de prose

**Ton** : prose académique sobre. Pas de marketing. Pas de "révolutionnaire",
"breakthrough", "state-of-the-art". Préférer "ce cycle confirme", "les données
suggèrent", "reste à valider".

**Chiffres** : toujours avec unité et N.
- Bien : "ASR 12.3% (N=30, Wilson 95% CI [0.04, 0.28])"
- Mal  : "L'ASR est bas"

**Tags** : obligatoires sur chaque affirmation empirique ou factuelle.
- `[ARTICLE VÉRIFIÉ]` : paper avec arXiv/DOI confirmé
- `[PREPRINT]` : paper trouvé mais non peer-reviewed
- `[EXPERIMENTAL]` : résultat de campagne AEGIS (préciser N, ASR, Wilson CI)
- `[HYPOTHÈSE]` : inférence sans publication
- `[CALCUL VÉRIFIÉ]` : formule dérivée mathématiquement

**Longueur** : viser 400-1200 mots. Une note trop courte ne raconte rien, une
note trop longue n'est pas lue.

### 2.3 — Les sections 8, 9, 10 sont la valeur

**Section 8 — "Ce qu'on sait maintenant qu'on ne savait pas avant"**

Un paragraphe. Doit se lire en 6 mois sans contexte. Exemple :

> Avant ce cycle, l'hypothèse C3 (efficacité des défenses δ³ post-output)
> reposait sur une seule campagne (THESIS-001). La validation THESIS-002 sur
> G-032 confirme que `CoTHijackingOutputOracle` réduit l'ASR de 96.7% à 12.3%
> sur hyde (Wilson CI [0.04, 0.28], N=30) sans régression sur les autres
> chaînes. C3 passe de 7/10 à 9/10. En revanche, le paper P094 (Zhao 2026)
> montre que l'attaque peut être déplacée à mi-`<think>`, ce qui ouvre
> G-0XX — un nouveau gap que ce cycle a fait émerger.

**Section 9 — "Ce qui reste incertain"**

Honnêteté obligatoire. Les zones d'ombre ne sont pas un aveu de faiblesse —
elles guident les prochains cycles. Exemple :

> - La réduction d'ASR sur xml_agent n'a été mesurée qu'à N=30 ; un cycle
>   avec N=100 (run_mass_campaign_n100.py) reste requis pour Wilson CI
>   irréfutable (Exploitation 3).
> - G-041 (SEAL stacked ciphers) est implémenté mais la détection ROT13
>   pourrait être contournée par un shift de +3 au lieu de +13 — non testé.
> - L'impact de la défense sur la latence n'a pas été mesuré ce cycle.

**Section 10 — "Prochaine action recommandée"**

Précision maximale. Pas "faire une campagne", mais :

> Action : `run_mass_campaign_n100.py --chains xml_agent --n-trials 100`
> Justification : C3 à 9/10, passage à 10/10 requiert réplication N≥100.
> Skill cible : /validation-pipeline
> Temps estimé : ~90 min

---

## 3. Critères apex de priorisation

### 3.1 — Dette scientifique

**Définition** : un gap est en "dette scientifique" s'il est marqué `IMPLEMENTE`
mais sans bloc `THESIS-002`, `ASR_AFTER`, ou `VALIDÉ EMPIRIQUEMENT`.

**Règle** : tant qu'un gap est en dette, il reçoit un bonus de priorité de +1
cran (P2 devient P1, P1 devient P0).

**Pourquoi** : c'est la forme la plus dangereuse d'échec silencieux — du code
qui donne l'illusion de défendre sans qu'on sache si c'est vrai.

### 3.2 — Corrélation émergente

**Définition** : un nouveau gap détecté par la phase CORRELATE (intersection de
deux findings de bacs différents).

**Règle** : priorité automatique P1 le cycle qui le détecte, P2 ensuite si non
validé.

**Pourquoi** : les gaps émergents sont la preuve que la méthode apex fonctionne.
Les ignorer c'est perdre la valeur de l'apex.

### 3.3 — Protection des chaînes haute-ASR

**Définition** : chaînes avec ASR > 80% dans THESIS-001 (hyde, xml_agent).

**Règle** : toute validation ou défense sur ces chaînes a priorité absolue P0.

**Pourquoi** : ce sont les chaînes qui définissent la bimodalité D-023 — ce
sont elles qui rendent la thèse scientifiquement défendable.

---

## 4. Template du signal SESSION_COMPLETE

Fichier : `_staging/signals/SESSION_COMPLETE_{id}_{date}.json`

```json
{
  "session_id": "SESSION-043",
  "timestamp": "2026-04-10T18:23:00",
  "apex": "aegis-research-lab",
  "status": "ACHIEVED",
  "duration_minutes": 87,
  "livrables": {
    "note_recherche": "research_archive/research_notes/SESSION-043_2026-04-10.md",
    "journal_apex": "_staging/research-lab/JOURNAL_SESSION-043.jsonl"
  },
  "actions": {
    "total": 6,
    "success": 5,
    "partial": 1,
    "failed": 0
  },
  "correlations_detected": 2,
  "gaps_closed": ["G-032"],
  "gaps_new": ["G-053"],
  "conjecture_transitions": [
    {"id": "C3", "from": "8/10", "to": "9/10", "autonomy": "AUTONOMOUS"}
  ],
  "next_action": {
    "type": "validation",
    "target": "G-037",
    "skill": "/validation-pipeline",
    "estimated_minutes": 45
  },
  "drift_check": "CLEAR",
  "escalations": []
}
```

---

## 5. Protocole de gestion du contexte (offload)

Quand le contexte atteint 70% pendant une session :

1. **HALT immédiat** — ne pas démarrer une nouvelle délégation
2. **Sauvegarde partielle** : produire une note de recherche PARTIELLE dans
   `research_archive/research_notes/SESSION-{id}_{date}_PARTIAL.md`
3. **Offload** : écrire l'état courant dans
   `_staging/research-lab/CONTEXT_OFFLOAD_SESSION-{id}.md` avec :
   - Phases complétées
   - Phase en cours
   - Buffer de rapports non corrélés
4. **Signal** : émettre `_staging/signals/SESSION_SUSPENDED_{id}.json`
5. **Rapport à l'utilisateur** : "Session suspendue à {phase}. Reprise possible
   avec `/aegis-research-lab resume SESSION-{id}`."

---

## 6. Différences entre "apex skill" et les systèmes état-de-l'art

Le design de ce skill s'inspire de :

### AI Scientist v2 (Sakana AI, 2024-2025)
- **Pris** : idée d'un pipeline end-to-end idéation → rédaction
- **Adapté** : AI Scientist cible la génération de papers ; ici la production
  est une note de recherche interne (plus courte, plus focalisée)
- **Différence** : ici la boucle est fermée par validation empirique sur robot
  simulé, pas par peer-review externe

### SciAgent (2024-2025)
- **Pris** : architecture coordinateur + workers spécialisés
- **Adapté** : ici le coordinateur est l'apex, les workers sont les skills
  existantes (research-director, validation-pipeline, etc.)
- **Différence** : SciAgent est multi-domaine ; ici monodomaine (sécurité LLM chirurgie)

### Agent Laboratory (2025)
- **Pris** : supervision humaine aux points SUPERVISED
- **Adapté** : les transitions de conjectures restent SUPERVISED
- **Différence** : Agent Laboratory prend une idée humaine en entrée ; ici
  l'apex peut démarrer sans input en lisant les signaux

### LiRA (Literature Review Agents, 2024)
- **Pris** : pipeline recherche → synthèse → raffinement
- **Adapté** : la phase CORRELATE implémente la synthèse inter-sources
- **Différence** : LiRA fait uniquement de la littérature ; ici on croise
  empirique + littérature

### MLAgentBench (Stanford 2023)
- **Pris** : idée d'un benchmark end-to-end d'agents de recherche
- **Adapté** : les scoring reports apex servent d'auto-benchmark
- **Différence** : MLAgentBench teste des agents sur des tâches ML fixées ;
  ici l'apex est évalué sur sa capacité à produire des notes de recherche
  utiles à la thèse

**Limitations observées dans la littérature (à éviter) :**
- **42% erreurs de codage dans AI Scientist** → d'où la règle "ne pas faire
  d'action tactique directement, toujours déléguer"
- **Hallucinations sur la nouveauté dans les surveys LiRA** → d'où les tags
  obligatoires `[ARTICLE VÉRIFIÉ]` vs `[HYPOTHÈSE]`
- **Drift silencieux dans les agents long-running** → d'où les drift checks
  à chaque phase et la délégation de la mémoire longue à research-director

---

## 6bis. Protocoles étendus (Agent Laboratory patterns)

Trois patterns empruntés à Agent Laboratory (Schmidgall et al. 2025, arXiv 2501.04227)
ont été adaptés à AEGIS. Cette section décrit leur application en détail.

### 6bis.1 — ITERATE (inspiré de `mle-solver`)

**Contexte d'origine** : dans Agent Laboratory, `mle-solver` itère sur son code
jusqu'à ce que la métrique cible soit atteinte. Chaque itération = lire le
feedback de l'exécution → modifier le code → rerun.

**Adaptation AEGIS** : l'apex n'écrit pas de code — il orchestre des skills.
Mais quand `/validation-pipeline` retourne PARTIAL, l'apex peut ajuster les
paramètres de la campagne et relancer, au lieu d'accepter passivement un
résultat imparfait.

**Diagnostic d'un PARTIAL** — grille de lecture :

| Symptôme dans le rapport | Cause probable | Ajustement (AUTONOMOUS) |
|--------------------------|----------------|-------------------------|
| ASR_AFTER > 30% | Défense trop faible | Élargir patterns regex (+synonymes, +cas limites) |
| CI width > 0.10 | N trop petit pour Wilson CI | Relancer avec N=100 |
| Une chaîne sur 3 couverte | `chain_ids` trop restreint | Ajouter les chaînes manquantes |
| False positives élevés | Seuil de sévérité trop lâche | Passer 0.80 → 0.75 |
| ASR stable entre 2 itérations | Plafond atteint | **Arrêt précoce** + verdict PARTIAL_EXHAUSTED |

**Ajustements SUPERVISED** (interdits en AUTONOMOUS) :
- Ajouter une méthode à une classe de défense
- Modifier les limites physiques (MAX_TENSION_G, MAX_WRIST_ANGLE_DEG, MAX_TOOL_VELOCITY)
- Désactiver une catégorie entière de détecteur
- Changer le scoring de sévérité d'une catégorie
- Toute modification qui pourrait impacter d'autres gaps non testés

**Format de log ITERATE dans le JSONL apex** :

```json
{"type": "iterate_start", "gap": "G-032", "initial_verdict": "PARTIAL", "asr_before_iterate": 0.45}
{"type": "iterate_attempt", "gap": "G-032", "attempt": 1, "adjustment": "N: 30 → 100", "autonomy": "AUTONOMOUS", "new_verdict": "PARTIAL", "asr": 0.22}
{"type": "iterate_attempt", "gap": "G-032", "attempt": 2, "adjustment": "+ synonyms regex", "autonomy": "AUTONOMOUS", "new_verdict": "VALIDATED", "asr": 0.12}
{"type": "iterate_end", "gap": "G-032", "final_verdict": "VALIDATED", "attempts": 2}
```

**Règles d'arrêt** :
- VALIDÉ → arrêt immédiat, succès
- 3 tentatives épuisées → PARTIAL_EXHAUSTED, logger et passer au gap suivant
- Δ ASR < 2% entre deux tentatives → plafond atteint, arrêt précoce
- Ajustement nécessaire est SUPERVISED → sortir, noter dans §10 de la note

### 6bis.2 — CHECKPOINT (inspiré de `state_saves/`)

**Contexte d'origine** : Agent Laboratory sauvegarde l'état du système à
chaque transition de phase pour permettre la reprise après crash ou
interruption manuelle.

**Adaptation AEGIS** : une session apex peut durer 1-2h et manipuler 50-100k
tokens. Une interruption (contexte plein, crash, perte réseau, pause
utilisateur) sans checkpoint = perte totale du travail en cours.

**Quand sauvegarder** :
1. **Toutes les 3 délégations terminées** (rythme régulier)
2. **Avant chaque transition de phase majeure** : TRIAGE→DELEGATE, DELEGATE→CORRELATE, CORRELATE→SYNTHESIZE
3. **Avant d'entrer en phase ITERATE** (état potentiellement long)
4. **Avant la passe reviewer hostile** (la note DRAFT existe déjà, précieuse)
5. **À 60% de contexte** (avant la règle offload à 70%)

**Structure complète d'un checkpoint** :

```json
{
  "session_id": "SESSION-043",
  "timestamp": "2026-04-10T16:47:00",
  "checkpoint_version": 1,
  "phase_courante": "DELEGATE",
  "phases_completees": ["OPEN", "TRIAGE"],
  "snapshot_open": { /* résultat complet de session_snapshot.py */ },
  "triage_bacs": {
    "A": [{"gap": "G-032", "priority": 0}, {"gap": "G-037", "priority": 1}],
    "B": [{"rr": "RR-044", "priority": 2}],
    "C": [],
    "D": [{"theme": "correlate_cot_hijacking_p094", "priority": 3}]
  },
  "delegations_terminees": [
    {
      "bac": "A",
      "target": "G-032",
      "skill": "/validation-pipeline",
      "status": "VALIDATED",
      "iterate_attempts": 2,
      "summary_short": "ASR 45% → 12.3% après +synonyms regex",
      "report_ref": "buffer_rapports.G-032"
    }
  ],
  "delegations_pending": [
    {"bac": "A", "target": "G-037", "next": true},
    {"bac": "A", "target": "G-041"},
    {"bac": "B", "target": "RR-044"}
  ],
  "buffer_rapports": {
    "G-032": "<full report text>",
    "...": "..."
  },
  "drift_check_last": "CLEAR",
  "drift_check_history": ["CLEAR@OPEN", "CLEAR@TRIAGE", "CLEAR@DELEGATE.1"],
  "tokens_consumed_estimate": 45000,
  "context_usage_pct": 38,
  "iterate_state": null,
  "correlate_state": null,
  "synthesize_state": null
}
```

**Protocole de reprise** (`/aegis-research-lab resume SESSION-{id}`) :

1. `python scripts/checkpoint.py load SESSION-{id}` → récupère le JSON
2. Vérifier la date : si > 48h, avertir l'utilisateur (laboratoire peut avoir évolué)
3. Re-lire le snapshot_open et comparer avec l'état actuel du labo :
   - Nouveaux signaux ? → les intégrer dans le triage avant de reprendre
   - Un gap ciblé a été modifié depuis ? → **HALT**, demander confirmation
4. Reconstruire les buffers en mémoire
5. Reprendre exactement à la première `delegations_pending`
6. **Ne PAS rejouer** les délégations terminées — leurs rapports sont dans le buffer
7. Logger dans le JSONL : `{"type": "resume", "from_checkpoint": "...", "skipped_delegations": N}`

**Pruning** : `checkpoint.py prune --older-than 7` à exécuter manuellement
(ou via cron) pour éviter l'accumulation. Les checkpoints des sessions
terminées avec SESSION_COMPLETE peuvent être supprimés plus tôt.

### 6bis.3 — SYNTHESIZE.2 — Reviewer hostile (inspiré de la review loop)

**Contexte d'origine** : Agent Laboratory utilise un reviewer agent qui note
les papers produits par `paper-solver` sur 4 axes (novelty, clarity, etc.).
Les papers avec score faible sont réécrits.

**Adaptation AEGIS** : le "paper" est la note de recherche. Le reviewer n'a
pas à noter — il doit **attaquer** la note. L'apex est structurellement
biaisé en sa propre faveur, il faut un contre-pouvoir adversarial avant la
signature.

**Pourquoi un agent séparé** — pas un second prompt à l'apex lui-même :
- L'apex a construit la note → biais de confirmation
- L'apex connaît l'historique des délégations → tendance à rationaliser les
  PARTIAL exhaustés
- Un agent fresh, sans contexte de session, lit la note comme un tiers
  sceptique la lirait — c'est exactement ce qu'on veut

**Prompt reviewer complet** : voir SKILL.md §6.3 étape 2. Points clés :
- Le reviewer reçoit **uniquement le DRAFT**, pas le buffer apex
- Il doit produire un JSON structuré (pas de prose libre)
- Il doit séparer `must_fix_before_signature` de `can_signal_but_note`

**Grille des 8 catégories de faiblesses recherchées** :

| # | Catégorie | Exemple de détection |
|---|-----------|---------------------|
| a | Affirmation empirique non taguée | "l'ASR baisse significativement" sans N/CI/tag |
| b | Affirmation littérature sans source | "des papers récents montrent" sans arXiv ID |
| c | Corrélation forcée | §5 affirme convergence alors que les sources mesurent des objets différents |
| d | Section 8 vague | "cycle productif" au lieu de "C3 passe de 8/10 à 9/10 grâce à X" |
| e | Section 9 complaisante | "tout est validé" ou §9 vide |
| f | Section 10 floue | "continuer la validation" sans skill cible ni paramètres |
| g | Transition conjecture abusive | propose CANDIDATE→ACTIVE avec une seule source |
| h | Drift silencieux | §1 dit "focus sur G-037" mais §3 ne montre que G-032 |

**Interaction reviewer ↔ apex** :

```
[SYNTHESIZE.1] apex écrit DRAFT
   ↓
[SYNTHESIZE.2 pass 1] spawn reviewer → verdict REVISE + 4 issues
   ↓
apex corrige les must_fix, met les can_signal en §9
   ↓
[SYNTHESIZE.2 pass 2] spawn reviewer → verdict ACCEPT
   ↓
[§6.4] signature finale, DRAFT.md → SESSION-{id}_{date}.md
```

**Règles de désaccord** : si l'apex pense qu'un `must_fix` est incorrect
(le reviewer se trompe), il a deux options :
1. **Convaincre par la preuve** : ajouter dans §9 une justification explicite
   citant la source qui contredit le reviewer — et signer avec avertissement.
2. **Soumettre à escalade humaine** : si le désaccord porte sur une transition
   de conjecture ou un verdict de validation critique — HALT.

L'apex NE DOIT JAMAIS ignorer silencieusement un `must_fix`. C'est cette
règle qui donne sa valeur au reviewer — sans elle, la passe est cosmétique.

**Logging dans le JSONL apex** :

```json
{"type": "reviewer_spawn", "pass": 1, "draft_path": "..._DRAFT.md"}
{"type": "reviewer_verdict", "pass": 1, "verdict": "REVISE", "severity": "major", "issues_count": 4}
{"type": "reviewer_fixes_applied", "pass": 1, "must_fix_applied": 3, "must_fix_rejected": 1, "rejection_justification": "source X contredit le reviewer"}
{"type": "reviewer_spawn", "pass": 2, "draft_path": "..._DRAFT.md"}
{"type": "reviewer_verdict", "pass": 2, "verdict": "ACCEPT"}
{"type": "note_signed", "final_path": "SESSION-043_2026-04-10.md", "reviewer_passes": 2}
```

**Échecs possibles du reviewer lui-même** :
- Le reviewer hallucine une issue → l'apex la rejette avec justification (cas 1 ci-dessus)
- Le reviewer est trop indulgent (ACCEPT immédiat sans vraie vérification) → pas de garde-fou direct, mais le pattern de toujours-ACCEPT doit être surveillé sur plusieurs sessions via l'INDEX_NOTES
- Le reviewer produit un JSON malformé → l'apex relance avec le prompt + `(réponse précédente invalide)`, max 1 retry

### §6bis.4 — Phase DISCOVER (apprentissage cumulatif)

**Objectif** : interroger la collection `aegis_research_notes` (ChromaDB, embeddings
locaux `all-MiniLM-L6-v2`) *avant* de construire le TRIAGE, afin d'éviter de
réinventer des résultats déjà archivés. Le §2bis du SKILL.md décrit le protocole
au niveau opérationnel ; cette section en détaille les règles techniques.

**Seuils de similarité** :

| Score cosinus | Interprétation | Action |
|---------------|----------------|--------|
| ≥ 0.70        | Quasi-duplicata | Lire la note existante avant toute délégation sur ce gap/conjecture |
| 0.55 – 0.69   | Pertinent       | Citer dans §11.2 de la note finale |
| 0.40 – 0.54   | Signal faible   | Mentionner en §9 si convergeant avec un autre finding |
| < 0.40        | Bruit           | Ignorer |

**Scripts associés** :
- `ingest_research_note.py` — indexe une note signée dans la collection ChromaDB
- `retrieve_similar_notes.py` — requête cosinus sur la collection, retourne les N
  chunks les plus proches avec leur score

**Règles anti-redondance** (3 règles strictes) :

1. **Re-lancement interdit sur gap+conjecture déjà résolu** : si une note existante
   contient le tag `[CALCUL VÉRIFIÉ]` et cible le même gap ET la même conjecture
   que l'item TRIAGE courant, ne pas relancer la délégation — marquer l'item comme
   `DISCOVERED_SKIP` dans le checkpoint et passer au suivant.

2. **Priorité dégradée sur action ignorée** : si une note DISCOVERED contient une
   §10 recommandant une action (skill cible + paramètres) et que cette action n'a
   jamais été suivie d'effet (aucun checkpoint ultérieur ne la référence), l'item
   correspondant descend en priorité B, même s'il était P0 dans le TRIAGE brut.

3. **Citation obligatoire** : toute note retrouvée avec sim ≥ 0.55 DOIT figurer
   dans §11.2 de la note finale de la session courante, au format défini en §6bis.7.
   Omettre une note DISCOVERED est une erreur bloquante au reviewer (§6bis.5).

**Cas limite — collection vide** : si `retrieve_similar_notes.py` renvoie zéro
résultats (collection non encore peuplée ou requête sans résultat), la phase
DISCOVER se termine silencieusement. Logger le tag `DISCOVER_EMPTY` dans le JSONL
apex (`{"type": "discover_empty", "query": "..."}`) mais NE PAS bloquer la session.
La session se poursuit vers TRIAGE normalement.

---

### §6bis.5 — Scoring multi-axes + auto-patch (reviewer v2)

**Contexte** : le reviewer §6bis.3 détecte des faiblesses catégorielles (grille à
8 entrées). Le reviewer v2 ajoute un scoring quantitatif 4-axes qui pilote
automatiquement la décision sans intervention humaine dans les cas courants.

**Les 4 axes (score 1-10)** :

| Axe       | Ce qu'il mesure |
|-----------|----------------|
| `novelty`   | La note apporte-t-elle une information nouvelle par rapport à l'existant ? |
| `soundness` | Les affirmations empiriques sont-elles correctement taguées et sourcées ? |
| `clarity`   | Le §8 et le §10 sont-ils précis et lisibles hors contexte de session ? |
| `impact`    | Le résultat fait-il avancer un gap, une conjecture ou un chapitre de thèse ? |

**Grille décisionnelle** :

| Condition | Verdict | Autonomie |
|-----------|---------|-----------|
| Tous les 4 axes ≥ 8 ET aucune issue `blocking` | `ACCEPT_AS_IS` | AUTONOMOUS |
| Tous les 4 axes ≥ 6 ET aucune issue `blocking` | `PATCH` | AUTONOMOUS |
| Au moins un axe < 6 OU au moins une issue `blocking` | `REVISE` | SUPERVISED, max 2 passes |
| 2 passes `REVISE` consécutives sans amélioration | `REJECT` | AUTONOMOUS + signal `REVIEWER_REJECT_*.json` |

**Qui applique le PATCH** : l'apex lui-même, sans sous-délégation. Les corrections
sont textuelles (reformulation, ajout de tags, correction de chiffres, précision
de §10) et ne requièrent pas de relance de campagne. Toute correction qui
nécessiterait une relance de délégation sort du périmètre PATCH et bascule en
REVISE SUPERVISED.

**Format JSON complet retourné par le reviewer** :

```json
{
  "session_id": "SESSION-043",
  "reviewer_pass": 1,
  "scores": {
    "novelty": 7,
    "soundness": 8,
    "clarity": 5,
    "impact": 8
  },
  "verdict": "REVISE",
  "autonomy": "SUPERVISED",
  "issues": [
    {
      "category": "d",
      "severity": "blocking",
      "section": "§8",
      "description": "Section 8 trop vague — 'cycle productif' sans chiffre.",
      "suggested_fix": "Remplacer par la transition C3 8/10 → 9/10 avec Wilson CI."
    }
  ],
  "cited_sessions_verified": ["SESSION-041", "SESSION-039"],
  "must_fix_before_signature": ["§8 vague (blocking)"],
  "can_signal_but_note": ["latence non mesurée"]
}
```

**Log des passes reviewer** :
`_staging/research-lab/reviews/REVIEW_{SESSION-id}_pass{N}.json`

Chaque fichier correspond à une passe ; le contenu est le JSON ci-dessus.

---

### §6bis.6 — Mode parallel lines

**Condition d'activation** : le mode parallèle ne se déclenche que si les trois
conditions suivantes sont simultanément vraies :
1. Au moins 2 conjectures distinctes sont ciblées dans le TRIAGE du cycle courant.
2. Les gaps associés à ces conjectures n'ont aucun gap *commun* (pas de chevauchement).
3. La collection DISCOVER (`aegis_research_notes`) est disponible (non vide).

Si l'une de ces conditions manque, la session s'exécute en mode séquentiel standard.

**Limite dure** : 3 lignes parallèles maximum. Au-delà, la corrélation inter-lignes
devient trop coûteuse à maintenir et le risque de drift entre lignes augmente
proportionnellement.

**Structure des checkpoints en mode parallel** :

Chaque ligne dispose de son propre checkpoint :
`CHECKPOINT_{SESSION-id}_line_{letter}.json` (ex: `_line_A`, `_line_B`, `_line_C`)

La structure interne est identique au checkpoint standard (§6bis.2), avec deux
champs supplémentaires :
```json
{
  "parallel_line": "A",
  "parallel_conjecture_scope": ["C3"],
  "parallel_gaps_scope": ["G-032", "G-037"]
}
```

**Point de synchronisation unique — SYNTHESIZE** :

Les lignes ne se synchronisent qu'une seule fois, à l'entrée de la phase SYNTHESIZE.
L'apex fusionne les buffers de rapports de toutes les lignes en *une* note de
recherche unifiée. Cette note inclut obligatoirement une section `§13 — Lignes
parallèles exécutées` listant pour chaque ligne : les gaps couverts, le verdict
final, et les tokens estimés.

**Règle de cohérence inter-lignes** :

Si deux lignes produisent des verdicts contradictoires sur le même paper ou la même
affirmation empirique (ex : ligne A accepte la convergence C3/G-032, ligne B la
rejette pour le même paper), l'apex DOIT :
1. Émettre le signal `_staging/signals/PARALLEL_CONFLICT_{SESSION-id}.json`
2. HALT immédiatement, avant toute signature de note
3. Présenter les deux positions à l'utilisateur pour arbitrage humain

Ce signal n'est PAS escaladable de façon autonome — la résolution nécessite la
lecture des deux buffers par un humain.

**Reviewer en mode parallel** : le reviewer §6.3 (et ses règles de scoring v2
§6bis.5) s'applique **une seule fois**, sur la note fusionnée produite après
SYNTHESIZE. Les lignes individuelles ne passent pas par le reviewer.

**Commandes CLI** (alignées sur les commandes de §4bis du SKILL.md) :

```
/aegis-research-lab --parallel          # activation automatique si conditions OK
/aegis-research-lab resume SESSION-043  # reprise avec détection automatique du mode
python scripts/checkpoint.py list       # voit les checkpoints _line_A/B/C
```

---

### §6bis.7 — Cross-citation vérifiée

**Règle fondamentale** : toute note de recherche produite lors d'une session ayant
lancé la phase DISCOVER (qu'elle ait retourné des résultats ou non) DOIT inclure
une section §11.2 — Sources DISCOVER.

**Format obligatoire de chaque entrée §11.2** :

```
SESSION-XXX (sim=0.XX) — §Y — [justification en une phrase]
```

Exemple :
```
SESSION-039 (sim=0.71) — §5 — Résultat sur xml_agent ASR confirme la direction G-037.
SESSION-041 (sim=0.58) — §8 — Transition C3 8→9 déjà documentée, non redondant ici.
```

Si DISCOVER_EMPTY (phase lancée, aucun résultat), écrire dans §11.2 :
```
(DISCOVER_EMPTY — aucune note similaire trouvée dans la collection)
```

**Vérification par le reviewer (§6.3 + §6bis.5)** :

Le reviewer vérifie l'existence physique de chaque fichier `SESSION-XXX_*.md` cité
dans §11.2 en consultant `research_archive/research_notes/`. Pour chaque citation :

- Fichier trouvé → entrée validée, ajoutée dans `cited_sessions_verified` du JSON
  reviewer (cf §6bis.5)
- Fichier introuvable (note orpheline) → issue `blocking`, catégorie `h`,
  verdict automatique REVISE — l'apex DOIT corriger avant signature

**Log** : les vérifications de cross-citation tombent dans le fichier reviewer
`_staging/research-lab/reviews/REVIEW_{SESSION-id}_pass{N}.json` (même fichier
que §6bis.5). Le champ `cited_sessions_verified` liste les sessions effectivement
trouvées sur le disque.

**Motivation** : un système d'apprentissage cumulatif (pattern agentRxiv) n'a de
valeur scientifique que si les citations entre notes sont traçables et vérifiables.
Une citation orpheline est du bruit — elle indique soit une note supprimée
(régresssion de l'archive), soit une hallucination de l'apex sur une session qui
n'a jamais existé. Dans les deux cas, c'est une erreur bloquante, non un simple
avertissement.

---

## 7. Exemple de session apex complète (simulation)

```
Utilisateur : /aegis-research-lab

[OPEN]
  python scripts/session_snapshot.py --json
  Snapshot produit :
    Gaps : 8 A CONCEVOIR, 3 IMPLEMENTE sans preuve, 12 FERMÉS
    C3 = 8/10, C6 = CANDIDATE (7/10)
    Signaux : 1 CAMPAIGN_COMPLETE_G032
  → CHECKPOINT.1 sauvegardé (fin de OPEN)

[TRIAGE]
  Bac A : 3 gaps IMPLEMENTE sans preuve (G-032, G-037, G-041)
  Bac B : RR-044 (literature search SEAL ciphers)
  Bac C : (rien)
  Bac D : corrélation G-032 × paper P094 potentielle

  Ordre : A1 (G-032) → A2 (G-037) → A3 (G-041) → B1 → D
  → CHECKPOINT.2 sauvegardé (fin de TRIAGE)

[DELEGATE]
  → /validation-pipeline G-032
    ← PARTIAL: ASR hyde 45% (N=30, défense trop faible)

  [ITERATE G-032]
    Tentative 1/3 :
      Diagnostic : pattern regex trop étroit (manque synonymes CoT)
      Ajustement : +synonyms regex (AUTONOMOUS)
      → /validation-pipeline G-032 (re-run)
      ← PARTIAL: ASR hyde 22% (amélioration +23%)
    Tentative 2/3 :
      Diagnostic : N=30 insuffisant pour CI strict
      Ajustement : N: 30 → 100 (AUTONOMOUS)
      → /validation-pipeline G-032 --n=100
      ← VALIDÉ: ASR hyde 12.3% (N=100, Wilson [0.07, 0.19])
    ITERATE end : VALIDÉ en 2 tentatives

  → CHECKPOINT.3 sauvegardé (3 délégations effectives)

  → /validation-pipeline G-037
    ← PARTIAL: multi-turn tracker détecte mais ne bloque pas
  [ITERATE G-037]
    Tentative 1/3 : seuil sévérité 0.80 → 0.75 → ASR 51% (Δ < 2%)
    Tentative 2/3 : +chaîne xml_agent → ASR 48% (Δ < 2%)
    ARRÊT PRÉCOCE : plafond atteint, verdict PARTIAL_EXHAUSTED
    → Noté en §10 de la note : nécessite ajustement structure (SUPERVISED)

  → /validation-pipeline G-041
    ← VALIDÉ (ASR stacked ciphers → 0%)
  → /research-director search RR-044
    ← 4 chunks sur SEAL 2025, 2 papers nouveaux
  → CHECKPOINT.4 sauvegardé (fin DELEGATE)

[CORRELATE]
  Pattern 1 : G-032 validé + paper P094 → nouveau gap G-053
              "mid-<think> payload placement"
  Pattern 2 : G-041 validé + RR-044 SEAL → C3 gagne un support ↑

[SYNTHESIZE.1 — DRAFT]
  Écriture de research_notes/SESSION-043_2026-04-10_DRAFT.md
  Sections 1-12 remplies, longueur ~850 mots
  → CHECKPOINT.5 sauvegardé (avant reviewer)

[SYNTHESIZE.2 — Reviewer hostile]
  Pass 1 :
    Spawn reviewer agent (general-purpose, prompt de §6.3)
    ← Verdict: REVISE, severity: major
    ← Issues (3) :
      1. §5.1 : "G-041 + RR-044 convergent" — reviewer dit les sources
         mesurent des objets différents (SEAL ≠ stacked ciphers de G-041)
         → must_fix
      2. §8 : "cycle productif" trop vague
         → must_fix
      3. §10 : "valider G-037" sans paramètres
         → must_fix
    Corrections apex :
      1. §5.1 réécrit en "G-041 validé ; RR-044 suggère une direction
         future à explorer (≠ convergence directe)" [accepté]
      2. §8 réécrit : "C3 passe de 8/10 à 9/10 via G-032 N=100 Wilson..."
      3. §10 précisé : "G-037 — modification structure MultiTurnTracker
         (ajouter méthode block_on_tracking), SUPERVISED"

  Pass 2 :
    Spawn reviewer agent (nouveau fresh context)
    ← Verdict: ACCEPT
  → Signature finale : DRAFT.md renommé → SESSION-043_2026-04-10.md

[MEMORIZE]
  → /research-director complete-session {buffer apex}
    ← CONJECTURES_TRACKER : C3 8/10 → 9/10 (AUTONOMOUS)
    ← THESIS_GAPS : G-032 fermé, G-041 fermé, G-053 créé,
                    G-037 reste IMPLEMENTE avec note SUPERVISED-requis
    ← RESEARCH_STATE : mis à jour

[EVOLVE]
  Prochaine action : G-037 → modification MultiTurnTracker (SUPERVISED)
  Temps : ~90 min, nécessite validation humaine avant run
  Signal : NEXT_CYCLE_2026-04-10.json émis

[CLOSE]
  Scoring report apex : 5/5
  Drift : CLEAR
  Reviewer passes : 2
  Iterate loops : 2 (G-032 VALIDÉ, G-037 PARTIAL_EXHAUSTED)
  Checkpoints : 5
  SESSION_COMPLETE_SESSION-043 émis
```
