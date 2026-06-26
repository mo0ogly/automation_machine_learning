---
description: Integre automatiquement les resultats experimentaux valides dans le manuscrit de these. Se declenche quand une conjecture est VALIDATED EXPERIMENTALLY. Ne cite que des resultats avec p < 0.05 et N >= 30.
name: thesis-writer
---

# Skill THESIS-WRITER — Integration Automatique des Resultats dans le Manuscrit

## Role

Agent autonome qui lit les rapports experimentaux (EXPERIMENT_REPORT), identifie les resultats SUPPORTED, et les integre dans les chapitres du manuscrit avec les chiffres exacts, intervalles de confiance, et references.

## Declencheur

- Appel explicite : `/thesis-writer [conjecture_id]`
- Hook dans research-director : signal `_staging/signals/CONJECTURE_VALIDATED_[CX]`
- Appel par l'EXPERIMENTALIST apres verdict SUPPORTED

## Entrees

1. `research_archive/experiments/EXPERIMENT_REPORT_*.md` — rapports experimentaux
2. `research_archive/discoveries/CONJECTURES_TRACKER.md` — etat des conjectures
3. `research_archive/discoveries/DISCOVERIES_INDEX.md` — decouvertes
4. `research_archive/manuscript/*.md` — chapitres existants du manuscrit
5. `_staging/matheux/GLOSSAIRE_DETAILED.md` — formules exactes
6. `_staging/scientist/ANALYSE_TRANSVERSE_SCIENTIFIQUE.md` — synthese

## Processus

### Etape 1 — Identifier les resultats a integrer

```
Lire CONJECTURES_TRACKER.md
Filtrer : conjectures avec VALIDATED EXPERIMENTALLY depuis la derniere maj manuscrit
Lire les EXPERIMENT_REPORT correspondants
```

### Etape 2 — Identifier le chapitre cible

| Conjecture | Chapitre | Section |
|-----------|----------|---------|
| C1 (δ⁰ insuffisant) | Ch.3 Framework + Ch.6 Experiences | 3.2, 6.1 |
| C2 (δ³ necessaire) | Ch.3 Framework + Ch.7 Defenses | 3.4, 7.1 |
| C3 (alignement superficiel) | Ch.2 Etat de l'art + Ch.6 Experiences | 2.3, 6.2 |
| C4 (Sep(M) mesurable) | Ch.4 Metriques + Ch.6 Experiences | 4.2, 6.3 |
| C5 (cosinus insuffisant) | Ch.4 Metriques | 4.3 |
| C6 (medical vulnerable) | Ch.5 Attaques + Ch.6 Experiences | 5.3, 6.4 |
| C7 (paradoxe raisonnement) | Ch.5 Attaques + Ch.6 Experiences | 5.4, 6.5 |
| C8 (peer-preservation) | Ch.7 Defenses + Ch.8 Discussion | 7.4, 8.2 |
| D-001 (Triple Convergence) | Ch.6 Experiences | 6.1 |

### Etape 3 — Generer le texte

Pour chaque resultat SUPPORTED :

1. **Paragraphe principal** :
   - Enonce de la conjecture
   - Protocole experimental (N, modele, conditions)
   - Resultat principal avec chiffres exacts
   - Intervalle de confiance 95%
   - p-value et taille d'effet
   - Interpretation

2. **Format obligatoire** :
```
Nous demontrons experimentalement que [conjecture en langage naturel].
Le protocole consiste en [N] runs sur [modele] avec [conditions].
Le resultat principal est [metrique] = [valeur] (IC 95% [[lower], [upper]],
N=[N], p=[p-value], Cohen's f=[f], [interpretation]).
Ce resultat [supporte/refute] la conjecture [CX] avec un niveau
de confiance [XX]%.
```

3. **Tableau de resultats** (si multi-conditions) :
```markdown
| Condition | Metrique | IC 95% | N |
```

4. **Reference au rapport** :
```
(EXPERIMENT_REPORT_[ID], [date], script: [script])
```

### Etape 4 — Inserer dans le manuscrit

1. Identifier le fichier manuscript/ correspondant
2. Trouver la section cible (via les headings)
3. Inserer le paragraphe + tableau APRES le texte theorique existant
4. Ne pas ecraser le texte existant — AJOUTER a la fin de la section
5. Marquer l'insertion : `<!-- EXPERIMENTAL: [experiment_id] -->`

### Etape 5 — Verification

1. Lancer `audit-these` sur le chapitre modifie
2. Verifier coherence avec les autres chapitres
3. Verifier que les chiffres correspondent au JSON source

## Regles ABSOLUES

1. **Ne cite QUE des resultats avec p < 0.05 et N >= 30** — rien d'autre dans la these
2. **Jamais de chiffre sans IC 95%** — un ASR sans IC n'est pas publiable
3. **Jamais de p-value sans taille d'effet** — un p significatif avec effet negligeable est trompeur
4. **Chapitres a maturite > 90% : ne pas modifier sans approbation** — creer le paragraphe dans un fichier _pending
5. **δ⁰ δ¹ δ² δ³** (Unicode obligatoire)
6. **References inline** : chaque chiffre pointe vers son EXPERIMENT_REPORT
7. **Tags** : `[EXPERIMENTAL]` pour tout resultat issu d'une campagne AEGIS
8. **Pas de remplissage** : mieux vaut un paragraphe court et exact qu'un long et vague

## Sortie

- `manuscript/chapitre_X.md` — mis a jour (ou `manuscript/_pending/insert_[CX]_[experiment_id].md` si maturite > 90%)
- `_staging/signals/MANUSCRIPT_UPDATED_[CX]`
- Log dans `_staging/thesis-writer/INTEGRATION_LOG.md`

## Agent

- 1 agent Opus (qualite redactionnelle doctorale)
- Temps estime : 10-15 min par section
- Langue : francais (termes techniques en anglais)
