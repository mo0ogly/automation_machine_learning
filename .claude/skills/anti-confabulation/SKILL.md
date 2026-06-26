---
name: anti-confabulation
description: "Garantit la tracabilite de chaque affirmation dans un livrable de recherche AEGIS (these ENS, 2026) et produit un score de tracabilite qui conditionne la sortie du livrable. Chaque chiffre, citation ou resultat est soit source, soit marque comme hypothese, estimation ou projection. Utiliser des que l'utilisateur redige ou fait relire une fiche d'attaque, une section de these, une analyse bibliographique, une note technique ou un contenu a sources citees, et des qu'apparaissent des metriques (ASR, Sep(M), taux de detection, FPR), des references academiques, ou des valeurs de parametres (poids SVC, seuils). Utiliser aussi pour auditer un texte existant et lister les affirmations non sourcees avec leur score. Triggers on: 'anti-confabulation', 'verifie les sources', 'cite tes references', 'score de tracabilite', 'fiche d'attaque', 'section de these', 'ASR projete'."
metadata:
  user_invocable: "true"
  argument_hint: "[chemin du fichier a auditer, ou rien pour le mode redaction]"
---

> **PREMIERE ACTION OBLIGATOIRE :** annoncer "Using anti-confabulation skill." en premiere ligne de reponse, puis preciser le mode retenu (REDACTION ou AUDIT).

# Anti-Confabulation

Ce skill encadre la production et la relecture de tout livrable ou chaque affirmation engage la credibilite scientifique de la these : fiche d'attaque, section de manuscrit, analyse bibliographique, note technique, post a sources citees. Il existe pour une raison simple : un modele de langage produit du texte fluide par defaut, et la fluidite masque les inventions. Le role du skill est de rendre chaque affirmation tracable ou explicitement incertaine, puis de la scorer, de sorte qu'un relecteur, un directeur de these ou un jury puisse verifier ou contester sans avoir a deviner ce qui est solide et ce qui ne l'est pas.

## Principe fondamental

Toute affirmation releve de l'un des deux cas suivants, sans troisieme possibilite :

1. elle est tracable a une source verifiable (publication, code, mesure experimentale), citee precisement ;
2. elle est explicitement marquee comme hypothese, estimation ou projection.

Aucune invention n'est permise, meme au profit d'un texte mieux ecrit. Un texte incomplet mais honnete vaut infiniment mieux qu'un texte fluide mais confabule. Chaque fois que le choix se pose entre fluidite et tracabilite, choisir la tracabilite.

## Quand utiliser ce skill

Declencher des que la tache consiste a produire ou relire un contenu qui avance des faits verifiables : redaction d'une fiche d'attaque ou d'une section de these, analyse bibliographique (P-ID), rapport chiffre, contenu LinkedIn a sources reelles, ou audit d'un document existant pour reperer les affirmations non sourcees. Declencher aussi des qu'apparaissent des metriques (ASR, Sep(M), taux de detection, FPR), des references academiques, ou des valeurs de parametres (poids SVC, seuils tau, coefficients).

Ne pas declencher pour de la conversation, du brainstorming exploratoire explicitement etiquete comme tel, ou du code sans affirmation empirique.

## Securite content filter

En mode AUDIT sur le depot poc_medical, ne jamais lire les fichiers sensibles (cf. CLAUDE.md) : `scenarios.py`, `attack_catalog.py`, les valeurs de `i18n.js`, le champ `template` des `prompts/*.json`. Auditer via les metadonnees et les fichiers .md uniquement. Si un content filter se declenche, logger l'incident et passer a la cible suivante ; ne jamais tenter de le contourner.

## Deux modes de fonctionnement

**Mode REDACTION.** L'utilisateur demande de produire du contenu neuf. Appliquer les tags en ligne au fil de la redaction, puis passer la checklist et produire le rapport de scoring avant livraison.

**Mode AUDIT.** L'utilisateur fournit un texte existant (ou un chemin de fichier). Produire un tableau de toutes les affirmations verifiables, chacune avec son tag et son statut, puis le scoring et une liste d'actions. Ne pas reecrire le texte sans demande explicite ; preserver l'original.

## Taxonomie des tags

Chaque affirmation verifiable porte exactement un tag.

