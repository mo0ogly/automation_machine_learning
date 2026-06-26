# CHECK QUERIES -- Commandes et queries d'audit

> Ce fichier contient toutes les commandes grep/count, checks backend/frontend,
> et queries SQL utilisees dans les phases C.1 et C.2 du cycle PDCA.

## Checks securite automatiques (C.1)

| Check ID | Type | Query / Commande | Target | Scope |
|----------|------|-------------------|--------|-------|
| SEC-01 | grep_count | `grep -rn "await fetch(" {scope}/services/ --include="*.ts" --exclude="apiConfig.ts" --exclude="loggerService.ts"` | 0 | Frontend -- fetch() brut hors fetchWithConfig |
| SEC-02 | grep_count | `grep -rn "localhost:8081" {scope}` | 0 | Tous -- URLs hardcodees |
| SEC-03 | grep_count | `grep -rn "console.log" {scope}/src/ --include="*.ts" --include="*.tsx" --exclude="loggerService.ts"` | 0 | Frontend -- console.log |
| SEC-04 | grep_count | `grep -rn "fmt.Println" {scope}/cmd/ --include="*.go"` | 0 | Backend -- fmt.Println |
| SEC-05 | grep_count | `grep -rn "fmt.Sprintf.*SELECT\|fmt.Sprintf.*INSERT\|fmt.Sprintf.*UPDATE" {scope} --include="*.go"` | 0 | Backend -- SQL injection patterns |
| SEC-06 | grep_count | `grep -rn 'sql.Open.*sqlite3' {scope}/cmd/sigma_web/ --include="*.go"` | 0 | Backend -- SQLite dans fichiers build actif |
| SEC-07 | grep_count | `grep -rn "dangerouslySetInnerHTML" {scope} --include="*.tsx" \| grep -v "DOMPurify"` | 0 | Frontend -- XSS sans DOMPurify |
| SEC-08 | diff_check | Comparer fichiers `.go` dans `cmd/sigma_web/` vs liste dans `build_secure_lia.sh` | 0 manquants | Backend -- fichiers hors build |
| SEC-09 | adoption | `grep -rl "HelpButton" {scope}/*.tsx` vs `grep -rl "export default" {scope}/*.tsx` | 100% | Frontend -- composants sans HelpButton |
| SEC-10 | sql_count | `SELECT component, tab_key FROM ui_help_content WHERE component LIKE '{module}%'` | Toutes tabs couvertes | DB -- ecrans/tabs sans aide |

## Checks backend (C.2)

| Check ID | Type | Commande | Expected |
|----------|------|----------|----------|
| TST-01 | command | `go build -mod=mod ./cmd/sigma_web/` | exit 0 |
| TST-02 | command | `go vet ./...` | 0 warnings |
| TST-03 | count | `find {scope} -name "*_test.go" -type f \| wc -l` | > 10 |
| TST-04 | command | `go test -v -cover {scope}/...` (si tests existent) | PASS |

## Checks frontend (C.2)

| Check ID | Type | Commande | Expected |
|----------|------|----------|----------|
| TST-05 | command | `cd sigma-react-frontend && npm run build` | exit 0 |
| TST-06 | count | `find {scope} -name "*.test.ts" -o -name "*.test.tsx" \| wc -l` | > 10 |
| TST-07 | command | `cd sigma-react-frontend && npm test -- --coverage --watchAll=false` (si tests existent) | PASS |

## Checks UI Help (C.1 -- BLOQUANT)

| Check | Query | Condition FAIL |
|-------|-------|----------------|
| Composants vs HelpButton | `grep -rl "export default" {scope}/*.tsx` vs `grep -rl "HelpButton" {scope}/*.tsx` | composants > HelpButton |
| Entrees EN en base | `SELECT count(*) FROM ui_help_content WHERE component LIKE '{module}%' AND language='en'` | count = 0 |
| Entrees FR en base | `SELECT count(*) FROM ui_help_content WHERE component LIKE '{module}%' AND language='fr'` | count = 0 |
| Parite EN/FR | Comparer les deux counts ci-dessus | EN != FR |
| HelpButton par tab | Pour chaque composant avec tabs : verifier que `HelpButton` a un `tabKey` dynamique | tabKey manquant ou statique |

## Checks pre-flight (P.0 -- BLOQUANT)

| Check | Commande | Condition FAIL |
|-------|----------|----------------|
| Go build | `bash cmd/sigma_web/build_secure_lia.sh 2>&1 \| grep "Build réussi"` | Pas "Build réussi" |
| React build | `cd sigma-react-frontend && node node_modules/.bin/vite build 2>&1 \| tail -1` | Pas "built in" |
| PostgreSQL | `psql -U lia_admin -d lia_scan -c "SELECT 1" 2>/dev/null` | exit != 0 |
| Backend health | `curl -s -o /dev/null -w "%{http_code}" http://localhost:8081/api/health` | != 200 (warning, pas bloquant si audit offline) |

