# Errata de l'overlay ABP V3.1 (data/corpus_updates/)

Source des corrections : PDF officiel `RFE-antibioprophylaxie-2023_V3.1_pour-mise-sur-site-juillet-2026_sans-code-CCAM.pdf` (122 p., SHA-256 `642ad1f1c2ae3a050d1165eb41caab9e0f418deb2770538afb2dc0005ced9e03`), texte extrait avec pypdf. Erreurs signalées par la revue A2 (`reports/agents/A2_revue_neon_v31.md`, §2.4), héritées de la conversion Chandra de la V3.0. Accord de l'utilisateur transmis par l'orchestrateur le 2026-11-27.

| Date | Page PDF | Avant (overlay) | Après | Texte du PDF |
|---|---|---|---|---|
| 2026-11-27 | 81, chirurgie de la vésicule biliaire (adulte) | La puce « ○ Patients à faible risque : aucun des critères ci-dessus » est dans la même cellule que « Patients à haut risque », sur la ligne céfazoline 2 g / céfuroxime 1,5 g ; la cellule de force porte « ●●● (Avis d'experts) / ●●● (GRADE 2) » | Ligne haut risque : céfazoline / céfuroxime, « ●●● (Avis d'experts) » ; nouvelle ligne « ▪ Cholécystectomie élective par laparoscopie ○ Patients à faible risque : aucun des critères ci-dessus » → « PAS D'ANTIBIOPROPHYLAXIE », « ◉◉◎ (GRADE 2) » | « o Patients à faible risque : aucun des critères ci-dessus  PAS D'ANTIBIOPROPHYLAXIE ◉◉◎ (GRADE 2) » |
| 2026-11-27 | 87, encadré allergie, urologie (adulte) | « Si céfotaxime : gentamicine 6 à 7 mg/kg IVL + métronidazole 1g IVL » | « Si céfoxitine : gentamicine 6 à 7 mg/kg IVL + métronidazole 1g IVL » | « Si céfoxitine : gentamicine 6 à 7 mg/kg IVL + métronidazole 1g IVL » |
| 2026-11-27 | 113, chirurgie de la vésicule biliaire (pédiatrie) | La puce « faible risque » est sur la ligne céfazoline 30 mg/kg ; la ligne « PAS D'ANTIBIOPROPHYLAXIE » a une première cellule vide | Ligne haut risque : céfazoline 30 mg/kg ; ligne « ▪ Cholécystectomie élective par laparoscopie ○ Patients à faible risque : aucun des critères ci-dessus » → « PAS D'ANTIBIOPROPHYLAXIE », « ●●● (Avis d'experts) » | « o Patients à faible risque : aucun des critères ci-dessus  PAS D'ANTIBIOPROPHYLAXIE ◉◎◎ (Avis d'experts) » |

Rien d'autre n'est modifié. Script reproductible : `apply_errata.py` (remplacements exacts, chacun vérifié unique).
`updates_manifest.json` ne référence que le SHA-256 du PDF source (inchangé) : pas de mise à jour nécessaire. Le SHA-256 du Markdown corrigé est inscrit dans `manifest.json` de tout index reconstruit (`corpus_updates.files`).