| Tag | Signification | Exigence attachee |
|-----|---------------|-------------------|
| `[SOURCE]` | Tracable a une publication | Citation complete : auteurs, venue, annee, section ou page si possible |
| `[MESURE]` | Resultat experimental du projet | Fichier de resultats bruts reference, N, intervalle de confiance, config exacte |
| `[CODE]` | Reference au code du projet | Fichier, ligne, commit hash |
| `[ESTIMATION]` | Valeur estimee sans mesure directe | Methode d'estimation explicitee, bornes d'incertitude |
| `[HYPOTHESE]` | Affirmation non demontree | Marquee comme telle, conditions de falsification specifiees |
| `[PROJECTION]` | Performance attendue mais non mesuree | Base de la projection explicitee : quelle source, quel raisonnement |
| `[A VERIFIER]` | Affirmation qui necessite verification | Action item explicite, jamais laisse sans suite |

Un cadre formel original (definition, fonction, modele) se note `[CONTRIBUTION]` et n'appelle pas de verification : c'est une construction, pas une affirmation empirique.

## Regles non negociables

Ces six regles sont la raison d'etre du skill. Elles sont volontairement strictes parce que chacune correspond a un mode de confabulation observe.

1. **Jamais inventer de reference.** Si une reference est necessaire et inconnue, ecrire `[A VERIFIER : source necessaire pour X]`. Ne jamais fabriquer un titre, des auteurs ou une venue.

2. **Jamais inventer de chiffre.** Tout chiffre est soit cite avec sa source, soit marque `[ESTIMATION : base sur ...]`, soit marque `[A REMPLIR]` s'il s'agit d'un resultat experimental a venir.

3. **Jamais presenter une projection comme une mesure.** Une valeur n'est une mesure que lorsque les runs ont ete executes (N >= 30 par condition, cf. regles doctorales). Avant cela, ecrire par exemple "ASR projete de l'ordre de 60% [PROJECTION : base sur ...]" ou "ASR [A MESURER]". Le vocabulaire doit refleter le statut reel.

4. **Jamais confabuler une publication.** En cas de doute sur l'existence d'un papier, chercher d'abord sur le web (ou cross-check ChromaDB via le COLLECTOR). Si introuvable, ecrire `[A VERIFIER : existence de la reference X]`. Le doute se documente, il ne se comble pas par l'invention.

5. **Toujours distinguer le cadre formel des valeurs.** Une definition est une construction legitime ("Soit Trust(i) = somme des wk fois authk"). Les valeurs des parametres (par exemple w1 = 0.35, tau = 0.50) sont des estimations qui doivent etre sourcees ou marquees `[ESTIMATION]`. Ne jamais laisser un lecteur croire qu'une valeur de parametre est demontree parce que le cadre qui l'entoure est rigoureux.

6. **Preferer l'honnetete a la fluidite.** Un texte qui porte dix fois `[A VERIFIER]` est meilleur qu'un texte fluide avec trois confabulations cachees. Les marqueurs ne sont pas une faiblesse du livrable, ils en sont la rigueur.

## Points de vigilance

Les confabulations se logent presque toujours aux memes endroits. Verifier systematiquement ces categories.

**Metriques chiffrees (ASR, Sep(M), taux de detection, FPR).** Sont-ce des mesures ou des projections ? Tant qu'une campagne experimentale n'a pas tourne, ce sont des `[HYPOTHESE]`, `[ESTIMATION]` ou `[PROJECTION]`, jamais des `[MESURE]`.

**Taux de detection.** D'ou vient le chiffre ? S'il provient d'un papier, le citer avec `[SOURCE]` et verifier que la valeur est bien celle du papier et non un arrondi commode. Sinon, marquer `[ESTIMATION]`.

**Valeurs corrigees ou ajustees.** Une valeur tiree d'une source mais transposee a un autre contexte (par exemple un taux mesure sur des LLM medicaux applique a un contexte chirurgical) devient une `[PROJECTION]`, pas une mesure. Le saut de contexte doit etre signale.

**Probabilites composees.** Un produit de probabilites de detection suppose l'independance des detecteurs : c'est une `[HYPOTHESE]` a signaler explicitement, et les valeurs individuelles d'entree sont en general des `[ESTIMATION]`.

**Valeurs de parametres (poids SVC, seuils, coefficients).** Toujours sourcees ou marquees. Si elles sont attribuees a un papier, verifier qu'elles y figurent reellement et ne sont pas une interpolation.

