# automation_machine_learning — Descriptif exécutif

## En une phrase

Une plateforme qui construit un modèle de machine learning en **étapes explicites,
inspectables et rejouables**, où un **copilote LLM** *observe* les diagnostics chiffrés et
*oriente* par des recommandations ancrées dans les vrais nombres, pendant que **l'expert
décide et agit** — l'humain garde le contrôle (human-in-the-loop).

## Le problème adressé

Les outils d'AutoML masquent la construction du modèle derrière une boîte noire ; les
notebooks à la main sont rejouables mais sans garde-fou ni assistance. Cette application
marie les deux mondes :

- **la rigueur du ML classique** — modèles statistiques, métriques déterministes,
  reproductibilité ;
- **la fluidité des LLM** — raisonnement, recommandations contextuelles, explications en
  langage naturel.

## Boucle de travail — OODA par étape

Chaque étape du pipeline suit la même boucle **Observe → Orient → Decide → Act**.
Rejouer une étape **invalide automatiquement les étapes en aval** (cohérence garantie).

```mermaid
flowchart LR
    subgraph Pipeline["Pipeline en 8 étapes rejouables"]
        direction LR
        C[Clean] --> T[Transform] --> I[Integrate] --> S[Separate]
        S --> M[Model] --> Tu[Fine-tuning] --> E[Evaluate] --> X[Explainability]
    end

    subgraph Loop["Boucle par étape (OODA, human-in-the-loop)"]
        direction TB
        O1["Observe<br/>diagnostics déterministes"] --> O2["Orient<br/>recommandation LLM<br/>ancrée dans les nombres"]
        O2 --> O3["Decide<br/>l'expert règle la config"]
        O3 --> O4["Act<br/>exécute / rejoue"]
        O4 -. "rejeu → invalide l'aval" .-> O1
    end

    Pipeline -.chaque étape.-> Loop
```

## Les 3 paradigmes d'apprentissage couverts

```mermaid
flowchart TD
    APP["automation_machine_learning"]

    APP --> SUP["Supervisé"]
    APP --> UNS["Non supervisé"]
    APP --> RL["Renforcement"]

    SUP --> SUP1["Régression — RMSE / R²"]
    SUP --> SUP2["Classification binaire & multiclasse<br/>accuracy / précision / rappel / F1<br/>matrice de confusion"]

    UNS --> UNS1["Clustering<br/>KMeans / DBSCAN / Agglomerative<br/>silhouette, Davies-Bouldin, Calinski-Harabasz"]
    UNS --> UNS2["Détection d'anomalies<br/>Isolation Forest / LOF"]

    RL --> RL1["Q-learning tabulaire<br/>démo GridWorld"]
    RL --> RL2["Deep RL — Gymnasium + Stable-Baselines3<br/>13 algorithmes (PPO/DQN/SAC/...)<br/>environnements cyber-défense SOC/NOC"]
```

## Architecture technique

```mermaid
flowchart LR
    subgraph Front["Frontend — React 18 + Vite + Tailwind (:5173)"]
        UI["Dashboard par étapes<br/>+ vues Reinforcement / Exploiter / Monitoring"]
        COP["Copilote d'analyse<br/>journal mémoire ré-injecté"]
    end

    subgraph Back["Backend — FastAPI (:8000)"]
        API["API REST par étape<br/>/api/session/.../stage/..."]
        PIPE["Pipeline ML<br/>scikit-learn / XGBoost"]
        AGENT["Agent LLM<br/>multi-provider, OpenAI-compatible"]
        PERSIST["Persistance sessions<br/>SQLite (joblib blobs)"]
        REG["Registre agents Deep RL<br/>« Mes agents »"]
    end

    subgraph LLM["Providers LLM (OpenAI-compatible)"]
        P["Groq · OpenAI · Ollama<br/>LiteLLM / vLLM ..."]
    end

    UI -->|"fetch API_URL"| API
    COP --> API
    API --> PIPE
    API --> AGENT
    API --> PERSIST
    API --> REG
    AGENT -->|"POST /chat/completions"| P

    Docker["Docker Compose — mlauto.sh (up / rebuild / seed / seed-deeprl)"] -.orchestre.- Front
    Docker -.orchestre.- Back
```

- **Frontend** : React 18 + Vite + Tailwind, port **5173**. Le navigateur dérive l'URL
  backend depuis l'origine de la page (accès LAN sans rebuild).
- **Backend** : FastAPI + uvicorn, port **8000**. Pipeline scikit-learn / XGBoost, agent LLM
  multi-provider, persistance des sessions en SQLite (blobs `joblib`).
- **Runtime** : Docker Compose, cycle de vie via `mlauto.sh` (`up`, `rebuild`, `seed`,
  `seed-deeprl`, `test`, `clean`).

## Couche agentique (mode assisté)

- **Copilote d'analyse** (panneau latéral) : assistants contextuels + **journal mémoire** —
  chaque réponse IA est enregistrée et **ré-injectée dans les prompts suivants**.
- **Une IA par graphique** : chaque figure a sa légende et un bouton d'explication ; la
  réponse s'affiche en ligne sous le graphique.
- **Tables de décision** : l'expert coche les colonnes/features à garder (conseil IA + raison).
- **Gouvernance des prompts** : tout prompt LLM est éditable et repérable via le panneau
  « Prompts IA » (zéro prompt codé en dur).
- **Multi-provider** : tout provider OpenAI-compatible (Groq, OpenAI, Ollama, LiteLLM,
  vLLM…), clé et modèle configurables à l'exécution.

## Le modèle en action (au-delà de l'entraînement)

Une fois le modèle produit, la vue **Exploiter** le rend interrogeable pour **n'importe quel
modèle du pipeline** : prédiction unitaire, prédiction par lot (CSV), analyses de sensibilité
et diagramme tornado, point de fonctionnement (seuil), export d'un bundle auto-descriptif
(modèle + rapport de métriques). S'y ajoutent le suivi (**Monitoring**) et la fiche modèle.

## Modèles exemples prêts à l'emploi

- **Pipeline classique** : `mlauto.sh seed` rejoue le pipeline sur les 13 datasets démo →
  un modèle exemple entraîné par jeu de données, présent dès l'installation (idempotent).
- **Deep RL SOC/NOC** : `mlauto.sh seed-deeprl` entraîne et sauvegarde des agents exemples
  dans le registre « Mes agents » (idempotent, ~20 min ; commande séparée, non lancée par
  `up`/`rebuild`).

## Public visé

Expert data/ML qui veut la **traçabilité** d'un pipeline fait main **plus** l'assistance d'un
copilote — sans céder la décision à une boîte noire.
