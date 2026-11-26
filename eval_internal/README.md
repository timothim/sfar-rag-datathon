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
