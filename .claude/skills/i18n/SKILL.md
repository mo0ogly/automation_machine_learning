---
name: i18n
description: >
  Internationalise l'app machine_learning (frontend React 19 + Vite, port 5173) qui a
  aujourd'hui tout le francais code en dur (aucune librairie i18n). Pose la couche
  react-i18next, extrait les chaines FR (texte JSX, placeholder/title/aria-label,
  messages) vers des fichiers de traduction namespaces par composant, produit la
  traduction anglaise, ajoute un selecteur de langue, et verifie qu'il ne reste aucune
  chaine FR en dur. Se declenche sur : "traduis l'app", "fr en anglais", "i18n",
  "internationalisation", "ajoute l'anglais", "language switcher", "extrait les strings".
---

# i18n — FR -> EN pour l'app machine_learning

## Contexte reel de CETTE app (ne pas confondre avec poc_medical)

- Frontend : **React 19 + Vite**, `frontend/src/` (36 fichiers `.jsx`), port **5173**.
- Backend : FastAPI port **8000** (les messages d'erreur/labels renvoyes par l'API
  peuvent aussi etre en FR — les traiter cote frontend au rendu, pas cote backend,
  sauf demande explicite).
- **Aucune** librairie i18n installee. Le francais est **code en dur** : noeuds texte
  JSX, attributs `placeholder` / `title` / `aria-label`, et chaines dans le JS.
- C'est l'inverse de poc_medical (qui a deja react-i18next FR/EN/BR). Ici on part de zero.

## Contraintes projet a respecter

- **Ports fixes** : ne jamais lancer de serveur en double. Reutiliser 5173/8000 si occupes.
- **Template literal bug** (regle projet) : **pas de `${}` dans les fonctions standalone `.jsx`**.
  Pour l'interpolation, utiliser l'interpolation de i18next (`t('cle', { n })` + `"{{n}}"`
  dans le JSON), **jamais** un template literal JS dans le composant.
- **Zero placeholder / zero emoticon** dans le code.
- **Fichiers <= 800 lignes** : les JSON de locale par namespace restent petits ; ne pas
  creer un seul `translation.json` geant.
- Toute nouvelle dependance doit etre signalee au user. `react-i18next` est le standard
  (et deja utilise dans le projet frere) — le proposer, mais confirmer avant `npm install`.

## Decision : approche

Par defaut, **react-i18next** (standard, `Trans` pour le JSX riche, interpolation,
detection de langue). Si le user refuse toute dependance, repli sur un contexte React
maison minimal (meme structure de fichiers de locale, `t()` maison). Demander une seule
fois, puis avancer.

## Workflow (autonome, composant par composant)

### 1. Inventaire des chaines FR
Lancer le scanner pour cartographier ce qui reste a traduire :
```bash
node .claude/skills/i18n/scripts/scan_fr.mjs frontend/src
```
Il liste, par fichier, les chaines suspectes FR (texte JSX + attributs) avec la ligne.
C'est la **liste de travail** et l'oracle de fin (0 resultat = termine).

### 2. Infrastructure (une seule fois)
1. `cd frontend && npm install react-i18next i18next i18next-browser-languagedetector`
   (confirmer avec le user avant).
2. Creer `frontend/src/i18n/index.js` :
   - init i18next avec `resources` charges depuis `locales/{lng}/{ns}.json`,
   - `fallbackLng: 'fr'` (le FR est la source de verite existante),
   - `supportedLngs: ['fr', 'en']`,
   - `detection` : `localStorage` puis `navigator`, cle `ml.lang`,
   - `interpolation.escapeValue: false` (React echappe deja).
3. Importer `./i18n` en tete de `frontend/src/main.jsx`.
4. Structure des locales :
   ```
   frontend/src/i18n/locales/
     fr/common.json         # boutons, statuts, labels transverses
     fr/dashboard.json      # un namespace par grande vue/composant
     fr/monitoring.json
     en/common.json
     en/monitoring.json
     ...
   ```
   Un namespace = un composant ou une vue coherente. Cle = `camelCase` descriptif
   (`monitoring.jitter.title`), pas le texte FR comme cle.

### 3. Selecteur de langue
Ajouter un petit switch FR/EN dans la barre de navigation (`App.jsx` / `ConfigMenu.jsx`) :
`i18n.changeLanguage('en')`. Persiste via le languagedetector (localStorage `ml.lang`).
Texte du switch lui-meme via `t('common.language')`.

