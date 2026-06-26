# SCORING_CONFIG -- Configuration de scoring par defaut

> Ce fichier contient la configuration de scoring par defaut.
> A charger au debut de chaque cycle PDCA.
> Le fichier SCORING_CONFIG.json evolue a chaque phase ACT (nouveaux checks, poids ajustes, domaines ajoutes/retires).

## Structure

Le SCORING_CONFIG.json est place a la racine du repertoire `pdca/{perimetre}/`.
Il est cree au cycle 1 avec les valeurs par defaut ci-dessous, puis mis a jour a chaque A.4.

## JSON par defaut

```json
{
  "version": 2,
  "comment": "v2: ajout domaine code_hygiene (RETEX APEX 2026-03-18), reequilibrage poids",
  "domains": {
    "security": {
      "weight": 20,
      "checks": [
        {"id": "SEC-01", "name": "No raw fetch()", "type": "grep_count", "pattern": "await fetch(", "scope": "services/", "exclude": ["apiConfig.ts", "loggerService.ts"], "target": 0},
        {"id": "SEC-02", "name": "No hardcoded URLs", "type": "grep_count", "pattern": "localhost:8081", "target": 0},
        {"id": "SEC-03", "name": "No console.log", "type": "grep_count", "pattern": "console.log", "scope": "src/", "exclude": ["loggerService.ts"], "target": 0},
        {"id": "SEC-04", "name": "No fmt.Println", "type": "grep_count", "pattern": "fmt.Println", "scope": "cmd/", "target": 0},
        {"id": "SEC-05", "name": "No SQL injection patterns", "type": "grep_count", "pattern": "fmt.Sprintf.*SELECT|fmt.Sprintf.*INSERT|fmt.Sprintf.*UPDATE", "target": 0},
        {"id": "SEC-06", "name": "No SQLite in active build", "type": "grep_count", "pattern": "sql.Open.*sqlite3", "scope": "cmd/sigma_web/", "target": 0},
        {"id": "SEC-07", "name": "No XSS without DOMPurify", "type": "grep_count", "pattern": "dangerouslySetInnerHTML", "scope": "src/", "exclude_pattern": "DOMPurify", "target": 0}
      ]
    },
    "testing": {
      "weight": 15,
      "checks": [
        {"id": "TST-01", "name": "Go compiles (build_secure_lia.sh)", "type": "command", "cmd": "bash cmd/sigma_web/build_secure_lia.sh", "expect": "exit 0"},
        {"id": "TST-02", "name": "React compiles (vite build)", "type": "command", "cmd": "cd sigma-react-frontend && node node_modules/.bin/vite build", "expect": "exit 0"},
        {"id": "TST-03", "name": "Go test files exist", "type": "count_files", "pattern": "*_test.go", "target": ">10"},
        {"id": "TST-04", "name": "React test files exist", "type": "count_files", "pattern": "*.test.ts*", "scope": "sigma-react-frontend/", "target": ">10"},
        {"id": "TST-05", "name": "PostgreSQL reachable", "type": "command", "cmd": "psql -U lia_admin -d lia_scan -c 'SELECT 1' 2>/dev/null", "expect": "exit 0"},
        {"id": "TST-06", "name": "Vitest passes", "type": "command", "cmd": "cd sigma-react-frontend && npx vitest run 2>/dev/null", "expect": "exit 0"}
      ]
    },
    "architecture": {
      "weight": 15,
      "checks": [
        {"id": "ARC-01", "name": "LogSystemEvent adoption", "type": "adoption_rate", "pattern": "LogSystemEvent", "scope": "cmd/sigma_web/*.go", "target": ">80%"},
        {"id": "ARC-02", "name": "customLogger adoption", "type": "adoption_rate", "pattern": "customLogger", "scope": "sigma-react-frontend/src/services/*.ts", "target": ">80%"},
        {"id": "ARC-03", "name": "FK integrity", "type": "manual", "description": "All cross-table FK constraints exist"},
        {"id": "ARC-04", "name": "Migrations numbered", "type": "count_files", "pattern": "migrations/0*.sql", "scope": "cmd/sigma_web/"},
        {"id": "ARC-05", "name": "setCORSHeaders adoption", "type": "adoption_rate", "pattern": "setCORSHeaders", "scope": "cmd/sigma_web/*_api.go", "target": ">90%", "description": "Tous les handlers API doivent commencer par setCORSHeaders(w)"}
      ]
    },
    "code_hygiene": {
      "weight": 15,
      "comment": "Nouveau domaine v2 -- RETEX APEX 2026-03-18 (10/14 fichiers etaient dead code)",
      "checks": [
        {"id": "HYG-01", "name": "No stub files", "type": "grep_count", "pattern": "501.*Not Implemented|w.WriteHeader\\(501\\)|StatusNotImplemented", "scope": "cmd/sigma_web/", "target": 0, "description": "Aucun handler retournant 501/placeholder dans le build actif"},
        {"id": "HYG-02", "name": "Build whitelist aligned", "type": "diff_check", "description": "Tous les .go dans cmd/sigma_web/ sont dans build_secure_lia.sh OU explicitement exclus (.disabled)"},
        {"id": "HYG-03", "name": "Dead code ratio < 10%", "type": "dead_code_ratio", "description": "Fichiers dans le build dont les symboles publics ont 0 appels externes < 10% du total"},
        {"id": "HYG-04", "name": "No emoji in code/docs", "type": "grep_count", "pattern": "[\\x{1F600}-\\x{1F64F}\\x{1F300}-\\x{1F5FF}\\x{1F680}-\\x{1F6FF}\\x{2600}-\\x{26FF}]", "scope": "cmd/sigma_web/,sigma-react-frontend/src/", "target": 0},
        {"id": "HYG-05", "name": "MUI v7 Grid syntax", "type": "grep_count", "pattern": "<Grid item |<Grid.*item ", "scope": "sigma-react-frontend/src/", "target": 0, "description": "Ancienne syntaxe MUI v5/v6 interdite"},
        {"id": "HYG-06", "name": "No hardcoded fontFamily", "type": "grep_count", "pattern": "fontFamily:.*['\"]monospace['\"]|fontFamily:.*['\"]Arial|fontFamily:.*['\"]Fira Code", "scope": "sigma-react-frontend/src/components/", "target": 0, "description": "Utiliser fontFamily: 'inherit' ou theme.typography.fontFamily"},
        {"id": "HYG-07", "name": "Chip borderRadius: 1", "type": "manual", "description": "Tous les composants Chip MUI ont borderRadius: 1 (pas oval par defaut). Verifier via grep -rn 'Chip' dans le perimetre"},
        {"id": "HYG-08", "name": "No mock/placeholder data", "type": "grep_count", "pattern": "mock[Dd]ata|MOCK_|fakeDat|dummyDat|lorem ipsum|example\\.com", "scope": "cmd/sigma_web/,sigma-react-frontend/src/", "target": 0}
      ]
    },
    "completeness": {
      "weight": 15,
      "checks": [
        {"id": "CMP-01", "name": "CRUD endpoints complete", "type": "manual"},
        {"id": "CMP-02", "name": "Frontend connected", "type": "manual"},
        {"id": "CMP-03", "name": "No TODO/placeholder", "type": "grep_count", "pattern": "TODO|FIXME|placeholder|PLACEHOLDER", "target": 0}
      ]
    },
    "documentation": {
      "weight": 10,
      "checks": [
        {"id": "DOC-01", "name": "Module docs exist", "type": "file_exists", "path": "_alire/01_DOCUMENTATION/"},
        {"id": "DOC-02", "name": "API documented", "type": "manual"},
        {"id": "DOC-03", "name": "CLAUDE.md current", "type": "file_exists", "path": "CLAUDE.md"},
        {"id": "DOC-04", "name": "UI Help content exists", "type": "grep_count", "pattern": "HelpButton|useHelp", "scope": "sigma-react-frontend/src/components/{perimetre}*/", "target": ">0", "description": "Les ecrans du perimetre doivent avoir des HelpButton integres et du contenu dans ui_help_content"}
      ]
    },
    "benchmark_parity": {
      "weight": 10,
      "checks": [
        {"id": "BNC-01", "name": "Feature parity", "type": "gap_count", "description": "Number of features in benchmark absent from LIA-SEC"},
        {"id": "BNC-02", "name": "Unique advantages", "type": "manual", "description": "Features in LIA-SEC absent from benchmark"},
        {"id": "BNC-03", "name": "No regression", "type": "delta_check", "description": "No domain score decreased vs previous cycle"}
      ]
    }
  }
}
```

