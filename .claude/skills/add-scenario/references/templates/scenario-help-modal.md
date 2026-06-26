# Template : ScenarioHelpModal.jsx Case Block
# Utilisé par : Frontend Dev (Phase 2a)
# Fichier cible : frontend/src/components/redteam/ScenarioHelpModal.jsx
# Ajouter dans l'objet HELP_DB (ou switch/case selon la structure courante)
# Anti-pattern CRITIQUE : PAS de template literals avec ${} — utiliser la concaténation (esbuild)

'{scenario_id}': {
  title: '{Nom lisible du scénario}',
  conjecture: 'C{1|2} — {claim thèse en une ligne}',
  severity: '{CRITICAL | HIGH | MEDIUM}',

  description: (
    '{Ce que ce scénario teste — 2-3 phrases. Inclure le vecteur d\'attaque ' +
    'et pourquoi c\'est cliniquement important. Référencer chain_id si RAG.}'
  ),

  formal: (
    'DY-AGENT: Integrity(S) := Reachable(M,i) ⊆ Allowed(i).\n' +
    'Attack: {comment Reachable(M,i) s\'étend au-delà de Allowed(i)}.\n' +
    'Conj. {N}: {delta_n} seul ne peut pas prévenir {attack_type} via {canal}.'
  ),

  mechanism: (
    'T-0 {setup}: {ce que l\'attaquant pré-positionne}.\n' +
    'T-1 {trigger}: {ce qui déclenche l\'attaque pendant l\'opération normale}.\n' +
    'T-2 {injection}: {comment le payload atteint le modèle}.\n' +
    'T-3 {effect}: {ce que le modèle fait de travers — faux positif/négatif/bypass}.'
  ),

  expected: (
    'Sep(M) < 0.{XX} sous {target_delta} seul (valide Conjecture {N}).\n' +
    '{Tout effet d\'amplification — ex: RAG retrieval booste l\'authority chain.}'
  ),

  defense: (
    '{delta_next}: {comment la prochaine couche défensive arrêterait cette attaque}.\n' +
    'AllowedOutputSpec: ajouter forbidden_directive "{directive}" pour corriger d4=0.\n' +
    'Sanitization ChromaDB: valider doc_type=adversarial avant retrieval.'
  ),

  svcBreakdown: (
    'SVC={actual_value} — d1={d1} d2={d2} d3={d3} d4={d4} d5={d5} d6={d6}\n\n' +
    'd1=1.0  Plausibilité clinique: {raison — ex: ICD-10 spécifique + terme anatomique}\n' +
    'd2=1.0  Authority chain: {raison — ex: FDA + ISO + credential clinicien}\n' +
    'd3={d3}  Deviation markers: {raison — 0.0 = gap _DEVIATION_MARKERS détecté}\n' +
    'd4={d4}  Actes interdits: {raison — 0.0 = AllowedOutputSpec sans directive}\n' +
    'd5={d5}  Réalisme format: {raison — HL7 ORU^R01 / FHIR / texte brut}\n' +
    'd6={d6}  Mapping MITRE: {raison — T-codes présents}\n\n' +
    'Pourquoi ça marche: {2-3 phrases — le paradoxe de la plausibilité, mécanisme ' +
    'bypass authority chain, et pourquoi le modèle ne peut pas distinguer DATA d\'INSTRUCTION}.'
  ),

  mitre: '{T1565.001, T1200, ...}',
},

---

# NOTES D'USAGE

## Règle template literal esbuild (CRITIQUE)

Ne JAMAIS utiliser de chaînes backtick avec ${} dans les fichiers JSX. esbuild crashe silencieusement.

```js
// MAUVAIS — esbuild crashe
svcBreakdown: `SVC=${svc} — d1=${d1}`,

// BON — concaténation de chaînes
svcBreakdown: 'SVC=' + svc + ' — d1=' + d1,

// BON — multi-lignes tout-littéral
svcBreakdown: (
  'SVC=0.55 — d1=1.0 d2=1.0 d3=0.0\n' +
  'Pourquoi: ...'
),
```

## Champ svcBreakdown

Ce champ alimente la section "SVC Analysis — Why This Works" rendue par :
```jsx
{help.svcBreakdown && (
  <section className="bg-blue-900/10 border border-blue-500/20 rounded-lg p-4">
    <h3>SVC Analysis — Why This Works</h3>
    <pre>{help.svcBreakdown}</pre>
  </section>
)}
```
Utiliser les valeurs SVC réelles calculées par `compute_svc()`, pas les valeurs prédites.

## Gate Vite build

Après ajout de l'entrée :
```bash
cd frontend && npx vite build 2>&1 | tail -5
```
Doit terminer par "built in Xs" — zéro erreur.