**Affirmations de primeur.** "Le premier", "le seul", "aucun autre", "novel" : soumises au HUMILITY GATE des regles doctorales. Exigent un WebSearch de verification avant publication, sinon reformuler en "parmi les premiers" ou qualifier avec scope et date.

**Publications.** Toute reference doit exister. Verifier par recherche web avant de l'inclure (voir la procedure ci-dessous).

## Cadre formel contre valeurs : la distinction a ne pas rater

C'est le piege le plus subtil. Une formalisation mathematique originale (une definition, une fonction, un modele) est une contribution legitime et ne constitue pas une confabulation. En revanche, les valeurs numeriques que l'on injecte dans ce cadre sont des affirmations empiriques distinctes.

Exemple : "Soit hom(i) le degre d'homoglyphie de l'entree i" est une definition `[CONTRIBUTION]`. "hom(i) = 0.42 pour ce payload" est une mesure ou une estimation, a taguer comme telle. Ne jamais laisser la rigueur du cadre formel teinter de fausse certitude les valeurs qu'il contient.

## Verification web des references (obligatoire en mode REDACTION)

Avant d'inclure une reference academique dans un livrable :

1. Chercher la reference sur le web (titre, auteurs, venue, annee), ou cross-check le corpus via le COLLECTOR / ChromaDB.
2. Si elle est confirmee, citer avec `[SOURCE]` et la formulation exacte verifiee.
3. Si elle est introuvable ou douteuse, ne pas l'inclure comme acquise : ecrire `[A VERIFIER : existence de la reference X]`.
4. Distinguer la qualite de la source : un papier peer-reviewed et un billet de blog d'editeur ne se citent pas au meme niveau de confiance. Signaler quand une source est de qualite inferieure (par exemple `[SOURCE — qualite inferieure : blog editeur]`).

Ne jamais combler un manque de reference par une invention plausible. L'absence de source est une information, pas un trou a remplir.

## Checklist avant livraison

Avant de remettre un livrable produit en mode REDACTION, verifier point par point :

- [ ] Toutes les references citees existent reellement (recherche web effectuee en cas de doute)
- [ ] Les metriques (ASR, Sep(M), taux de detection, FPR) sont marquees `[MESURE]`, `[ESTIMATION]` ou `[PROJECTION]`
- [ ] Les taux de detection ont une source ou sont marques `[ESTIMATION]`
- [ ] Les valeurs corrigees ou projetees sont explicitement marquees comme projections
- [ ] Les hypotheses d'independance (probabilites composees) sont signalees
- [ ] Les valeurs de parametres (poids, seuils) sont sourcees ou marquees
- [ ] Les affirmations de primeur ont passe le HUMILITY GATE (WebSearch)
- [ ] Aucune publication n'est inventee
- [ ] Le cadre formel et les valeurs sont distingues

Si un point ne peut pas etre coche, le livrable n'est pas pret : ajouter le marqueur correspondant plutot que de livrer une affirmation non qualifiee.

## SCORING — Indice de Tracabilite (ITR)

Le scoring n'est pas decoratif : il conditionne la sortie du livrable, dans l'esprit du lint_sources de `/audit-these` (regle CLAUDE.md : plus de 5% de claims NONE = PAS DONE). Toute passe REDACTION ou AUDIT se termine par un score et un verdict.

### Score quantitatif

Definir :

- A = nombre total d'affirmations verifiables (chiffres, references, resultats, valeurs de parametres)
- Q = nombre d'affirmations correctement qualifiees (tag valide ET exigence du tag satisfaite)
- ITR = Q / A, exprime en pourcentage

Une affirmation est correctement qualifiee si :

- `[SOURCE]` : reference verifiee (web ou ChromaDB), citation complete
- `[MESURE]` : fichier de resultats reference, N et config presents
- `[CODE]` : fichier et ligne verifiables
- `[ESTIMATION]` : methode d'estimation explicitee
- `[HYPOTHESE]` / `[PROJECTION]` : base explicitee
- `[A VERIFIER]` : action item present (dette declaree, pas cachee)

### Verdict (gate de sortie)

| ITR | Verdict |
|-----|---------|
| 98% ou plus | CONFORME : le livrable peut sortir |
| 90% a moins de 98% | A CORRIGER : resoudre les dettes `[A VERIFIER]` avant diffusion |
| moins de 90% | NON CONFORME : refaire la passe |

