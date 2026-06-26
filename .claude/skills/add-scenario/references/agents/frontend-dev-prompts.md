# Frontend Dev Agent — Prompt Templates
# Référencé par : SKILL.md Phase 2a

## Prompt 1 — Générer le bloc case ScenarioHelpModal

Passer à l'agent Frontend Dev. Produit un bloc case JSX prêt à coller.

```xml
<context>
Tu ajoutes une entrée dans ScenarioHelpModal.jsx pour un nouveau scénario AEGIS Red Team.
Le fichier utilise un switch où chaque case retourne un objet JS plain (pas du JSX).
Pattern existant : case "scenario_id": return { title, objective, technique, delta,
conjecture, mitre, svc_expected, steps: [...] };

Paramètres confirmés :
  scenario_id      : {scenario_id}
  attack_type      : {attack_type}
  target_delta     : {target_delta}
  conjecture       : {conjecture}
  clinical_context : {clinical_context}
  svc_score        : {SVC de Backend Dev}
  mitre_ttps       : {MITRE TTPs de Backend Dev ou Scientist}

Résumé du prompt forgé : {une phrase résumant ce que fait le prompt forgé}
</context>

<instructions>
Générer le bloc case en suivant exactement le pattern du fichier existant.
Règles :
- Pas de template literals avec ${} — esbuild casse sur eux dans les fichiers .jsx
- svc_expected doit être le SVC réel calculé par Backend Dev, pas un placeholder
- Tableau steps : 1 à 3 items, chacun une chaîne plain décrivant ce qui se passe
- technique : nommer la technique d'attaque spécifique utilisée
  (ex : "Triple authority chain + HL7 OBX injection")
- conjecture : utiliser exactement "C1", "C2", ou "null" (chaîne, pas null JS)
</instructions>

<output_format>
case "{scenario_id}":
  return {
    title: "...",
    objective: "...",
    technique: "...",
    delta: "delta{1|2|3}",
    conjecture: "C1|C2|null",
    mitre: "T..., T...",
    svc_expected: 0.XX,
    steps: [
      "...",
    ],
  };
</output_format>
```

---

## Prompt 2 — Vérification incrémentation badge

Après incrément du count badge dans ScenariosView.jsx :

```xml
<context>
La ligne badge dans ScenariosView.jsx affiche le count total de scénarios.
Elle doit correspondre exactement au count Python backend — source de vérité unique :
backend/scenarios.py.
</context>

<instructions>
1. Lancer : python -c "from backend.scenarios import get_all_scenarios; print(len(get_all_scenarios()))"
2. Lire la ligne badge courante : grep -n "chains / [0-9]* scenarios" ScenariosView.jsx
3. Si les nombres diffèrent, mettre à jour la ligne badge pour correspondre au count backend.
4. Ne jamais fixer le badge count manuellement — toujours dériver de get_all_scenarios().
</instructions>

<output_format>
BADGE_REPORT:
  backend_count    : {N}
  jsx_count_before : {N-1}
  jsx_count_after  : {N}
  status           : COHERENT | MISMATCH_FIXED | MISMATCH_UNFIXABLE
</output_format>
```

---

## Prompt 3 — Interprétation du résultat Vite build

Après `npx vite build`, interpréter l'output :

```xml
<instructions>
Parser l'output Vite build :
- "built in Xs" sans erreurs = PASS
- "X error(s)" = FAIL — lire la première erreur, identifier le fichier et la ligne
- Échec le plus courant dans ce codebase : template literal `${}` dans un champ message de .jsx
  Fix : remplacer la chaîne backtick par une chaîne single-quoted + concaténation

Si le build échoue :
1. Lire le fichier erreur à la ligne indiquée
2. Trouver le template literal
3. Remplacer : `text ${var} text` → 'text ' + var + ' text'
4. Relancer le build

Reporter : BUILD_PASS | BUILD_FAIL — {résumé erreur et fix appliqué}
</instructions>
```

---

## Référence anti-patterns esbuild / JSX

| Anti-pattern | Cause | Fix |
|--------------|-------|-----|
| `` `...\${var}...` `` dans message= | esbuild mal-parse comme expression JSX | `'...' + var + '...'` |
| `<br>` dans une chaîne | esbuild traite comme tag JSX | `'\n'` ou `'\\n'` |
| `&` nu dans chaîne passée à JSX | problème d'entité HTML | `'&amp;'` |

---

## Fichiers touchés par Frontend Dev

| Fichier | Action |
|---------|--------|
| `frontend/src/components/redteam/views/ScenariosView.jsx` | Incrémenter badge count |
| `frontend/src/components/redteam/ScenarioHelpModal.jsx` | Ajouter case block |

**Ne pas modifier en Phase 2a** (géré par d'autres phases) :
- `backend/scenarios.py` — Backend Dev (Phase 1b)
- `README.md` et variantes — Red Team IA (Phase 3)
- `formal_framework_complete.md` — Mathematician (Phase 3)
