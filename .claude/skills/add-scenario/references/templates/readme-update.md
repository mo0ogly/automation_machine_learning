# Template : Mise à jour README
# Utilisé par : Red Team IA specialist (Phase 3)
# Fichiers : README.md, README_FR.md, README_BR.md, backend/README.md

## Commande de détection

```bash
grep -n "scenario" README.md README_FR.md README_BR.md backend/README.md \
  | grep -E "[0-9]+ scenario"
```

## Pattern de mise à jour

Trouver la ligne count et incrémenter de 1. Patterns courants :

| Fichier | Pattern à trouver | Exemple |
|---------|------------------|---------|
| README.md | `**N scenarios**` ou `N attack scenarios` | `48 → 49` |
| README_FR.md | `**N scénarios**` ou `N scénarios d'attaque` | `48 → 49` |
| README_BR.md | `**N cenários**` ou `N cenários de ataque` | `48 → 49` |
| backend/README.md | `N scenarios` ou `SCENARIO_CATALOG (N)` | `48 → 49` |

## Vérification de cohérence

```bash
python -c "
from backend.scenarios import get_all_scenarios
import re, sys

backend_n = len(get_all_scenarios())
files = ['README.md', 'README_FR.md', 'README_BR.md', 'backend/README.md']
for f in files:
    try:
        content = open(f).read()
        m = re.search(r'(\d+)\s+scenario', content, re.IGNORECASE)
        n = int(m.group(1)) if m else -1
        status = 'OK' if n == backend_n else 'MISMATCH (found ' + str(n) + ', expected ' + str(backend_n) + ')'
        print(f + ': ' + status)
    except FileNotFoundError:
        print(f + ': NOT FOUND')
"
```

Les 4 fichiers doivent afficher `OK`. Tout `MISMATCH` est une anomalie → auto-correction en mettant à jour le count.

---

## Anomalie : COUNT_MISMATCH

Si le count README ne correspond pas à `get_all_scenarios()` :
1. Lancer la vérification ci-dessus pour identifier les fichiers incorrects
2. Corriger chaque fichier individuellement (jamais de sed global — trop fragile)
3. Relancer la vérification pour confirmer
4. Logger dans RETEX : `COUNT_MISMATCH: corrigé dans {filenames}`

## Ce qu'il NE FAUT PAS mettre à jour

Ne pas toucher ces fichiers en Phase 3 (gérés par d'autres phases) :
- `ScenariosView.jsx` badge — Frontend Dev (Phase 2a)
- `ScenarioHelpModal.jsx` — Frontend Dev (Phase 2a)
- `scenarios.py` — Backend Dev (Phase 1b)
