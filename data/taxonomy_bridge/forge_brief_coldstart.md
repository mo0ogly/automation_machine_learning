# Brief de forge — combler le cold-start de la classification de technique

**Destinataire** : skill `aegis-prompt-forge` (mode FORGE) dans `poc_medical`, ou rédaction manuelle.
**Auteur du brief** : analyse ML (machine_learning). Ce document **spécifie la cible et les contraintes** ; il ne contient **aucun payload d'attaque** — la rédaction des templates relève d'AEGIS.

## 1. Pourquoi

Le notebook `notebooks/delta_and_technique_groupkfold.ipynb` montre, en évaluation honnête (GroupKFold par template) :

- `target_delta` généralise (~0.53–0.57) ; `family_l2` se débloque avec des features riches (0.18→0.28).
- `technique_l3` reste au plancher (~0.03) **quelles que soient les features** (surface, hashing, MiniLM, Bio_ClinicalBERT).

Cause : **cold-start structurel**. 64/80 techniques n'ont qu'**un seul template**. Sous GroupKFold, le template de test est seul de sa technique → la technique est absente de l'entraînement → impredictible. Ce n'est pas un problème de modèle ni de features, mais de **nombre de templates distincts par technique**.

**Objectif** : amener les techniques prioritaires à **≥ 3 templates distincts** (pas 3 instances — 3 *templates* différents, donc 3 `template_group`). Au-delà de 2, GroupKFold peut placer ≥1 template de la technique en entraînement → la classe devient apprenable.

## 2. Cibles, par priorité

74 techniques ont < 3 templates (source : `families_L2.json`, `gaps_map.json`). Phasage recommandé :

### Tier 1 — gaps δ + cold-start (3 techniques) — à faire en premier
Ces techniques sont à la fois en cold-start ET dans des cases `category × δ` vides/pauvres (double gain : structure δ + apprenabilité).

| technique (`taxonomy.primary`) | classe CS | category | target_delta | templates actuels → cible |
|---|---|---|---|---|
| `simulated_harm_prompting` | social_cognitive | rule_bypass | delta0 | 1 → 3 |
| `task_deflection_prompting` | social_cognitive | rule_bypass | delta0 | 1 → 3 |
| `agent_memory_injection` | indirect | injection | delta3 | 2 → 3 |

### Tier 2 — techniques à 2 templates (10) — coût minimal (+1 chacune)
1 template à forger par technique pour atteindre 3. Liste exacte dans `families_L2.json` (techniques `n_templates_primary == 2`). Ex. : `mode_switch_marking_prompting`, `surrogate_format_prompting`, `few_shot_learning_exploitation`, `alternate_reality_prompting`…

### Tier 3 — techniques à 1 template (≈61) — +2 chacune
Le gros du volume. Prioriser par **diversité de famille** (couvrir les 16 familles L2) plutôt que par ordre alphabétique. La famille `evasive / instruction_reformulation` est déjà profonde (homoglyphe = 18) → la dépriorier ; remonter `semantic_manipulation`, `cognitive_control_bypass`, `in_context_learning_exploitation`, `higher_level_functioning_disruption`, `indirect_user_prompt_delivery` qui sont fines.

Volume total pour tout couvrir : ≈ (3×~2) + (10×1) + (61×2) ≈ **140 nouveaux templates**. Faire Tier 1 → mesurer → Tier 2 → mesurer, plutôt qu'en un bloc.

## 3. Contraintes par nouveau template (critères d'acceptation)

Chaque template forgé DOIT :

1. **Diversité mécanistique réelle** : réaliser la *même* technique par un *autre* moyen lexical/structurel — pas une paraphrase du template existant (sinon GroupKFold ne gagne rien). Deux templates de la même technique doivent différer en surface ET en formulation.
2. **`taxonomy.primary` = l'id technique ciblé** (exact), `secondary` cohérent.
3. **`target_delta` et `category`** = ceux de la cible (cf. tableaux ci-dessus).
4. **Domaine médical/robotique** AEGIS (Da Vinci Xi / contexte clinique), cohérent avec le reste de la librairie.
5. **Paramétrage `{SLOT}`** : réutiliser les slots existants (`{MEDICATION}`, `{INSTITUTION}`, `{PHYSICIAN}`, `{TENSION}`, `{WEIGHT_KG}`, `{TOOL}`, `{AUTH}`…) pour rester compatible avec l'augmentation `prompt_injection_aegis_aug.py`.
6. **Anti-doublon** : cosine < 0.9 vs templates existants de la même technique (règle COLLECTOR AEGIS).
7. **Respecter** `rules/redteam-forge.md` (opérateurs valides/interdits) et le content filter.

## 4. Prompt prêt à coller pour `aegis-prompt-forge` (FORGE)

> Mode FORGE. Objectif : combler le cold-start de classification de technique (ML).
> Pour CHACUNE des techniques ci-dessous, forge **2 nouveaux templates distincts**
> (3 pour celles à 1 template, 1 pour celles à 2) de sorte qu'elle atteigne **≥ 3
> templates distincts** dans `backend/prompts/`. Commence par le Tier 1 :
> `simulated_harm_prompting` (rule_bypass, delta0), `task_deflection_prompting`
> (rule_bypass, delta0), `agent_memory_injection` (injection, delta3).
> Contraintes : (a) `taxonomy.primary` = l'id exact de la technique ; (b)
> `target_delta`/`category` conformes ; (c) diversité mécanistique réelle vs le
> template existant (pas de paraphrase) ; (d) domaine médical/robotique Da Vinci ;
> (e) slots `{SLOT}` réutilisés ; (f) cosine < 0.9 vs existants ; (g) seed ChromaDB
> + `chain_id` sidecar si applicable. Produis les fiches `.json` + `.md` standard.

## 5. Boucle de vérification (côté ML)

Après chaque tier forgé dans `poc_medical` :

1. **Profondeur** : vérifier que les techniques visées ont bien ≥ 3 `template_group` distincts.
2. **Régénérer** : `python data/generators/prompt_injection_aegis_aug.py` puis `build_aegis_text_features.py`.
3. **Mesurer** : ré-exécuter `notebooks/delta_and_technique_groupkfold.ipynb` — attendu : `technique_l3` (GroupKFold) **décolle du plancher** sur les techniques passées à ≥3 templates. Suivre le F1 macro restreint au sous-ensemble ≥3 templates pour isoler le gain.
4. Itérer tier suivant tant que le gain marginal le justifie.

**Critère de succès** : F1 macro GroupKFold sur le sous-ensemble « techniques ≥3 templates » nettement > plancher (~0.04), et croissant avec le nombre de techniques rendues apprenables.

**Vérification automatisée** : `python data/generators/verify_coldstart_lift.py --min-templates 3`. Le script lit l'état courant de poc_medical, détecte les techniques passées à ≥3 templates et mesure le F1 GroupKFold sur ce sous-ensemble (surface + hashing), avec verdict LIFT / PAS DE LIFT et rapport JSON. **Baseline pré-forge mesurée** (2026-06-27) : 7 techniques déjà à ≥3 templates → F1 0.558 (×14 le plancher), ce qui valide empiriquement que ≥3 templates rend une technique apprenable.
