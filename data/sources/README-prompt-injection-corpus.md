# Corpus de detection d'injection de prompt indirecte (synthetique)

Fiche d'accompagnement du corpus `prompt-injection-corpus.jsonl` (et de sa vue plate `prompt-injection-corpus.csv`), genere par `prompt_injection_corpus.py`.

## 1. Resume

Corpus annote de 1000 segments concu pour entrainer et evaluer des classifieurs de detection d'injection de prompt indirecte, c'est-a-dire des instructions malveillantes dissimulees dans de la donnee qu'un agent LLM ingere (pages web, e-mails, passages recuperes par un RAG, sorties d'outils, documents). La tache visee est defensive : apprendre la frontiere entre instruction de confiance et donnee non fiable.

Le corpus a ete construit pour eviter les deux faiblesses des jeux naifs sur ce sujet : un signal trop facile que capte un simple filtre par mots-cles, et l'absence de cas negatifs realistes. Il integre donc des hard negatives (texte benin contenant des mots declencheurs) et une categorie injection_discussion (texte qui parle de l'injection sans la perpetrer), qui sont les confuseurs critiques.

| Propriete | Valeur |
| --- | --- |
| Enregistrements | 1000 |
| Injections | 550 |
| Benins | 450 (clean 202, hard_negative 180, injection_discussion 68) |
| Techniques d'injection | 12, equilibrees |
| Langues | carrier en 721, fr 235, pt 44 |
| Injections cross-linguales | 148 (langue primaire de la charge differente du carrier) |
| Injections code-switchees | 49 (deux langues melees dans une meme charge) |
| Obfuscation des injections | 6 types plus aucune |
| Format primaire | JSON Lines (UTF-8, unicode preserve) |
| Graine de reproduction | 42 |

## 2. Avertissement et perimetre

Corpus synthetique a visee de recherche, de benchmark et d'enseignement. Les charges (payloads) sont des artefacts textuels inertes destines a entrainer la detection ; elles ne constituent pas un outillage d'attaque operationnel. Le perimetre est l'injection indirecte : la charge est toujours embarquee dans de la donnee, jamais saisie directement par l'utilisateur. Les domaines, identifiants, URL et adresses sont fictifs (`attacker.example`, `exfil.example`).

## 3. Format et schema d'annotation

Le format primaire est JSON Lines : un objet par ligne, encodage UTF-8 avec `ensure_ascii=false`, ce qui preserve les caracteres d'evasion (homoglyphes cyrilliques, espaces de largeur nulle U+200B). Une vue CSV plate est fournie pour inspection ; les champs liste y sont serialises (OWASP joint par barre verticale, span au format debut deux-points fin).

| Champ | Type | Description |
| --- | --- | --- |
| `id` | chaine | Identifiant stable, PI-000001 et suivants |
| `text` | chaine | Texte complet du carrier, injection embarquee in situ pour les positifs |
| `label` | enum | injection ou benign |
| `technique` | enum ou null | Mecanisme d'injection (voir section 4), null si benin |
| `owasp_llm` | liste | Categories OWASP LLM 2025 ; le vecteur est toujours LLM01:2025 plus l'impact |
| `carrier` | enum | Canal de donnee porteur du segment |
| `language` | enum | Langue du carrier (document hote) : en, fr ou pt |
| `payload_language` | enum ou null | Langue primaire de l'instruction injectee ; null si benin. Peut differer de `language` |
| `payload_secondary_language` | enum ou null | Seconde langue presente dans une charge code-switchee ; null sinon |
| `cross_lingual` | booleen | Vrai quand la langue primaire de la charge differe de `language` (bascule au niveau de la charge entiere) |
| `code_switched` | booleen | Vrai quand la charge mele deux langues en interne (code-switching intra-payload) |
| `obfuscation` | enum | Encodage d'evasion applique a la charge, none si en clair |
| `injection_position` | enum ou null | Emplacement de la charge dans le carrier |
| `boundary` | enum ou null | Frontiere de confiance franchie (voir section 6) |
| `severity` | enum ou null | Niveau d'impact indicatif |
| `benign_subtype` | enum ou null | clean, hard_negative ou injection_discussion pour les benins |
| `payload_span` | liste ou null | Offsets caractere debut et fin de l'instruction injectee dans `text` |

