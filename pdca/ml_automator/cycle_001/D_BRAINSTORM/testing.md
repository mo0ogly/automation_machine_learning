## Score : 0/100

## Forces
- Architecture découplée Frontend (React/Vite) / Backend (FastAPI) très favorable à la mise en place de tests isolés.
- Présence d'un pipeline CI/CD GitHub Actions (`.github/workflows/deploy.yml`) ayant déjà des étapes prévues pour l'exécution des tests unitaires et E2E sur la partie Frontend.

## Faiblesses (GAPS)
- Absence totale de fichiers de tests et de code de couverture, que ce soit pour le Frontend ou le Backend.
- Les scripts exécutés par la CI (`npm run test` et `npm run test:e2e`) n'existent même pas dans le `frontend/package.json`.
- Faux-positifs dangereux en CI : le workflow GitHub Actions utilise `continue-on-error: true` pour les étapes de test, ignorant totalement les échecs et déployant quand même.
- L'infrastructure de test n'est pas installée (ni `pytest` côté backend, ni `vitest`/`playwright` côté frontend).
- Le backend (FastAPI) est totalement ignoré dans les validations de la CI.

## Quick Wins
- **Frontend** :
  - Ajouter les librairies de test : `npm install -D vitest @testing-library/react playwright`.
  - Ajouter les scripts correspondants dans `package.json` (`"test": "vitest run"`, `"test:e2e": "playwright test"`).
  - Écrire un premier test unitaire très simple validant le rendu de `App.jsx`.
  - Retirer tous les `continue-on-error: true` du fichier `deploy.yml` pour les jobs de tests afin de sécuriser les déploiements de la CI.
- **Backend** :
  - Ajouter les librairies de test : `pip install pytest httpx`.
  - Créer un dossier `backend/tests/` et y écrire un `test_api.py` qui teste la route `/health` de l'API.
  - Ajouter un nouveau Job "test-backend" dans `deploy.yml` pour valider les APIs en exécutant `pytest` avant de déployer.
