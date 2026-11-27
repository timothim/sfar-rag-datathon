## multirfe_synth dev (n=94)  before=20261127-012247_multirfe_synth_dev_b0fz_after.json  after=20261127-012801_multirfe_synth_dev_b0fz_nointro.json

### C9_simple_hybrid_rerank
| métrique | avant | après | diff [IC95] | P(après<=avant) |
|---|---:|---:|---:|---:|
| passage_hit@8 | 0.855 | 0.855 | +0.000 [+0.000, +0.000] | 1.00 |
| passage_mrr | 0.688 | 0.674 | -0.013 [-0.033, +0.000] | 1.00 |
| hit_ctx | 0.855 | 0.855 | +0.000 [+0.000, +0.000] | 1.00 |
| doc_hit | 0.974 | 0.974 | +0.000 [+0.000, +0.000] | 1.00 |
| obsolete_intrusion | 0.000 | 0.000 | +0.000 [+0.000, +0.000] | 1.00 |

Rang du passage (trouvés) : médiane 1 -> 1, moyenne 1.66 -> 1.69
Courbe passage hit@k : @1 0.592->0.566, @3 0.803->0.803, @5 0.829->0.829, @8 0.855->0.855, @12 0.855->0.855, @16 0.855->0.855, @20 0.855->0.855
Rang changé : 2 questions ; meilleur 0, pire 2
  pire : MR-g2c188878f4fca6996f4b:1->2, MR-g55e468b6df0cb295c14b:1->2
  meilleur : 

### C9_simple_hybrid_rerank-final_top_k=16+context_window=1+expand_table_parent=true
| métrique | avant | après | diff [IC95] | P(après<=avant) |
|---|---:|---:|---:|---:|
| passage_hit@8 | 0.882 | 0.868 | -0.013 [-0.039, +0.000] | 1.00 |
| passage_mrr | 0.670 | 0.648 | -0.021 [-0.053, +0.000] | 1.00 |
| hit_ctx | 1.000 | 1.000 | +0.000 [+0.000, +0.000] | 1.00 |
| doc_hit | 0.921 | 0.921 | +0.000 [+0.000, +0.000] | 1.00 |
| obsolete_intrusion | 0.000 | 0.000 | +0.000 [+0.000, +0.000] | 1.00 |

Rang du passage (trouvés) : médiane 1.0 -> 1.0, moyenne 4.08 -> 4.18
Courbe passage hit@k : @1 0.592->0.566, @3 0.711->0.684, @5 0.776->0.776, @8 0.882->0.868, @12 0.908->0.908, @16 0.934->0.934, @20 0.947->0.961
Rang changé : 6 questions ; meilleur 2, pire 4
  pire : MR-g2c188878f4fca6996f4b:1->4, MR-g0aba15fbdfface749f92:8->11, MR-g55e468b6df0cb295c14b:1->4, MR-ga95d75ad6fe8fb541a44:26->28
  meilleur : MR-gae3cda1acd4e903f01fd:20->19, MR-gb8871ff491d05e49db36:22->20
## abp171 dev (n=102)  before=20261127-012336_abp171_dev_b0fz_after.json  after=20261127-012850_abp171_dev_b0fz_nointro.json

### C9_simple_hybrid_rerank
| métrique | avant | après | diff [IC95] | P(après<=avant) |
|---|---:|---:|---:|---:|
| passage_hit@8 | 0.941 | 0.941 | +0.000 [+0.000, +0.000] | 1.00 |
| passage_mrr | 0.740 | 0.740 | +0.000 [+0.000, +0.000] | 1.00 |
| hit_ctx | 0.941 | 0.941 | +0.000 [+0.000, +0.000] | 1.00 |
| doc_hit | 1.000 | 1.000 | +0.000 [+0.000, +0.000] | 1.00 |
| obsolete_intrusion | 0.000 | 0.000 | +0.000 [+0.000, +0.000] | 1.00 |

Rang du passage (trouvés) : médiane 1.0 -> 1.0, moyenne 1.81 -> 1.81
Courbe passage hit@k : @1 0.637->0.637, @3 0.794->0.794, @5 0.902->0.902, @8 0.941->0.941, @12 0.941->0.941, @16 0.941->0.941, @20 0.941->0.941
Rang changé : 0 questions ; meilleur 0, pire 0
  pire : 
  meilleur : 

### C9_simple_hybrid_rerank-final_top_k=16+context_window=1+expand_table_parent=true
| métrique | avant | après | diff [IC95] | P(après<=avant) |
|---|---:|---:|---:|---:|
| passage_hit@8 | 0.912 | 0.912 | +0.000 [+0.000, +0.000] | 1.00 |
| passage_mrr | 0.714 | 0.714 | +0.000 [+0.000, +0.000] | 1.00 |
| hit_ctx | 0.990 | 0.990 | +0.000 [+0.000, +0.000] | 1.00 |
| doc_hit | 1.000 | 1.000 | +0.000 [+0.000, +0.000] | 1.00 |
| obsolete_intrusion | 0.000 | 0.000 | +0.000 [+0.000, +0.000] | 1.00 |

