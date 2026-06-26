# Regles Red Team Forge — AEGIS

## Application AEGIS — Architecture

### Frontend (React 18 + Vite + Tailwind v4, port 5173)
- Command Center (Red Team Lab) : 15+ vues (catalog, scenarios, studio, playground, logs, timeline)
- HUD chirurgical : CameraHUD, VitalsMonitor, RobotArmsView
- Panneaux d'analyse : AnalysisPanel, CompareView, DeltaScore, EscalationPanel
- i18n trilingual FR/EN/BR (277 KB)

### Backend (FastAPI + Ollama + ChromaDB, port 8042)
- 36 chaines d'attaque dans `agents/attack_chains/`
- 102 templates dans `prompts/*.json` (97 numerotes + 5 config)
- Moteur genetique dans `agents/genetic_engine/`
- 11 routes API dans `routes/`
- RagSanitizer : 15 detecteurs + GMTP candidat 16e

### ChromaDB (backend/chroma_db/)
- aegis_corpus : ~4200 docs (fiches + templates + PDFs)
- aegis_bibliography : ~4700 docs (analyses + PDFs + metadonnees)
- Collections RAG par chaine (medical-rag, rag-basic, etc.)

## Moteur genetique — Regles

1. **Fitness** : SVC score 6 dimensions (Zhang et al. 2025, arXiv:2501.18632v2)
2. **Population** : 102 templates, gradient SVC 0.5/6 a 3.5/6
3. **Croisement** : templates compatibles par couche delta ciblee
4. **Mutation** : operateurs valides (autorite, cross-lingual, encoding, task injection)
5. **Operateurs INTERDITS** : XML fictif (regression prouvee #01→#16), negation directe (DAN mort), cliches Hollywood (0xROOT_HACK)
6. **Calibration** : #14 (SVC 1.0) = plancher, #18 (SVC 0.5) = sous-plancher absolu

## Campagnes — Regles

1. **N >= 30** par condition (validite statistique Sep(M), Zverev et al. 2025)
2. **Metriques obligatoires** : ASR, Sep(M), SVC (6 dim), P(detect), cosine drift
3. **Export** : fiche d'attaque .docx (11 sections + 2 annexes) via `/fiche-attaque`
4. **Resultats experimentaux tracables** : benchmark JSON avec N, ASR, p-value, IC 95%
5. **Pas de resultats simules** — ZERO placeholder, ZERO setTimeout dans le frontend

## Fiches d'attaque — Regles

1. **11 sections + 2 annexes** par fiche (voir `.claude/skills/fiche-attaque/references/document-sections.md`)
2. **3 agents** : SCIENTIST (Section 11, Sonnet) + MATH (3+5, Sonnet) + CYBER-LIBRARIAN (reste, Sonnet)
3. **TEXT-ONLY** : agents retournent du texte, PAS des fichiers
4. **SECTIONS EXCLUSIVES** : zero chevauchement (voir `references/agent-prompts.md`)
5. **PDFs dans le RAG** : SCIENTIST query `--multi-collection` (aegis_corpus + aegis_bibliography)
6. **Seed retour** : chaque fiche est seedee dans ChromaDB apres generation
7. **Index** : `fiche_index.json` mis a jour apres chaque fiche

## Adaptation au Modele — Protocoles Experimentaux

Les protocoles DOIVENT etre adaptes a la taille du modele cible :
- **3B** : max_tokens >= 500, fuzzing leger (1 transform max), temperature 0
- **7B** : max_tokens >= 300, fuzzing moyen (1-2 transforms), temperature 0.3
- **70B+** : parametres standard, fuzzing complet, temperature 0.7

## Multi-Provider LLM — Regle Absolue

**Tout agent AG2 (ConversableAgent) DOIT accepter `provider` et `model` en parametres.**

Regles :
1. **Propagation integrale** : si l'orchestrateur recoit `provider=groq`, TOUS les agents (RedTeam, Medical, SecurityAudit, AdaptiveAttacker, GroupChatManager) DOIVENT recevoir le meme provider. Jamais de fallback cache sur Ollama.
2. **Pas de modele hardcode specifique au provider** : `CYBER_MODEL = "saki007ster/CybersecurityRiskAnalyst:latest"` n'existe que sur Ollama. Quand `provider != "ollama"`, utiliser `MEDICAL_MODEL` en fallback.
3. **Signature obligatoire** : `def create_XXX_agent(provider: str = None, model: str = None) -> ConversableAgent`
4. **Verification** : avant lancement, `grep -c "groq.com.*200 OK"` vs `grep -c "11434"` dans les logs. Si mix provider detecte → BLOQUER.

### RETEX 2026-04-08 — THESIS-001 gele 3h

**Symptome** : THESIS-001 bloque a 115 appels Groq avec retry loop Ollama (500 errors).

**Cause** : `orchestrator.py` passait `provider=groq` uniquement au `medical_agent`. Les 3 autres agents (`red_team_agent`, `security_audit_agent`, `adaptive_attacker`) tombaient sur Ollama par defaut. Quand Ollama devenait instable, le GroupChat AG2 restait bloque en retry sur `security_audit_agent`.

**Fix** : propager `provider/model` a tous les `create_*_agent()` + fallback `CYBER_MODEL → MEDICAL_MODEL` quand provider cloud.

**Lecon** : AG2 multi-agent = multi-config LLM. Chaque `ConversableAgent` a sa propre `llm_config`. Les scripts directs (`call_llm()`) sont plus robustes car mono-provider par design.

## Boucle Iterative des Campagnes

Chaque campagne a un maximum de 3 iterations :
1. **Iteration 1** : parametres standards, N=30
2. **Iteration 2** : ajustes selon diagnostic (N augmente, parametres affines, modele change)
3. **Iteration 3** : dernier essai avant escalade humaine
- Verdict apres chaque iteration : SUPPORTED / REFUTED / INCONCLUSIVE
- Si INCONCLUSIVE apres 3 iterations → escalade au directeur de these
- Resultats dans `research_archive/experiments/EXPERIMENT_REPORT_*.md`
- Suivi dans `research_archive/experiments/campaign_manifest.json`

## Process

- Toujours via `aegis.ps1` / `aegis.sh` (JAMAIS de commandes directes)
- `/apex` pour implementation structuree (10 etapes)
- `/audit-pdca` pour audit qualite avec benchmark
- `/fiche-attaque` pour generation de fiches
- `/bibliography-maintainer incremental` pour recherche biblio
- `/research-director cycle` pour orchestration PDCA complete