**Fautes bloquantes (capping).** Toute publication inventee, ou toute projection presentee comme mesure, force le verdict a NON CONFORME quel que soit l'ITR. Ce sont les deux fautes les plus couteuses pour une these (cf. HUMILITY GATE et REFERENCES INLINE dans `.claude/rules/doctoral-research.md`). Le volume n'est jamais une excuse : "97 affirmations sur 97 taguees" ne vaut rien si une seule reference est inventee.

### Auto-evaluation agentique (sur 50)

A la fin de chaque passe, scorer sur 5 criteres (0 a 10 chacun) :

| Critere | Description | Score |
|---------|-------------|-------|
| Couverture du tagging | Chaque affirmation verifiable porte un tag | /10 |
| Verification des references | Chaque `[SOURCE]` confirmee, 0 publication inventee | /10 |
| Honnetete des statuts | Mesure, projection et estimation correctement distinguees | /10 |
| Distinction cadre formel / valeurs | Definitions vs valeurs de parametres separees | /10 |
| Tracabilite des dettes | Chaque `[A VERIFIER]` a une action, 0 dette cachee | /10 |
| **Total** | | **/50** |

Seuils : 45 ou plus exemplaire ; 35 a 44 acceptable avec ameliorations identifiees ; moins de 35 refaire la passe.

### Rapport de scoring (format obligatoire)

```
SCORING ANTI-CONFABULATION — {document} — {date}
ITR : {Q}/{A} = {pct}%
Verdict : CONFORME | A CORRIGER | NON CONFORME
Fautes bloquantes : {liste ou AUCUNE}
Auto-evaluation : {N}/50
Dettes ouvertes [A VERIFIER] : {N}
```

## Mode AUDIT : format de sortie

Pour auditer un texte existant, produire un tableau par section ou par fiche, le scoring, puis une synthese des actions.

```
## Audit : [nom du document ou de la section]

| Affirmation | Tag | Source ou probleme potentiel |
|-------------|-----|------------------------------|
| Citation exacte de l'affirmation | [TAG] | Source si presente, sinon nature du probleme |

[Rapport de scoring]

## Actions
- [A VERIFIER] References a confirmer (titre, auteurs, venue)
- [A MESURER] Valeurs presentees comme acquises mais non mesurees
- [A SOURCER] Estimations sans methode explicitee
```

Regles de l'audit :

- Ne lister que les affirmations verifiables. Une definition ou une construction theorique se note `[CONTRIBUTION]` et n'entre pas dans le denominateur A de l'ITR.
- Etre honnete sur les chiffres de detection arrondis : si un papier est cite mais que la valeur exacte n'a pas ete confirmee, marquer `[A VERIFIER : chiffre exact dans la source]`.
- Distinguer un calcul correct d'hypotheses incorrectes : un calcul peut etre juste alors que ses valeurs d'entree sont des estimations. Le signaler comme `[CALCUL base sur ESTIMATIONS]`.
- Ne pas reecrire le texte d'origine sans demande explicite.

## Integration dans le pipeline AEGIS

Le scoring anti-confabulation est complementaire de `/audit-these claims` (lint_sources) : lint_sources mesure la couverture des sources sur le corpus entier, anti-confabulation qualifie chaque affirmation d'un livrable unitaire et bloque sa sortie si le verdict n'est pas CONFORME.

| Skill | Quand declencher anti-confabulation | Mode |
|-------|-------------------------------------|------|
| fiche-attaque | Sur les sections texte des 3 agents, avant assemblage .docx | AUDIT + scoring |
| thesis-writer | Avant integration d'un passage au manuscrit | AUDIT + scoring |
| bibliography-maintainer | Sur chaque analyse P-ID produite | AUDIT |
| Redaction LinkedIn / note technique | Avant publication | REDACTION + scoring |

## Pourquoi cette discipline

Dans un travail de recherche, une seule reference inventee ou une seule projection presentee comme mesure suffit a discrediter l'ensemble. Le cout d'un marqueur `[A VERIFIER]` est nul ; le cout d'une confabulation decouverte par un relecteur, un jury ou un pair est la perte de credibilite du document entier. Ce skill optimise donc pour la verifiabilite, pas pour l'elegance apparente, et le score rend cette priorite mesurable.