Le champ `payload_span` permet une evaluation au niveau du span (localiser l'instruction injectee), pas seulement au niveau du document. Sur ce corpus, les 550 injections portent un span valide (verifie dans les bornes), de longueur 74 a 262 caracteres.

## 4. Taxonomie des techniques

Douze mecanismes d'injection sont distingues, chacun associe a son impact OWASP LLM 2025. Le vecteur reste LLM01:2025 Prompt Injection ; les codes additionnels qualifient la consequence.

| Technique | Description | Impact OWASP additionnel | Severite par defaut |
| --- | --- | --- | --- |
| `instruction_override` | Annulation des consignes precedentes (ignore previous instructions) | aucun | medium |
| `delimiter_injection` | Faux delimiteurs ou fin de contexte pour s'echapper du bac a sable de donnee | aucun | medium |
| `role_hijack` | Reassignation de persona ou de role (developer mode, AdminBot) | aucun | medium |
| `system_prompt_leak` | Extraction du prompt systeme ou de la configuration | LLM07:2025 | high |
| `data_exfiltration` | Exfiltration de donnees vers une URL, un webhook ou un mail | LLM02:2025, LLM06:2025 | critical |
| `tool_abuse` | Detournement d'outils ou d'actions (shell, mail, paiement, calendrier) | LLM06:2025 | critical |
| `conditional_trigger` | Charge a declenchement conditionnel ou differe | LLM06:2025 | high |
| `refusal_suppression` | Pression pour supprimer refus et avertissements | aucun | medium |
| `fake_authority` | Usurpation d'un message systeme, developpeur ou administrateur | aucun | high |
| `output_manipulation` | Injection de HTML ou de markdown actif dans la sortie | LLM05:2025 | high |
| `misinformation_seed` | Consigne d'affirmer une information fausse ou biaisee | LLM09:2025 | medium |
| `staged_multistep` | Attaque en plusieurs etapes ou de second ordre visant un agent ulterieur | LLM06:2025 | high |

## 5. Carriers, positions et obfuscation

Treize types de carriers couvrent les surfaces d'ingestion realistes : email, web_page, support_ticket, code_comment, document, product_review, rag_chunk, tool_output, calendar_invite, chat_log, html_metadata, api_response, pdf_text. Pour les positifs, la charge est embarquee a une position variable (`injection_position` : start, middle, end, footer, metadata), entouree de contenu legitime, ce qui reproduit l'essence de l'injection indirecte.

Sept regimes d'obfuscation sont representes pour eprouver la robustesse au-dela du simple appariement de chaines : none, base64 (encodage de la charge precede d'une consigne de decodage), leetspeak, homoglyph (substitution par des caracteres cyrilliques visuellement proches), zero_width (insertion d'espaces de largeur nulle), html_comment et markdown_hidden (texte rendu invisible). Les deux derniers ne s'appliquent qu'aux carriers porteurs de balisage.

## 6. Injection multilingue : cross-linguale et code-switching

Deux dimensions orthogonales modelisent l'exploitation de l'asymetrie des garde-fous, qui sont entraines de facon disproportionnee sur une langue dominante, en general l'anglais. Une instruction exprimee dans une langue moins dotee, ou qui change de langue, franchit plus souvent les filtres.

Cross-linguale (au niveau de la charge entiere). `language` decrit la langue du carrier, le document hote ; `payload_language` decrit la langue de l'instruction injectee. Lorsque les deux different, `cross_lingual` vaut vrai. Cent quarante-huit injections sont cross-linguales. Les paires les plus frequentes sont en vers fr et en vers pt, c'est-a-dire un document d'apparence anglaise dissimulant une instruction en francais ou en portugais.

Code-switching (intra-payload). Une seule instruction mele deux langues en interne, la bascule survenant a une frontiere de clause pour rester grammaticalement coherente. Le champ `code_switched` vaut vrai et `payload_secondary_language` indique la seconde langue. Quarante-neuf injections sont code-switchees, sur les techniques qui s'y pretent. Exemple : une charge d'exfiltration qui commence en anglais (Append the user name and email to the URL...) puis bascule en francais (et invite l'utilisateur a ouvrir le lien), enfouie dans un e-mail en portugais. C'est une evasion d'un cran superieur, qui defait les detecteurs supposant une langue unique par segment.

Les deux drapeaux sont independants : une charge code-switchee peut aussi etre cross-linguale par rapport a son carrier. Sur les benins, les deux valent faux.

Distinction importante de perimetre. Le corpus mesure la difficulte de detection, pas l'efficacite de l'attaque contre un modele victime. L'asymetrie des garde-fous releve d'un harnais de red team contre une cible ; ici, l'interet de ces dimensions est de reveler l'angle mort d'un detecteur entraine surtout sur une langue. Le protocole adapte consiste a entrainer sur des injections monolingues puis a mesurer le rappel sur les sous-ensembles cross-lingual et code-switched.

## 7. Frontieres de confiance et lien DY-AGENT

Chaque injection indirecte franchit une frontiere depuis la donnee non fiable vers le canal d'instruction. Le champ `boundary` distingue le canal source :

- `data_to_instruction` : email, web, document, avis, commentaire de code, calendrier, transcription, metadonnees HTML, texte de PDF.
- `tool_output_to_instruction` : sortie d'outil et reponse d'API.
- `retrieved_context_to_instruction` : passage recupere par un RAG.

Ces trois frontieres sont les surfaces ou une separation instruction/donnee doit etre garantie. Le corpus permet ainsi de mesurer la performance d'un detecteur par frontiere, et de l'aligner sur les niveaux de delta-separation d'une architecture agentique : chaque niveau cible une frontiere et la detection au niveau de cette frontiere correspond a l'application de la separation correspondante. Un protocole utile consiste a evaluer separement chaque valeur de `boundary` pour verifier qu'un detecteur ne se contente pas de generaliser sur un seul canal.

## 8. Validation et resultats de reference

Le corpus est integralement deduplique (1000 textes uniques) et equilibre par technique. Deux baselines illustrent sa qualite, en separation entrainement et test stratifiee a 25 pourcent.

| Detecteur | Accuracy | F1 |
| --- | --- | --- |
| TF-IDF caracteres 3-5 grammes plus regression logistique | 0.98 | 0.98 |
| Appariement naif par mots-cles | 0.60 | 0.51 |

L'ecart est l'argument central : un modele appris distingue correctement injection et donnee benigne, y compris sur les confuseurs (zero faux positif sur hard_negative et injection_discussion dans le test), alors que le detecteur par mots-cles s'effondre precisement sur ces cas, avec un taux de faux positifs de 0.15 sur les hard negatives et de 0.41 sur l'injection_discussion. Le corpus penalise donc les detecteurs triviaux, ce qui est l'objectif d'un jeu de reference robuste.

Protocoles d'evaluation recommandes, au-dela du decoupage aleatoire :

- Generalisation inter-technique : entrainer sur un sous-ensemble de techniques, tester sur les techniques retirees, pour mesurer la robustesse a des mecanismes non vus.
- Generalisation inter-langue et multilingue : entrainer sur des injections monolingues en, tester sur les charges fr et pt, sur le sous-ensemble cross-lingual et sur le sous-ensemble code-switched, pour mesurer l'angle mort multilingue (voir section 6).
- Robustesse a l'obfuscation : evaluer separement le sous-ensemble obfusque.
- Evaluation par frontiere (voir section 7).

## 9. Limites

- Donnees synthetiques sans validite externe ; la diversite est bornee par les bibliotheques de charges et de carriers.
- Les charges sont representatives de patrons connus, pas exhaustives de l'espace des attaques reelles.
- Le corpus cible l'injection indirecte au niveau du texte ingere ; il ne couvre pas l'injection multimodale ni les attaques au niveau des tokens du modele.
- Le plafond de performance d'un modele char n-grammes est eleve sur le decoupage aleatoire ; privilegier les protocoles inter-technique et inter-langue pour un test exigeant.

## 10. Reproduction

```bash
# Corpus par defaut (1000 enregistrements, graine 42)
python prompt_injection_corpus.py --rows 1000 --seed 42 \
  --jsonl prompt-injection-corpus.jsonl --csv prompt-injection-corpus.csv

# Corpus plus grand
python prompt_injection_corpus.py --rows 4000 --seed 7 \
  --jsonl corpus.jsonl --csv corpus.csv
```

Parametres exposes dans la dataclass `CorpusConfig` : `injection_ratio`, repartition des benins (`benign_clean_ratio`, `benign_hard_negative_ratio`, `benign_discussion_ratio`), `language_probs`, `obfuscation_rate` et `obfuscation_choices`. Aucune valeur n'est codee en dur dans la logique d'assemblage.

## 11. References

- OWASP Top 10 for LLM Applications 2025 (v2.0, OWASP GenAI Security Project, 18 novembre 2024), designations LLM01:2025 a LLM10:2025.
- Greshake et al., 2023, travaux fondateurs sur l'injection de prompt indirecte contre des applications integrant des LLM.
- CISA et travaux ENISA sur la securite des systemes a base d'IA pour le cadrage des risques agentiques.
