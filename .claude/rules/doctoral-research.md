# Regles de recherche doctorale — AEGIS (ENS, 2026)

## AUTOMATISATION — L'UTILISATEUR NE DEMANDE PAS

Le pipeline de recherche doit etre AUTO-DECLENCHANT. Apres chaque etape, la suivante se lance sans que l'utilisateur ait a demander. Si l'utilisateur doit dire "c'est indexe ?", "le directeur a les elements ?", "les preuves sont propagees ?" — c'est que le pipeline est casse.

Regles :
1. Analyse terminee → LIBRARIAN propage automatiquement dans doc_references/ + indexes
2. Propagation faite → SCIENTIST met a jour conjectures + gaps + research_requests automatiquement
3. Mise a jour faite → RETEX produit automatiquement avec actions pour le directeur
4. RETEX produit → RESEARCH_STATE.md mis a jour automatiquement
5. PDFs telecharges → injectes dans ChromaDB automatiquement
6. Nouvelle fiche → seedee dans ChromaDB automatiquement
7. Campagne terminee → EXPERIMENTALIST analyse resultats automatiquement
8. Conjecture validee experimentalement → THESIS-WRITER met a jour le manuscrit automatiquement
9. Resultat INCONCLUSIVE → protocol_v2 genere automatiquement (max 3 iterations)

JAMAIS de travail qui reste dans _staging/ sans etre propage. JAMAIS de rapport sans actions extractees. JAMAIS de PDF sans injection RAG.

## ANTI-DOUBLON — COLLECTOR

Avant d'attribuer un P-ID, le COLLECTOR DOIT verifier l'absence de doublon
via query ChromaDB (titre + auteurs, seuil cosine > 0.9). Si doublon detecte → ne pas integrer.

## ANTI-DOUBLON ÉTAPE 0 — avant toute vérification biblio (scoped ou full)

Avant d'envoyer une référence arXiv à WebFetch / WebSearch / ANALYST / COLLECTOR — que ce soit en mode full_search, incremental, ou dans un sub-agent de vérification ad-hoc — **TOUJOURS cross-check MANIFEST.md pour son arXiv ID en premier** via l'utilitaire dédié :

```bash
python backend/tools/check_corpus_dedup.py <arxiv_id> [<arxiv_id> ...]
```

Comportement :
- Exit 0 `[NEW]` → procéder avec la vérification / analyse / injection
- Exit 1 `[DUPLICATE] as PXXX` → **ARRÊTER**. La version corpus PXXX est autoritative. Référencer PXXX au lieu de créer un doublon. Ne PAS re-vérifier sur arXiv, ne PAS créer de nouvelle analyse, ne PAS ré-injecter dans ChromaDB.
- Exit 2 `[ERROR]` → diagnostiquer (MANIFEST manquant, needle trop court) avant de continuer