Rang du passage (trouvés) : médiane 1 -> 1, moyenne 2.74 -> 2.74
Courbe passage hit@k : @1 0.637->0.637, @3 0.735->0.735, @5 0.824->0.824, @8 0.912->0.912, @12 0.980->0.980, @16 0.990->0.990, @20 0.990->0.990
Rang changé : 0 questions ; meilleur 0, pire 0
  pire : 
  meilleur : 
## abpe171 dev (n=102)  before=20261127-012434_abpe171_dev_b0fz_after.json  after=20261127-012947_abpe171_dev_b0fz_nointro.json

### C9_simple_hybrid_rerank
| métrique | avant | après | diff [IC95] | P(après<=avant) |
|---|---:|---:|---:|---:|
| passage_hit@8 | 0.961 | 0.961 | +0.000 [+0.000, +0.000] | 1.00 |
| passage_mrr | 0.804 | 0.802 | -0.002 [-0.005, +0.000] | 1.00 |
| hit_ctx | 0.961 | 0.961 | +0.000 [+0.000, +0.000] | 1.00 |
| evidence_hit | 0.948 | 0.948 | +0.000 [+0.000, +0.000] | 1.00 |
| evidence_recall | 0.897 | 0.893 | -0.003 [-0.010, +0.000] | 1.00 |
| sufficiency | 0.833 | 0.833 | +0.000 [+0.000, +0.000] | 1.00 |
| doc_hit | 1.000 | 1.000 | +0.000 [+0.000, +0.000] | 1.00 |
| obsolete_intrusion | 0.000 | 0.000 | +0.000 [+0.000, +0.000] | 1.00 |

Rang du passage (trouvés) : médiane 1.0 -> 1.0, moyenne 1.51 -> 1.52
Courbe passage hit@k : @1 0.696->0.696, @3 0.892->0.892, @5 0.941->0.941, @8 0.961->0.961, @12 0.961->0.961, @16 0.961->0.961, @20 0.961->0.961
Courbe evidence_recall_curve : @1 0.581->0.581, @3 0.818->0.818, @5 0.883->0.883, @8 0.897->0.893, @12 0.897->0.893, @16 0.897->0.893, @20 0.897->0.893
Courbe sufficiency_curve : @1 0.469->0.469, @3 0.729->0.729, @5 0.812->0.812, @8 0.833->0.833, @12 0.833->0.833, @16 0.833->0.833, @20 0.833->0.833
Rang changé : 1 questions ; meilleur 0, pire 1
  pire : Q52:2->3
  meilleur : 

### C9_simple_hybrid_rerank-final_top_k=16+context_window=1+expand_table_parent=true
| métrique | avant | après | diff [IC95] | P(après<=avant) |
|---|---:|---:|---:|---:|
| passage_hit@8 | 0.941 | 0.941 | +0.000 [+0.000, +0.000] | 1.00 |
| passage_mrr | 0.770 | 0.770 | +0.000 [+0.000, +0.000] | 1.00 |
| hit_ctx | 0.980 | 0.980 | +0.000 [+0.000, +0.000] | 1.00 |
| evidence_hit | 0.958 | 0.958 | +0.000 [+0.000, +0.000] | 1.00 |
| evidence_recall | 0.928 | 0.928 | +0.000 [+0.000, +0.000] | 1.00 |
| sufficiency | 0.885 | 0.885 | +0.000 [+0.000, +0.000] | 1.00 |
| doc_hit | 1.000 | 1.000 | +0.000 [+0.000, +0.000] | 1.00 |
| obsolete_intrusion | 0.000 | 0.000 | +0.000 [+0.000, +0.000] | 1.00 |

Rang du passage (trouvés) : médiane 1.0 -> 1.0, moyenne 2.16 -> 2.16
Courbe passage hit@k : @1 0.696->0.696, @3 0.814->0.814, @5 0.902->0.902, @8 0.941->0.941, @12 0.971->0.971, @16 0.980->0.980, @20 0.980->0.980
Courbe evidence_recall_curve : @1 0.581->0.581, @3 0.704->0.704, @5 0.825->0.819, @8 0.877->0.877, @12 0.918->0.918, @16 0.923->0.923, @20 0.928->0.928
Courbe sufficiency_curve : @1 0.469->0.469, @3 0.594->0.594, @5 0.729->0.719, @8 0.812->0.812, @12 0.865->0.865, @16 0.875->0.875, @20 0.885->0.885
Rang changé : 0 questions ; meilleur 0, pire 0
  pire : 
  meilleur : 
