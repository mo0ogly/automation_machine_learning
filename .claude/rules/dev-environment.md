# Règle — Environnement de dev (machine_learning)

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