Cette étape est **obligatoire** pour :
- `/bibliography-maintainer full_search` et `/bibliography-maintainer incremental`
- Tout sub-agent COLLECTOR / ANALYST spawné depuis un skill
- Tout sub-agent de vérification ad-hoc (p.ex. verification scoped d'une note académique)
- Toute création manuelle d'un P-ID dans MANIFEST.md

**Failure mode documenté** : 2026-04-09, un agent de vérification scoped a dédupliqué via cosine arXiv (source externe) mais PAS via MANIFEST (source interne). Résultat : Crescendo (arXiv:2404.01833, déjà présent comme P099) a été re-vérifié et aurait été re-intégré sans le cross-check manuel post-hoc. Fix : `backend/tools/check_corpus_dedup.py` + cette règle + Step 0 dans le SKILL.md du bibliography-maintainer.

**Limitation** : le check s'appuie sur l'arXiv ID (pattern `arXiv:XXXX.XXXXX` dans MANIFEST). Pour les papers sans arXiv ID (conference proceedings, journaux sans preprint), compléter par un check titre via `--title "<needle>"` (needle >= 12 chars pour éviter les faux positifs). Pour les doublons sémantiques (même contenu, titre différent), le fallback reste le check cosine ChromaDB du COLLECTOR ci-dessus.

## POST-INJECTION — COLLECTOR

Apres injection PDF dans ChromaDB, verifier >= 5 chunks presents.
Si echec → BLOCKED, pas de P-ID attribue. Logger dans le preseed JSON.

## PROPAGATION VERIFIEE — LIBRARIAN

Apres chaque Phase ANALYST, verifier que TOUS les P-IDs
sont dans MANIFEST.md et doc_references/. Si manquant → LIBRARIAN incremental AVANT de passer a Phase 4.

## PRE-CHECK EXPERIMENTAL

Avant une campagne N>=30, lancer 5 runs baseline :
- Si ASR baseline < 5% → ajuster parametres (max_tokens, fuzzing, temperature)
- Si ASR baseline > 90% → verifier que le juge n'est pas trop laxiste
- Logger le pre-check dans le protocol JSON

## VERIFICATION AVANT COMPLETION — REGLE ABSOLUE

**Aucun lot n'est "done" tant que `/audit-these claims` n'a pas ete execute dessus.**

1. Apres chaque batch d'analyses : `python lint_sources.py` → si > 5% NONE → PAS DONE
2. Apres chaque batch de fiches : `python lint_sources.py` sur les fiches → si > 5% → PAS DONE
3. Apres chaque correction de refs : `python verify_fidelity.py` → si erreur factuelle → CORRIGER
4. Toute affirmation "le seul", "le premier", "aucun autre" → WebSearch de verification AVANT publication
5. **HUMILITY GATE (2026-04-12)** : "Il y a tres peu de chance que personne ait vu avant nous.
   Soyons humbles." Le SCIENTIST ne peut PAS promouvoir une decouverte de PROPOSED a ACTIVE
   si elle contient un mot-cle de primeur ("premier", "seul", "aucun autre", "first", "only",
   "novel", "unprecedented") SANS avoir d'abord execute un WebSearch via `/bibliography-maintainer scoped`.
   Si un concurrent est trouve → reformuler en "parmi les premiers" ou "etend le travail de X".
   Si rien n'est trouve → qualifier avec scope + date ("aucun travail identifie par WebSearch YYYY-MM-DD").
   JAMAIS de primeur absolue. Cette regle est un GATE BLOQUANT, pas un conseil.
   **Failure mode documente** : D-021 "premier red team autonome" refute par AutoRedTeamer (OpenReview 2025).
   Taux de faux positifs detecte : 3.4% (1/29 decouvertes). C'est trop pour une these ENS.
5. Chaque session COMMENCE par `/audit-these full` et se TERMINE par `/audit-these full`

Le volume n'est PAS une metrique de qualite. "97/97 done" ne veut rien dire si 42.8% des claims n'ont pas de source.

## CROSS-VALIDATION OBLIGATOIRE — PAS DE BATCH AVEUGLE

Apres chaque batch de N analyses :
1. Selectionner 3 analyses aleatoirement
2. Pour chacune, verifier les 3 chiffres les plus importants contre le fulltext ChromaDB
3. Si UN SEUL chiffre est faux → refaire TOUT le batch (l'agent a produit du travail bacle)
4. Logger le resultat de la cross-validation dans le journal

Regles :
- Maximum 3 agents en parallele (pas 6 — trop difficile a auditer)
- Chaque agent produit un rapport de sources verifiees vs non trouvees
- Les `[SOURCE A VERIFIER]` sont des DETTES — pas des acquis

## QUALITE DOCTORALE — PAS DE TRAVAIL BACLE

Les analyses doivent etre de niveau publication, pas de niveau resume d'abstract. Un stagiaire qui produit du travail superficiel est mis a la porte.

1. **Lire le papier COMPLET** : les PDFs sont dans ChromaDB (5500+ chunks fulltext). Les agents DOIVENT query le RAG avec `--multi-collection` pour lire le texte complet, PAS se limiter a l'abstract.
2. **Formules EXACTES** : extraire la notation originale du papier, pas une paraphrase. Si la formule n'est pas dans l'abstract, lire le PDF via le RAG.
3. **Limites des auteurs** : identifier ce que les auteurs eux-memes admettent comme limitations. C'est dans la section Discussion/Limitations du papier.
4. **Critique methodologique** : N suffisant ? Reproductible ? Biais de selection ? Comparaison avec d'autres travaux ?
5. **Comparaison AEGIS** : chaque papier doit etre mis en perspective avec nos propres resultats experimentaux.
6. **Pas de remplissage** : si l'analyse fait 500 mots a partir de 200 mots d'abstract, c'est du remplissage. Mieux vaut une analyse courte et precise qu'une longue et vide.

## ZERO APPROXIMATION — ZERO HALLUCINATION

1. **ZERO HALLUCINATION** : toute reference DOIT avoir arXiv ID ou DOI verifie.
2. **ZERO DOCUMENT NON REFERENCE** : chaque .md pointe vers son PDF dans `literature_for_rag/`. Chaque PDF est injecte dans ChromaDB.
3. **TRIPLE VERIFICATION** : (1) URL verifiee WebFetch, (2) cross-validation 2eme agent, (3) tracabilite complete.
4. **Tags obligatoires** : `[ARTICLE VERIFIE]` / `[PREPRINT]` / `[HYPOTHESE]` / `[CALCUL VERIFIE]` / `[EXPERIMENTAL]`
5. **PDFs dans le RAG** : tout PDF telecharge → extrait pypdf → injecte ChromaDB. Un PDF pas dans le RAG est inutile.
6. **Sep(M)** : N >= 30 par condition. Sep(M)=0 avec 0 violations = artefact statistique.
7. **Formules par calcul** : pas par citation d'abstract. Marquer `[ABSTRACT SEUL]` si formule non vue.
8. **Pas de WebSearch direct** : deleguer a `/bibliography-maintainer` (COLLECTOR verifie les URLs).

## REFERENCES INLINE — REGLE ABSOLUE

**CHAQUE affirmation factuelle dans CHAQUE fichier produit par un agent DOIT citer sa source exacte inline.**

Format obligatoire :
- `"31 sur 36 applications vulnerables" (Liu et al., 2023, Section 5.1, Table 2)`
- `"ASR de 94.4%" (Lee et al., 2025, JAMA Network Open, Table 3, p.e2512345)`
- `"Theoreme 10 : gradient nul au-dela de l'horizon" (Young, 2026, Section 4.2, Eq. 15)`
- `"Sep(M) = 73.2% pour le meilleur modele" (Zverev et al., 2025, ICLR, Table 1)`

Un chiffre sans reference inline = un chiffre non verifiable = INACCEPTABLE pour une these.

Cela s'applique a TOUS les agents : ANALYST, MATHEUX, CYBERSEC, WHITEHACKER, SCIENTIST.
Cela s'applique a TOUS les fichiers : analyses, glossaires, playbooks, axes de recherche, briefings.

## METHODE DE LECTURE CRITIQUE — 3 PASSAGES (Keshav, 2007)

Chaque papier est analyse en 3 passages, conformement au protocole doctoral :

### Passage 1 — Survol (5-10 min)
- Titre, abstract, introduction (1er paragraphe), conclusion, figures/tableaux + legendes
- Question : quelle est la claim principale ? Est-elle originale ?
- Decision : merite-t-il une lecture complete ?

### Passage 2 — Structure (20-30 min)
- Chaque section en sautant les details techniques
- Identifier : probleme → hypothese → methode → resultats → limites avouees
- Signaux d'alerte : pas de section limitations, figures sans barres d'erreur, baselines obsoletes, p-values sans taille d'effet

### Passage 3 — Profondeur critique (variable)
- Equations, preuves, annexes, code source
- Verifier la coherence interne : resultats reproductibles avec les parametres decrits ?
- Confronter avec d'autres papiers du corpus

## TEMPLATE D'ANALYSE OBLIGATOIRE

Chaque fichier `_staging/analyst/PXXX_analysis.md` DOIT suivre cette structure EXACTE :

```markdown
## [Auteurs, Annee] — Titre court

**Reference :** arXiv:XXXX.XXXXX / DOI:XX.XXXX
**Revue/Conf :** [Nom, Quartile SCImago ou CORE Ranking, Annee]
**Lu le :** [Date]
> **PDF Source**: [literature_for_rag/PXXX_xxx.pdf](../../literature_for_rag/PXXX_xxx.pdf)
> **Statut**: [ARTICLE VERIFIE] — lu en texte complet via ChromaDB (N chunks)

### Abstract original
> [Copie verbatim de l'abstract en anglais]
> — Source : PDF page 1

### Resume (5 lignes)
- **Probleme :** [...]
- **Methode :** [...]
- **Donnees :** [Dataset, taille N, public/prive]
- **Resultat :** [Metrique principale + valeur exacte + reference page/table]
- **Limite :** [Limite principale avouee par les auteurs + section du papier]

### Analyse critique
**Forces :** [...] (avec references inline : section, table, figure)
**Faiblesses :** [...] (avec justification)
**Questions ouvertes :** [...]

### Formules exactes
[Notation originale du papier, numero d'equation, page]
Lien glossaire AEGIS : F01-F72

### Pertinence these AEGIS
- **Couches delta :** δ⁰ δ¹ δ² δ³ (lesquelles, avec justification)
- **Conjectures :** C1-C7 (supportee/affaiblie/neutre, avec evidence du papier)
- **Decouvertes :** D-001 a D-020 (confirmee/nuancee/contredite)
- **Gaps :** G-001 a G-027 (adresse/cree)
- **Mapping templates AEGIS :** #01-#97

### Citations cles
> "[Verbatim exact]" (Section X.Y, p. XX)
> "[Verbatim exact]" (Section X.Y, p. XX)

### Classification
| Champ | Valeur |
|-------|--------|
| SVC pertinence | X/10 |
| Reproductibilite | Haute/Moyenne/Faible + justification |
| Code disponible | Oui (URL) / Non |
| Dataset public | Oui (URL) / Non |
```

## VERIFICATION INTEGRITE SCIENTIFIQUE

Avant de citer un papier, verifier :
1. **Retractation** : le papier n'est pas retracte (verifier Retraction Watch si doute)
2. **Preprint vs peer-review** : marquer `[PREPRINT]` si pas encore publie en conference/journal
3. **Resultats trop parfaits** : signaler si 0 variance, toutes p-values < 0.001, courbes trop lisses
4. **Duplications** : signaler si les memes resultats apparaissent dans plusieurs papiers des memes auteurs

## Skills ecosystem

| Skill | Role | Etat partage |
|-------|------|-------------|
| `research-director` | Orchestrateur PDCA | Lit/ecrit RESEARCH_STATE.md |
| `bibliography-maintainer` | 9 agents, recherche biblio | MAJ Sections 3,4,6 de RESEARCH_STATE |
| `fiche-attaque` | 3 agents, fiches d'analyse | MAJ Section 5 de RESEARCH_STATE |
| `aegis-prompt-forge` | Forge prompts, audit, RETEX | MAJ Section 2 de RESEARCH_STATE |
| `add-scenario` | 6 agents, creation scenarios | Backend scenarios.py |

## Fichiers partages

- `research_archive/RESEARCH_STATE.md` — source de verite
- `research_archive/RESEARCH_ARCHIVE_GUIDE.md` — structure des dossiers
- `research_archive/doc_references/prompt_analysis/research_requests.json` — file d'attente gaps
- `research_archive/_staging/briefings/DIRECTOR_BRIEFING_RUN*.md` — briefings par RUN

## Red Team Forge

- Moteur genetique : croisement + mutation de 102 templates
- SVC fitness : 6 dimensions, gradient 0.5-3.5/6
- Operateurs valides : autorite institutionnelle, cross-lingual, encoding, task injection
- Operateurs invalides : XML fictif (regression prouvee #01→#16), negation directe (DAN mort), cliches Hollywood (0xROOT_HACK)
- Calibration : #14 (SVC 1.0) = plancher, #18 (SVC 0.5) = sous-plancher absolu
- Campagnes : N >= 30, metriques ASR/Sep(M)/SVC/P(detect)/cosine drift

## References cles

- Liu et al. (2023) — arXiv:2306.05499, Prompt Injection
- Zverev et al. (2025) — ICLR 2025, Sep(M) + ASIDE
- Qi et al. (2025) — ICLR 2025, Shallow Alignment (Outstanding Paper)
- Lee et al. (2025) — JAMA, Medical LLM 94.4% ASR
- Kim et al. (2025) — ACL 2025, GMTP RAG defense
- Wang et al. (2025) — ICML 2025, Illusion of Role Separation
- Corpus : 80 papiers (P001-P080), 66 formules (F01-F72)
