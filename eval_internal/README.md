# eval_internal — jeux de questions internes (outils de développement)

**Ces questions sont synthétiques, générées par un LLM et NON validées médicalement.** Elles servent uniquement à mesurer la généralisation du système RAG-SFAR pendant le développement, sur des recommandations autres que l'antibioprophylaxie. Ce ne sont pas un benchmark de référence ni un livrable du projet : la création de benchmarks fiables est confiée aux experts médicaux du projet `benchmark-enrichi`. Dès que leurs jeux existent, ils s'importent avec `python -m rag_sfar.evaluation.datasets import ...` (voir `eval/README.md`) et font foi.

## Contenu

| Fichier | Rôle |
|---|---|
| `build_multirfe.py` | Construction du jeu `multirfe_synth` : échantillonnage des passages, génération, vérification, écriture |
| `datasets/multirfe_synth.jsonl` | Jeu normalisé (format commun, `provenance = llm_synthetic`) |
| `splits/multirfe_synth/{dev,test}.jsonl` | Découpage ; `test.jsonl` est scellé dans `eval/LOCKBOX.md` |
| `a_valider_medecins.csv` | 30 à 50 questions proposées à la relecture des médecins du datathon |
| `work/` | Traces : passages d'ancrage, sorties brutes des générateurs et vérificateurs, journal des rejets (`audit_trail.json`) |

## Méthode

1. **Échantillonnage** : 70 recommandations en vigueur, en français, hors antibioprophylaxie, stratifiées par période (tranches de 5 ans) et par domaine. Jusqu'à 3 passages par document : une recommandation cotée, une ligne de tableau, un autre passage. Plus les lignées qui ont au moins 2 éditions, pour les questions de comparaison.
2. **Génération** : une question par passage, ancrée sur un extrait verbatim (`gold_passages`), avec une réponse courte et des termes-clés. Elle a été faite par des sous-agents Claude Code (Claude Opus 5.5), qui ne voient ni le code du système ni le benchmark officiel. Quatre types de questions : recommandation, tableau ou posologie, cas clinique court, comparaison d'éditions. S'y ajoutent des questions hors corpus, pour mesurer l'abstention.
3. **Vérification indépendante** : des sous-agents distincts, qui n'ont pas généré les questions, jugent chaque question. Ils vérifient que la réponse est présente et non ambiguë dans la source, que la question se comprend seule, qu'elle n'est pas recopiée et qu'elle est cliniquement sensée. Pour les questions hors corpus, ils vérifient sur les 10 meilleurs passages BM25 que le corpus ne répond pas.
4. **Contrôles programmatiques** : l'extrait doit figurer dans le passage, et la question ne doit pas recopier 8 mots consécutifs ou plus de la source.
5. **Découpage** : le split dev/test tient à l'écart des **documents entiers** (« RFE jamais vues », tag `unseen_doc`), en plus d'une fraction des questions des autres documents.

## Limites connues

