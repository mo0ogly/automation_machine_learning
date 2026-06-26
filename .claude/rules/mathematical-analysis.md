# Regles d'analyse mathematique — AEGIS (ENS, 2026)

## QUALIFICATION EPISTEMIQUE — AVANT TOUTE ANALYSE

Chaque papier contenant des resultats formels DOIT etre classe :

| Nature | Critere | Tag |
|--------|---------|-----|
| Theoreme/Preuve | Demonstration formelle (existence, unicite, borne, convergence) | `[THEOREME]` |
| Conjecture/Empirique | Resultat observe mais non prouve, experiences numeriques tenant lieu de preuve | `[EMPIRIQUE]` |
| Algorithme/Methode | Contribution algorithmique — avec ou sans garanties (complexite, convergence) | `[ALGORITHME]` |
| Heuristique | Algorithme SANS borne de convergence, meme performant | `[HEURISTIQUE]` |
| Survey | Synthese — avec ou sans taxonomie originale | `[SURVEY]` |

**Un scaling law empirique n'est PAS un theoreme. Une heuristique performante n'est PAS un algorithme avec garanties.**

## ANALYSE DES HYPOTHESES — LA CLE

Un theoreme vaut EXACTEMENT ce que valent ses conditions.

### Grille obligatoire

Pour chaque resultat formel cite dans la these, remplir :

| Hypothese | Explicite/Implicite | Force | Verifiable en pratique ? | Commentaire |
|-----------|-------------------|-------|------------------------|-------------|
| H1 : i.i.d. | Explicite | Forte | Non (donnees reelles) | Gap theorie/pratique |
| H2 : convexite | Implicite | Forte | Rarement en deep learning | Resultat non applicable directement |
| H3 : sub-Gaussien | Explicite | Moyenne | A verifier empiriquement | |

### Signaux d'alerte

- Hypothese de convexite non questionnee → deep learning est NON-convexe
- "Avec haute probabilite" → sur quelle mesure ? regime asymptotique n→∞ ou d→∞ ?
- Complexite asymptotique sans constantes → O(n²) avec constante 10⁶ vs O(n³) avec constante 10⁻³
- Bornes vides → la borne est-elle exploitable en pratique ou seulement en dimension infinie ?

## VERIFICATION DES PREUVES

### Protocole

1. **Identifier le lemme central** dont tout decoule (souvent Lemma 3.1 ou Proposition centrale)
2. **Verifier chaque implication** : pour chaque ⟹ ou "donc", demander : trivial ? necessite une hypothese non utilisee ? contre-exemple possible ?
3. **Cas limites** : tester mentalement n=1, distribution de Dirac, dimension infinie, gradients nuls
4. **Appendices** : JAMAIS ignorer "voir Appendice A" — c'est la que se cachent les hypotheses supplementaires

### Outils de verification

| Outil | Usage |
|-------|-------|
| Lean 4 / Mathlib | Verification formelle pour resultats critiques |
| Proof Wiki | Verifier les lemmes standards utilises |
| zbMATH Open | Index mathematique formel, reviews par mathematiciens |
| MathSciNet (AMS) | Base de reference, citations formelles |

## RIGUEUR STATISTIQUE

### Checklist formelle

1. **Bornes de generalisation** : PAC-learning, VC-dimension, Rademacher, information-theoretic ? Performance empirique sans borne theorique = anecdote
2. **Regime de validite** : resultats asymptotiques (n→∞) pertinents pour les N effectifs ? Resultats non-asymptotiques (finite-sample) plus exploitables
3. **Tests statistiques** : adaptes a la structure des donnees ? Puissance calculee ? Correction multiple (Bonferroni, BH) quand comparaisons multiples ?
4. **Reproductibilite numerique** : variance entre runs ? Seed fixee ? Resultats non reproductibles = suspects

### References statistiques cles

- Wainwright (2019) — High-Dimensional Statistics (concentration inequalities, minimax)
- Shalev-Shwartz & Ben-David (2014) — Understanding ML (PAC, Rademacher, VC)
- Boucheron, Lugosi, Massart (2013) — Concentration Inequalities (Hoeffding, Bernstein, McDiarmid)

## POSITIONNEMENT FORMEL

1. **Comparaison bornes minimax** : le resultat atteint-il la borne optimale ? Quel est le gap ?
2. **Generalisation ou specialisation** : hypotheses plus faibles (generalisation) ou plus fortes avec gain en constante (specialisation) ?
3. **Travaux simultanes** : verifier les dates arXiv de la meme semaine — memes resultats ?

## TEMPLATE FICHE MATHEMATICIEN

Chaque papier avec des resultats formels DOIT avoir cette fiche dans `_staging/matheux/` :

```markdown
## [Auteurs, Annee] — Titre

**Reference** : arXiv:XXXX.XXXXX / DOI:XX.XXXX
**Revue/Conf** : [Nom, CORE Ranking]
**MSC 2020** : [Codes classification mathematique]
**Nature** : [THEOREME] / [EMPIRIQUE] / [ALGORITHME] / [HEURISTIQUE] / [SURVEY]

### Resultat principal
**Theoreme X.X** (Hypotheses : H1, ..., Hn)
[Enonce formel EXACT — copier-coller la notation originale du papier]
(Section X.Y, p. XX, Eq. NN)

### Hypotheses — analyse
| Hypothese | Explicite/Implicite | Force | Verifiable ? | Commentaire |
|-----------|-------------------|-------|--------------|-------------|
| H1 | | | | |
| H2 | | | | |

### Idee centrale de la preuve (5-10 lignes)
Quel est l'insight mathematique non trivial ?
Lemme central : ... (Section X, Lemma Y)
Inegalite cle : ... (Eq. NN)
Argument : [concentration / couplage / compacite / martingale / ...]

### Lacunes et questions ouvertes
- Ce que le resultat ne prouve PAS
- Prochaine etape naturelle
- Conjectures des auteurs (Section Discussion)

### Pertinence these AEGIS
**Role** : [Outil / Baseline / Contre-exemple / Inspiration]
- Hypothese a relacher pour notre contribution : ...
- Lien avec formules AEGIS : F01-F72
- Lien avec conjectures : C1-C7
```

## APPLICATION A AEGIS — FORMULES F01-F72

Chaque formule du glossaire DOIT specifier :

1. **Nature epistemique** : theoreme (prouve) / empirique (observe) / heuristique (pas de garantie)
2. **Hypotheses sous-jacentes** : sous quelles conditions la formule est-elle valide ?
3. **Reference exacte** : `(Auteur, Annee, Section X, Eq. Y, p. Z)`
4. **Bornes connues** : borne superieure/inferieure, optimale ou pas ?
5. **Regime de validite** : asymptotique ou finite-sample ? N minimal ?

Exemples corrects :
- `F15 Sep(M) : defini dans (Zverev et al., 2025, ICLR, Definition 2, p.4) [THEOREME — definition formelle]`
- `F22 ASR : metrique empirique sans borne theorique [EMPIRIQUE — pas de garantie de convergence]`
- `F44 I_t martingale : prouve dans (Young, 2026, Theorem 8, p.12) [THEOREME — decomposition martingale avec preuve constructive]`
- `F46 Recovery Penalty : propose dans (Young, 2026, Section 6, Eq.19) [HEURISTIQUE — objectif propose sans validation empirique]`