## Checks dead code triage (C.0 -- OBLIGATOIRE)

| Check | Commande | Description |
|-------|----------|-------------|
| Extraire symboles Go | `grep "^func \|^type " {fichier}.go \| awk '{print $2}' \| cut -d'(' -f1` | Liste symboles publics |
| Compter appels externes (cross-language) | `grep -rn "SymbolName" --include="*.go" --include="*.tsx" --include="*.ts" --include="*.py" . \| grep -v {fichier}.go \| wc -l` | 0 sur tous les langages = dead code certain |
| Ratio dead code | `(fichiers 0 appels / fichiers total) * 100` | > 10% = FAIL (HYG-03) |

> **Note :** le grep doit couvrir `.go`, `.tsx`, `.ts` et `.py` car un handler Go peut etre
> appele uniquement via route API depuis le frontend React. Un grep `.go` seul
> classerait ce handler comme DEAD alors qu'il est ACTIF.

Classification :

| Categorie | Critere | Action |
|-----------|---------|--------|
| ACTIF | Symboles appeles ailleurs | Inclure dans scoring |
| PROTOTYPE | Code propre, routes commentees, 0 appels | Exclure, signaler |
| DEAD | 0 appels, code obsolete | Exclure, proposer .disabled |

## Checks code hygiene (C.1 -- domaine code_hygiene)

| Check ID | Type | Query / Commande | Target | Scope |
|----------|------|-------------------|--------|-------|
| HYG-01 | grep_count | `grep -rn "501.*Not Implemented\|w.WriteHeader(501)\|StatusNotImplemented" cmd/sigma_web/ --include="*.go"` | 0 | Backend -- handlers stub 501 |
| HYG-02 | diff_check | Comparer `ls cmd/sigma_web/*.go` vs fichiers listes dans `build_secure_lia.sh` | 0 orphelins non .disabled | Backend -- alignement build |
| HYG-03 | dead_code_ratio | Script triage C.0 ci-dessus (voir section "Checks dead code triage") | < 10% | Backend -- ratio dead code. C.0 execute le triage ; HYG-03 mesure son resultat dans le scorecard. |
| HYG-04 | grep_count | `grep -Prn '[\x{1F600}-\x{1F64F}\x{1F300}-\x{1F5FF}\x{1F680}-\x{1F6FF}]' cmd/sigma_web/ sigma-react-frontend/src/` | 0 | Tous -- emoji |
| HYG-05 | grep_count | `grep -rn '<Grid item \|<Grid.*item ' sigma-react-frontend/src/ --include="*.tsx"` | 0 | Frontend -- ancienne syntaxe MUI v5 |
| HYG-06 | grep_count | `grep -rn "fontFamily:.*'monospace'\|fontFamily:.*'Arial'" sigma-react-frontend/src/components/ --include="*.tsx"` | 0 | Frontend -- polices hardcodees |
| HYG-07 | manual | `grep -rn 'Chip' sigma-react-frontend/src/components/{perimetre}/ --include="*.tsx"` -> verifier borderRadius: 1 | Tous Chip = borderRadius: 1 | Frontend -- pas d'ovales |
| HYG-08 | grep_count | `grep -rn "mockData\|MOCK_\|fakeData\|dummyData\|lorem ipsum\|example\.com" cmd/sigma_web/ sigma-react-frontend/src/` | 0 | Tous -- donnees fictives |

## Checks design quality (C.1 -- /frontend-design audit)

| Check | Description | Condition FAIL |
|-------|-------------|----------------|
| Design generique | Design generique/boilerplate AI ? | Oui = FAIL |
| Theme-aware | Couleurs via `useTheme`, pas hardcodees | Hardcode = FAIL |
| Responsive | `Grid size={{ xs, md, lg }}` (MUI v7) | Absent = FAIL |
| States | Loading/Error/Empty states presents | Manquant = FAIL |
| Accessibilite | aria-label, tooltips, contraste | Absent = FAIL |

## Checks recette LIA-SEC (C.2 -- si applicable)

| Check | Commande | Quand |
|-------|----------|-------|
| Recipe | `./validate_rules_recipe.sh {rule_dir}` | 41 checks |
| Ultimate | `./validate_rules_ultimate.sh {rule_dir}` | 91 checks |
| ReportRule | `./validate_reportrules.sh {rule_dir}/R-*.json` | 8 checks |

## Formule de scoring (C.3)

```
Pour chaque domaine :
  score_domaine = agent_score * (1 - penalite_secu - penalite_tests)
  score_pondere = score_domaine * weight / 100

score_global = SUM(score_pondere)

SI cycle > 1 :
  CHARGER cycle_{N-1}/C_SCORECARD.json
  CALCULER delta par domaine
  DETECTER regressions (score baisse > 5 points)
  CALCULER tendance (improving / stable / declining)
```
