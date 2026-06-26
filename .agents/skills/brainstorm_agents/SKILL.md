---
name: brainstorm_agents
description: Orchestre N subagents parallèles sur un sujet avec collecte structurée des rapports. Adapté de brainstorm-agents pour Antigravity.
---

# BRAINSTORM-AGENTS -- Orchestrateur de Subagents Parallèles (Antigravity)

Lance N subagents en parallèle via `invoke_subagent`, chacun spécialisé sur un domaine ou une question,
collecte les rapports structurés via leurs messages de retour, et consolide les résultats.

## Syntaxe et Déclenchement

Se déclenche lorsque l'utilisateur demande `/brainstorm-agents <sujet> --domains="dom1,dom2,..."`, ou lorsqu'un besoin d'audit/brainstorming multi-domaine est identifié (ex: préparation ML pour plusieurs types d'algorithmes).

## TRAÇABILITÉ AGENTIQUE (OBLIGATOIRE)

### Plan persistant
Créer `_alire/tracking/PLAN_BRAINSTORM_{SUJET}_{YYYY-MM-DD}.md`.

### Decision log
Logger dans `_alire/02_LOGS/Journals/decision_log.jsonl` les décisions non-triviales.

### Replanification
Si des agents échouent, analyser et relancer via `invoke_subagent` ou redéfinir la stratégie.

## WORKFLOW

### Étape 1 : Préparation des prompts
Pour chaque domaine, préparer un prompt spécifique :
"Tu es un expert spécialisé sur le domaine '{domaine}'.
Sujet : {sujet}
Mission : Analyser l'état actuel, identifier forces/faiblesses/gaps et proposer des Quick Wins.
Format obligatoire :
## Score : XX/100
## Forces
## Faiblesses (GAPS)
## Quick Wins"

### Étape 2 : Lancement parallèle
Utiliser l'outil `invoke_subagent` avec un tableau `Subagents`.
**RÈGLE STRICTE** : TOUJOURS lancer tous les subagents dans UN SEUL APPEL à `invoke_subagent` (pas de séquentiel).
Type d'agent recommandé : `research` ou `self`.

### Étape 3 : Collecte et consolidation
Attendre que le système vous notifie du retour des subagents (ne pas bloquer).
Pour chaque agent terminé, sauvegarder son rapport dans `_alire/temp/brainstorm/`.
Générer un fichier `CONSOLIDATED.md` contenant la synthèse des scores et des recommandations.

## RÈGLES
1. **1 appel d'outil = N subagents.** Jamais de lancement séquentiel entre domaines.
2. **Subagents read-only par défaut.** Ils auditent ou recherchent, le parent coordonne.
3. **Format obligatoire.** Chaque rapport DOIT contenir un score.
4. **Annonce de fin obligatoire.** Toujours annoncer la prochaine étape une fois la consolidation terminée.
