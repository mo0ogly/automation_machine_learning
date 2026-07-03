# Règle — Environnement de dev (machine_learning)

## PROCESS MANAGEMENT — `mlauto` UNIQUEMENT (RÈGLE ABSOLUE)

**L'app tourne sous Docker. Tout cycle de vie des services passe par `mlauto` — JAMAIS de `docker` / `uvicorn` / `npm` bruts, JAMAIS tuer le process sur 8000.**

| Besoin | Commande (Linux/Git Bash) | Windows PowerShell |
|--------|---------------------------|--------------------|
| Démarrer (build si besoin) | `./mlauto.sh up` | `.\mlauto.ps1 up` |
| Redémarrer (code seul) | `./mlauto.sh restart` | `.\mlauto.ps1 restart` |
| Rebuild (requirements/package.json/Dockerfile changés) | `./mlauto.sh rebuild` | `.\mlauto.ps1 rebuild` |
| Logs / état / santé | `./mlauto.sh logs [svc]` · `status` · `health` | idem `.ps1` |
| Tests backend en conteneur | `./mlauto.sh test` | `.\mlauto.ps1 test` |
| Arrêt | `./mlauto.sh down` | `.\mlauto.ps1 down` |

- `mlauto.sh` et `mlauto.ps1` sont **en parité** (mêmes verbes) — utiliser celui de la plateforme.
- Interdits : `docker compose up/restart` en direct, `uvicorn app:app`, `npm run dev`, `kill`/`Stop-Process` sur le serveur. Détails + incident fondateur : section « RUNTIME = DOCKER » plus bas.

## PORTS FIXES — RÈGLE ABSOLUE

**JAMAIS changer les numéros de port du frontend ni du backend.**

| Service | Port | Commande |
|---------|------|----------|
| Frontend (Vite + React) | **5173** | `cd frontend && npm run dev` |
| Backend (FastAPI/uvicorn) | **8000** | `uvicorn app:app --port 8000` (depuis `backend/`) |

- Le frontend parle au backend en dur sur `http://localhost:8000` (`API_URL` dans `App.jsx` / `Dashboard.jsx`). Changer le port du backend casse tous les appels du front.
- L'utilisateur lance lui-même son frontend sur **5173** et son backend sur **8000**. Ces serveurs sont les serveurs de référence.

## NE PAS LANCER DE SERVEURS EN DOUBLE

**Why:** `preview_start` avec `autoPort: true` voyait 5173/8000 occupés (par les serveurs de l'utilisateur) et spawnait des doublons sur des ports aléatoires (50950, 51961, …) → confusion, instances mortes, et l'utilisateur croit que « ça ne marche pas » alors qu'il regarde un autre serveur. Incident répété le 2026-06-27.

**How to apply:**
1. Si un serveur tourne déjà sur 5173 (front) ou 8000 (back) → **c'est celui de l'utilisateur, le réutiliser**. NE PAS en démarrer un autre.
2. `autoPort` DOIT rester à `false` dans `.claude/launch.json` (front ET back). Si le port est occupé, échouer franchement plutôt que sauter sur un port aléatoire.
3. Pour inspecter l'app : se connecter au 5173 existant. Si l'aperçu ne peut pas, le dire — ne PAS contourner en spawnant un nouveau port.
4. Pour redémarrer le backend après un changement de code Python (pas de `--reload`), arrêter le process sur 8000 et le relancer **sur 8000**, jamais ailleurs.
5. Ne jamais demander à l'utilisateur de « regarder sur le port X » autre que 5173/8000.

## RUNTIME = DOCKER (méthode d'install documentée) — NE JAMAIS TUER / SQUATTER LE SERVEUR

**Why (incident 2026-07-03) :** l'app tourne via **Docker** — c'est l'Option A « recommandée » du README (`mlauto.sh up` / `mlauto.ps1 up`, stack backend+frontend en conteneurs). Le local `uvicorn` (Option B) n'est qu'un fallback sans Docker. Un agent a vu un process `.venv\python.exe -m uvicorn app:app` sur 8000, a conclu à tort « pas de Docker », a **tué ce process et lancé son propre uvicorn local sur 8000** → le port 8000 s'est retrouvé squatté, empêchant le conteneur Docker de s'y binder. L'utilisateur : « on était sous docker et tu as bousillé le truc ». C'est une dérive grave : action infra destructive non demandée + conclusion contredisant l'install documentée.

**How to apply :**
1. **La méthode d'exécution de référence est Docker** (`./mlauto.sh up` / `.\mlauto.ps1 up`). Avant toute hypothèse sur le runtime, **lire la doc d'install (README « Option A — Docker »)**. Ne PAS déduire le runtime d'un seul `docker ps` en échec (le CLI peut viser le mauvais context / Docker Desktop peut redémarrer).
2. **NE JAMAIS tuer le process qui écoute sur 8000, ni lancer un `uvicorn` local à sa place.** Ça squatte le port et casse le conteneur.
3. Cycle de vie des services **uniquement via `mlauto`** (cf. CLAUDE.md « Process Management ») :
   - changement de code seul → `./mlauto.sh restart`
   - changement de `requirements.txt` / `package.json` / Dockerfile → `./mlauto.sh rebuild` (ou `up`, qui rebuild si besoin)
   - jamais de `docker`/`uvicorn`/`npm` bruts pour (re)démarrer.
4. **Dépendances Python** : les ajouter à `backend/requirements.txt` (le `Dockerfile` fait `pip install -r`), PAS via `pip install` dans un `.venv` hôte — le conteneur ne le verrait pas. Après ajout → `./mlauto.sh rebuild`.
5. Si le port 8000 est occupé, c'est le conteneur de l'utilisateur : le **réutiliser**, jamais le remplacer.
