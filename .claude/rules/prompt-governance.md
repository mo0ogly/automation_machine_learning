# Gouvernance des prompts LLM — ZERO hardcoding

**Règle absolue (projet automation_machine_learning).** Tout texte de prompt
envoyé à un LLM — system prompt, few-shot, persona, assistant, interprétation,
recommandation, explication… — DOIT être **éditable** et **repérable** dans
l'interface. **JAMAIS de prompt codé en dur** passé au modèle.

## Les 4 obligations (pour CHAQUE prompt)

1. **Résolu, pas en dur** : le prompt est obtenu via
   `prompt_store.STORE.resolve("<prompt_id>", DEFAULT_…)` dans `backend/agent_prompts.py`.
   Aucun `system = "Tu es…"` littéral passé directement à `_call_llm`.
2. **Default enregistré** : un default existe dans `agent_prompts` et le prompt
   est listé par `GET /api/prompts` (id + label).
3. **Éditable via l'UX** : il apparaît dans le panneau **« Prompts IA »**
   (Configuration ⚙ → IA → « Prompts IA… ») et peut être modifié / réinitialisé.
4. **Repérable via l'UX** : il porte une localisation (`localisation.view` +
   `data-prompt-loc` côté frontend) pour que le bouton **« Localiser »** y mène.

## Enforcement

- Avant de merger toute fonctionnalité LLM (nouvel endpoint, nouvelle persona,
  nouvel assistant) : vérifier que le prompt **apparaît dans `GET /api/prompts`**
  et se **localise** dans l'UI. Sinon, ce n'est PAS done.
- Audit rapide : `grep -nE '"(Tu es|You are|Réponds en JSON|Respond in JSON)' backend/*.py`
  → tout résultat hors `agent_prompts.py` (defaults) est une violation à corriger.
- Un nouveau prompt ⇒ un `prompt_id` + un default + une entrée de liste + une
  localisation. Pas d'exception « petit prompt rapide ».

## Failure mode documenté (2026-06-27)

`llm_agent._persona_messages` (personas « Synthèse exécutive » / « Revue analyste
expert » de la vue Exploiter, via `/analyze`) avait ses system prompts **codés en
dur** → invisibles et non éditables dans le panneau, alors que `recommend_system`,
`interpret_system` et `assist_system` passaient bien par `prompt_store`. Corrigé :
ajout de `executive_system` / `expert_system` au store + résolution dans
`_persona_messages`. C'est exactement le type de régression que cette règle interdit.