## Explication des types de checks

| Type | Description | Champs |
|------|-------------|--------|
| `grep_count` | Compte les occurrences d'un pattern. `target: 0` = aucune occurrence attendue | `pattern`, `scope`, `exclude`, `target` |
| `command` | Execute une commande shell. Verifie le code retour | `cmd`, `expect` |
| `count_files` | Compte les fichiers correspondant au pattern | `pattern`, `scope`, `target` |
| `adoption_rate` | Pourcentage de fichiers du scope qui contiennent le pattern | `pattern`, `scope`, `target` |
| `file_exists` | Verifie l'existence d'un fichier ou repertoire | `path` |
| `gap_count` | Nombre de gaps identifies (benchmark vs LIA-SEC) | `description` |
| `delta_check` | Verifie que le score n'a pas baisse vs cycle precedent | `description` |
| `manual` | Check manuel -- l'agent doit evaluer et justifier | `description` |

## Evolution du SCORING_CONFIG

A chaque phase A.4 (RETEX), le SCORING_CONFIG evolue :

- **AJOUTER checks** : nouveau check ID, type, query, justification
- **RETIRER checks** : check ID, raison (faux positif, obsolete)
- **AJUSTER poids** : domaine, ancien poids -> nouveau poids, justification
- **NOUVEAU domaine** : nom, poids, checks initiaux

Le champ `version` est incremente a chaque modification.