- Les questions et les références ont été produites et vérifiées par des LLM de la même famille que certains générateurs évalués. Il existe donc un risque d'auto-préférence, à surveiller dans les comparaisons avec les modèles Claude.
- La vérité terrain « passage » ne couvre que le passage d'ancrage. Un autre passage du corpus peut aussi contenir la réponse. La métrique passage est donc une borne basse ; la métrique document la complète.
- Les questions de comparaison d'éditions dépendent des lignées d'éditions calculées par le système (voir l'audit, I1). Elles sont peu nombreuses.

## `genprobe` — sonde de généralisation tenue à l'écart (agent E1, 2026-11-27)

**48 questions synthétiques, écrites et vérifiées par un LLM (Claude Opus 5.5, sous-agents Claude Code), NON validées par un médecin.** Ce n'est pas un benchmark : c'est une sonde interne qui exerce, sur d'autres RFE que l'antibioprophylaxie, les situations que les règles de retrieval n'ont pu être mesurées que sur l'antibioprophylaxie.

- **Tenue à l'écart de la mise au point** : à n'exécuter qu'une fois, sur les configurations gelées ; chaque exécution est consignée dans `JOURNAL.md`. Les auteurs n'ont lu ni le code de retrieval, ni les rapports de mise au point, ni les autres jeux de questions, et aucun modèle ni retrieval n'a été lancé sur ces questions.
- **Composition** : 4 familles de 12 questions (tags `fam:*`) — QCM à une seule option étayée (`fam:mcq`) ; ligne de tableau dont la réponse dépend d'une note, d'un champ ou d'un en-tête (`fam:table_note`) ; contraste de populations adulte / enfant / femme enceinte / sujet âgé / obèse (`fam:population`, dont 6 `population_unspecified` avec `meta.expected_behavior = conditional_or_clarification`) ; questions à deux sources éloignées (`fam:two_source`, tags `two_documents` / `two_sections`). 18 questions portent sur un tableau. 47 RFE en vigueur (50 `doc_id`), 2002 à 2026, aucune sur l'antibioprophylaxie.
- **Fichiers** : `datasets/genprobe.jsonl` ; `splits/genprobe/dev.jsonl` (jeu entier, pas de split test) ; `genprobe_a_valider_medecins.csv` (relecture médicale à faire) ; `build_genprobe_checks.py` (contrôles) ; `work/genprobe/` (rapport des contrôles, corrections de la seconde relecture).
- **Construction** : rédaction à partir des éditions en vigueur seulement (`index/tas_v3_errata`, `is_latest_edition = 1`), une famille par sous-agent ; références et citations verbatim (8 à 40 mots ; lignes de tableau en cellules séparées par « ‖ ») ; `evidence` / `evidence_sets` remplis pour toutes les questions (métrique `sufficiency`). Contrôles programmatiques : `.venv/bin/python eval_internal/build_genprobe_checks.py --mapping` (citations verbatim dans le Markdown source, éditions en vigueur, exclusion antibioprophylaxie, identifiants, clés QCM, comptes, couverture du mapping par `passage_match` sur les chunks). Seconde relecture indépendante par deux sous-agents qui n'avaient pas écrit les questions : 16 corrections (`work/genprobe/second_pass_corrections.json`).
- **Limites** : synthétique et non validé ; auto-préférence possible avec les générateurs Claude ; 48 questions, donc des IC larges (12 par famille) ; références fondées sur le texte du corpus, y compris de vieilles RFE encore « en vigueur » dans l'index ; détails dans `reports/agents/E1_genprobe.md`.

## `genprobe2` — seconde sonde tenue à l'écart (agent E2, 2026-11-27)

**60 questions synthétiques, écrites et relues par un LLM (Claude Opus 5.5, sous-agents Claude Code), NON validées par un médecin.** Outil interne, pas un benchmark. Il mesure trois faiblesses du retrieval : réponse qui exige deux passages éloignés, ligne propre à une population (enfant, nouveau-né, femme enceinte) face à la ligne adulte, ligne de tableau qui dépend d'une note ou d'un en-tête.

- **Tenu à l'écart, scellé** : écrit avant l'évaluation des nouveaux mécanismes de retrieval, par des auteurs qui n'ont lu ni le code de retrieval ni les rapports de mise au point. **À exécuter une seule fois, sur les configurations finales** ; chaque exécution est consignée dans `JOURNAL.md`. Exclu de `--suite full` (`HELD_OUT_SUITES`). Hash : `splits/genprobe2/SEALED.md`.
- **Composition** (tags `fam:*` + sous-type) : `fam:two_source` 20 (10 `two_documents`, 10 `two_sections`) ; `fam:population` 20 (8 `population_specific`, 6 `population_adult`, 6 `population_unspecified` avec `meta.expected_behavior = conditional_or_clarification`), dont 6 sur l'antibioprophylaxie (édition 2026 en vigueur) et 11 RFE ; `fam:table_note` 12 (5 `note_footnote`, 4 `note_scope`, 3 `note_header`) ; `fam:control` 8. 49 RFE en vigueur (titres distincts), 2002 à 2026. `evidence` / `evidence_sets` partout (métrique `sufficiency`) ; `meta.weak` signale 10 items dont la propriété visée est affaiblie.
- **Fichiers** : `datasets/genprobe2.jsonl` ; `splits/genprobe2/dev.jsonl` (jeu entier) ; `genprobe2_a_valider_medecins.csv` ; `build_genprobe2_checks.py` (contrôles, index `tas_v6`) ; `work/genprobe2/` (consigne des auteurs, rapport des contrôles, corrections de la seconde relecture).
- **Limites** : voir `reports/agents/E2_genprobe2.md`.