### 4. Migration d'un composant (repeter)
Pour chaque composant de la liste du scanner, dans l'ordre (commencer par `common`
puis les grosses vues : `Dashboard`, `MonitoringPanel`, `ExploitView`, `ReinforcementView`) :

1. `import { useTranslation } from 'react-i18next'` + `const { t } = useTranslation('monitoring')`.
2. Remplacer chaque chaine FR :
   - **Texte JSX** : `<h6>Stabilite sous perturbation</h6>` -> `<h6>{t('jitter.title')}</h6>`.
   - **Attribut** : `title="Reglages"` -> `title={t('settings.tooltip')}`.
   - **JSX riche** (texte + `<strong>`, liens) : utiliser `<Trans i18nKey="..." />`
     avec les balises, plutot que de casser la phrase en morceaux.
   - **Interpolation** : `PSI = {pd.psi}` -> `t('drift.psi', { psi: pd.psi })` avec
     `"PSI des predictions = {{psi}}"` dans le JSON. **Jamais** de `${}` en `.jsx`.
   - **Pluriel / conditionnel** : utiliser les regles de pluriel i18next (`_one`/`_other`).
3. Ajouter la cle dans `fr/<ns>.json` (valeur = le FR original **verbatim**, accents inclus)
   ET dans `en/<ns>.json` (traduction EN).
4. Ne PAS traduire : identifiants techniques, cles JSON d'API, noms de modeles, unites.

### 5. Qualite de la traduction EN
- Terminologie ML/cyber coherente : garder les termes techniques anglais deja standards
  (drift, jitter, baseline, threshold, ROC, recall). Traduire seulement la prose FR.
- Ton : concis, orientation analyste SOC/threat-intel (cf. positionnement produit).
- Verifier que les accents FR restent corrects dans `fr/*.json` (aucun ASCII degrade :
  jamais "modele" pour "modele" -> garder "modèle").
- Pas d'over-traduction : un label deja anglais (`AUC`, `F1`) reste tel quel dans les deux.

### 6. Verification (obligatoire avant de conclure)
1. Re-lancer `node .claude/skills/i18n/scripts/scan_fr.mjs frontend/src` -> **0 chaine FR
   en dur restante** (hors JSON de locale `fr/`, hors commentaires code, hors cles techniques).
2. Verifier la parite des cles FR/EN :
   ```bash
   node .claude/skills/i18n/scripts/check_parity.mjs frontend/src/i18n/locales
   ```
   -> aucune cle presente dans un `fr/*.json` absente du `en/*.json` correspondant, et vice-versa.
3. `cd frontend && npm run build` doit passer.
4. Test manuel sur le 5173 existant : basculer FR<->EN, verifier qu'aucun texte ne
   disparait ni n'affiche la cle brute (`monitoring.jitter.title` visible = cle manquante).
5. Lancer `npm run test` (vitest) si des tests referencent des libelles FR : les mettre
   a jour pour interroger via role/testid plutot que le texte traduit.

## Ordre recommande des composants (par volume de texte)
1. `common` (boutons, statuts, erreurs partages)
2. `Dashboard.jsx`, `StagePanel.jsx`, `StageStepper.jsx`
3. `MonitoringPanel.jsx`, `StabilityPanel.jsx`, `DiagnosticsView.jsx`
4. `ExploitView.jsx` + `components/exploit/*`
5. `ReinforcementView.jsx`
6. `Copilot.jsx`, `ChatDock.jsx`, `AssistAnswer.jsx`, panneaux AI backends
7. Le reste (modals, menus, bannieres).

Ne PAS tout faire d'un bloc : migrer un composant, verifier build, passer au suivant.
Commiter par lot coherent (ex. "i18n(monitoring): extraction FR + traduction EN").

## Definition of Done
- Infra react-i18next en place + selecteur FR/EN fonctionnel et persistant.
- `scan_fr.mjs` retourne 0 hors locales `fr/`.
- Parite FR/EN complete (`check_parity.mjs` OK).
- `npm run build` et `npm run test` verts.
- Bascule FR/EN testee a l'ecran sur le 5173, aucun texte manquant ni cle brute affichee.
