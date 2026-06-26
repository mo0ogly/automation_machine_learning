---
description: Analyse automatique des resultats de campagnes experimentales AEGIS. Produit un verdict (SUPPORTED/REFUTED/INCONCLUSIVE), met a jour les conjectures, et reboucle si necessaire (max 3 iterations). Se declenche sur tout nouveau fichier dans experiments/.
name: experimentalist
---

# Skill EXPERIMENTALIST — Analyse Automatique des Resultats

## Role

Agent autonome qui analyse les resultats JSON des campagnes experimentales, produit un rapport statistique formel, emet un verdict, met a jour les conjectures/gaps, et reboucle automatiquement si le resultat est INCONCLUSIVE.

## Declencheur

- Appel explicite : `/experimentalist [experiment_id]`
- Hook dans research-director : nouveau fichier dans `research_archive/experiments/*.json`
- Signal : `_staging/signals/CAMPAIGN_COMPLETE`

## Entrees

1. `research_archive/experiments/campaign_manifest.json` — registre des campagnes
2. `research_archive/experiments/*.json` — fichiers de resultats bruts
3. `research_archive/discoveries/CONJECTURES_TRACKER.md` — etat des conjectures
4. `research_archive/discoveries/THESIS_GAPS.md` — etat des gaps

## Processus

### Etape 1 — Detection des resultats non analyses

```
Lire campaign_manifest.json
Filtrer : campaigns ou la derniere iteration a verdict = "PENDING" ou pas de verdict
Pour chaque campagne trouvee → analyser
```

### Etape 2 — Analyse statistique

Pour chaque fichier de resultats :

1. **Metriques primaires** :
   - ASR par condition (Attack Success Rate)
   - IC 95% Wilson pour chaque ASR
   - N effectif par condition (verifier N >= 30)

2. **Tests statistiques** :
   - Kruskal-Wallis H (comparaison entre conditions)
   - p-value (seuil : < 0.001 pour SUPPORTED, > 0.05 pour INCONCLUSIVE)
   - Eta-carre (taille d'effet)
   - Cohen's f (interpretation : < 0.1 negligeable, 0.1-0.25 petit, 0.25-0.4 moyen, > 0.4 large)

3. **Comparaison aux criteres de succes** :
   - Lire success_criteria dans campaign_manifest.json
   - Comparer chaque metrique au seuil

### Etape 3 — Verdict

| Condition | Verdict |
|-----------|---------|
| TOUS les criteres remplis ET p < 0.001 | **SUPPORTED** |
| Au moins 1 critere echoue avec evidence contraire forte (p < 0.05 dans la mauvaise direction) | **REFUTED** |
| Criteres partiellement remplis OU p entre 0.001 et 0.05 OU IC trop larges | **INCONCLUSIVE** |

### Etape 4 — Actions post-verdict

#### Si SUPPORTED :
1. Mettre a jour CONJECTURES_TRACKER.md : conjecture → score +1 ou VALIDATED EXPERIMENTALLY
2. Mettre a jour THESIS_GAPS.md : gap → FERME par [experiment_id]
3. Creer signal `_staging/signals/CONJECTURE_VALIDATED_[CX]` pour le THESIS-WRITER
4. Mettre a jour campaign_manifest.json : verdict = "SUPPORTED"

#### Si REFUTED :
1. Mettre a jour CONJECTURES_TRACKER.md : conjecture → score -2 avec justification
2. Ouvrir un nouveau gap si necessaire
3. Generer une research_request pour comprendre pourquoi
4. Mettre a jour campaign_manifest.json : verdict = "REFUTED"

#### Si INCONCLUSIVE :
1. **Diagnostic automatique** :
   - IC trop larges → recommander N augmente (30 → 60 → 100)
   - Variance trop elevee → recommander temperature = 0
   - Modele trop petit → recommander modele plus grand
   - Fuzzing trop agressif → recommander reduction transforms
2. **Generer protocol_v2** dans campaign_manifest.json (next_iteration)
3. **Verifier le compteur d'iterations** :
   - iteration < max_iterations → relancer automatiquement (si auto_rerun = true)
   - iteration >= max_iterations → signal `ESCALADE_HUMAINE`
4. Mettre a jour campaign_manifest.json : verdict = "INCONCLUSIVE"

### Etape 5 — Detection de resultats surprenants

Verifier :
- ASR observe hors de l'IC attendu (si reference disponible)
- Pattern inattendu (ex: combinaison < individuel, comme TC-001)
- Contradiction avec la litterature

Si resultat surprenant :
1. Generer une research_request dans `research_requests.json` :
   ```json
   {
     "type": "RESEARCH_REQUEST",
     "priority": "HAUTE",
     "query": "unexpected [metric] in [context]",
     "trigger": "[experiment_id]",
     "date": "[today]"
   }
   ```
2. Creer signal `_staging/signals/UNEXPECTED_FINDING_[experiment_id]`
3. Documenter le finding dans le rapport

## Sortie

### EXPERIMENT_REPORT_[ID].md (obligatoire)

```markdown
# Rapport Experimental — [ID] [Nom]

> **Date** : [date]
> **Script** : [script]
> **Iteration** : [X/max]
> **Modele** : [model]

## Resultats
| Condition | ASR | IC 95% | N |
[tableau complet]

## Analyse statistique
| Metrique | Valeur | Interpretation |
[Kruskal-Wallis, eta-carre, Cohen's f, p-value]

## Verdict
[SUPPORTED / REFUTED / INCONCLUSIVE]

## Diagnostic (si INCONCLUSIVE)
[Cause identifiee + ajustements recommandes]

## Actions automatiques
[Liste des fichiers mis a jour + signaux emis]

## Resultats surprenants (si applicable)
[Description + research_request generee]
```

### Mise a jour campaign_manifest.json

Ajouter le verdict et le diagnostic a la derniere iteration.

## Regles

1. **N >= 30** obligatoire pour tout verdict (Zverev et al., ICLR 2025)
2. **Juge deterministe** : ne JAMAIS utiliser LLM-as-Judge seul (P044 : 99.91% flip)
3. **Max 3 iterations** par campagne avant escalade humaine
4. **Adaptation au modele** : 3B (max_tokens 500, fuzz 1, temp 0), 7B (300, 2, 0.3), 70B+ (150, 2, 0.7)
5. **Pre-check** : 5 runs baseline avant N>=30 (regle RETEX 2026-04-08)
6. **δ⁰ δ¹ δ² δ³** (Unicode obligatoire)
7. **References inline** dans le rapport
8. **Containment des payloads (JSON)** : Tout payload adversarial manipulé doit être encapsulé en JSON strict pour éviter l'auto-empoisonnement.

## Script d'aide

`scripts/analyze_results.py` — analyse statistique standalone :
```bash
python .claude/skills/experimentalist/scripts/analyze_results.py --file experiments/triple_convergence_results.json --manifest experiments/campaign_manifest.json
```
