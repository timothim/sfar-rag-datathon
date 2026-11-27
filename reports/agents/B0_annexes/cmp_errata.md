## multirfe_synth dev (n=94)  before=20261127-012247_multirfe_synth_dev_b0fz_after.json  after=20261127-012527_multirfe_synth_dev_b0fz_errata.json

### C9_simple_hybrid_rerank
| métrique | avant | après | diff [IC95] | P(après<=avant) |
|---|---:|---:|---:|---:|
| passage_hit@8 | 0.855 | 0.855 | +0.000 [+0.000, +0.000] | 1.00 |
| passage_mrr | 0.688 | 0.688 | +0.000 [+0.000, +0.000] | 1.00 |
| hit_ctx | 0.855 | 0.855 | +0.000 [+0.000, +0.000] | 1.00 |
| doc_hit | 0.974 | 0.974 | +0.000 [+0.000, +0.000] | 1.00 |
| obsolete_intrusion | 0.000 | 0.000 | +0.000 [+0.000, +0.000] | 1.00 |

Rang du passage (trouvés) : médiane 1 -> 1, moyenne 1.66 -> 1.66
Courbe passage hit@k : @1 0.592->0.592, @3 0.803->0.803, @5 0.829->0.829, @8 0.855->0.855, @12 0.855->0.855, @16 0.855->0.855, @20 0.855->0.855
Rang changé : 0 questions ; meilleur 0, pire 0
  pire : 
  meilleur : 

### C9_simple_hybrid_rerank-final_top_k=16+context_window=1+expand_table_parent=true
| métrique | avant | après | diff [IC95] | P(après<=avant) |
|---|---:|---:|---:|---:|
| passage_hit@8 | 0.882 | 0.882 | +0.000 [+0.000, +0.000] | 1.00 |
| passage_mrr | 0.670 | 0.670 | +0.000 [+0.000, +0.000] | 1.00 |
| hit_ctx | 1.000 | 1.000 | +0.000 [+0.000, +0.000] | 1.00 |
| doc_hit | 0.921 | 0.921 | +0.000 [+0.000, +0.000] | 1.00 |
| obsolete_intrusion | 0.000 | 0.000 | +0.000 [+0.000, +0.000] | 1.00 |

Rang du passage (trouvés) : médiane 1.0 -> 1.0, moyenne 4.08 -> 4.08
Courbe passage hit@k : @1 0.592->0.592, @3 0.711->0.711, @5 0.776->0.776, @8 0.882->0.882, @12 0.908->0.908, @16 0.934->0.934, @20 0.947->0.947
Rang changé : 0 questions ; meilleur 0, pire 0
  pire : 
  meilleur : 
## abp171 dev (n=102)  before=20261127-012336_abp171_dev_b0fz_after.json  after=20261127-012617_abp171_dev_b0fz_errata.json

### C9_simple_hybrid_rerank
| métrique | avant | après | diff [IC95] | P(après<=avant) |
|---|---:|---:|---:|---:|
| passage_hit@8 | 0.941 | 0.941 | +0.000 [+0.000, +0.000] | 1.00 |
| passage_mrr | 0.740 | 0.735 | -0.005 [-0.015, +0.000] | 1.00 |
| hit_ctx | 0.941 | 0.941 | +0.000 [+0.000, +0.000] | 1.00 |
| doc_hit | 1.000 | 1.000 | +0.000 [+0.000, +0.000] | 1.00 |
| obsolete_intrusion | 0.000 | 0.000 | +0.000 [+0.000, +0.000] | 1.00 |

Rang du passage (trouvés) : médiane 1.0 -> 1.0, moyenne 1.81 -> 1.82
Courbe passage hit@k : @1 0.637->0.627, @3 0.794->0.794, @5 0.902->0.902, @8 0.941->0.941, @12 0.941->0.941, @16 0.941->0.941, @20 0.941->0.941
Rang changé : 1 questions ; meilleur 0, pire 1
  pire : Q159:1->2
  meilleur : 

### C9_simple_hybrid_rerank-final_top_k=16+context_window=1+expand_table_parent=true
| métrique | avant | après | diff [IC95] | P(après<=avant) |
|---|---:|---:|---:|---:|
| passage_hit@8 | 0.912 | 0.912 | +0.000 [+0.000, +0.000] | 1.00 |
| passage_mrr | 0.714 | 0.709 | -0.005 [-0.015, +0.000] | 1.00 |
| hit_ctx | 0.990 | 0.990 | +0.000 [+0.000, +0.000] | 1.00 |
| doc_hit | 1.000 | 1.000 | +0.000 [+0.000, +0.000] | 1.00 |
| obsolete_intrusion | 0.000 | 0.000 | +0.000 [+0.000, +0.000] | 1.00 |

Rang du passage (trouvés) : médiane 1 -> 1, moyenne 2.74 -> 2.75
Courbe passage hit@k : @1 0.637->0.627, @3 0.735->0.735, @5 0.824->0.824, @8 0.912->0.912, @12 0.980->0.980, @16 0.990->0.990, @20 0.990->0.990
Rang changé : 1 questions ; meilleur 0, pire 1
  pire : Q159:1->2
  meilleur : 
## abpe171 dev (n=102)  before=20261127-012434_abpe171_dev_b0fz_after.json  after=20261127-012714_abpe171_dev_b0fz_errata.json

### C9_simple_hybrid_rerank
| métrique | avant | après | diff [IC95] | P(après<=avant) |
|---|---:|---:|---:|---:|
| passage_hit@8 | 0.961 | 0.961 | +0.000 [+0.000, +0.000] | 1.00 |
| passage_mrr | 0.804 | 0.804 | +0.000 [+0.000, +0.000] | 1.00 |
| hit_ctx | 0.961 | 0.961 | +0.000 [+0.000, +0.000] | 1.00 |
| evidence_hit | 0.948 | 0.948 | +0.000 [+0.000, +0.000] | 1.00 |
| evidence_recall | 0.897 | 0.897 | +0.000 [+0.000, +0.000] | 1.00 |
| sufficiency | 0.833 | 0.833 | +0.000 [+0.000, +0.000] | 1.00 |
| doc_hit | 1.000 | 1.000 | +0.000 [+0.000, +0.000] | 1.00 |
| obsolete_intrusion | 0.000 | 0.000 | +0.000 [+0.000, +0.000] | 1.00 |

Rang du passage (trouvés) : médiane 1.0 -> 1.0, moyenne 1.51 -> 1.51
Courbe passage hit@k : @1 0.696->0.696, @3 0.892->0.892, @5 0.941->0.941, @8 0.961->0.961, @12 0.961->0.961, @16 0.961->0.961, @20 0.961->0.961
Courbe evidence_recall_curve : @1 0.581->0.581, @3 0.818->0.818, @5 0.883->0.883, @8 0.897->0.897, @12 0.897->0.897, @16 0.897->0.897, @20 0.897->0.897
Courbe sufficiency_curve : @1 0.469->0.469, @3 0.729->0.729, @5 0.812->0.812, @8 0.833->0.833, @12 0.833->0.833, @16 0.833->0.833, @20 0.833->0.833
Rang changé : 0 questions ; meilleur 0, pire 0
  pire : 
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
Courbe evidence_recall_curve : @1 0.581->0.581, @3 0.704->0.704, @5 0.825->0.825, @8 0.877->0.877, @12 0.918->0.918, @16 0.923->0.923, @20 0.928->0.928
Courbe sufficiency_curve : @1 0.469->0.469, @3 0.594->0.594, @5 0.729->0.729, @8 0.812->0.812, @12 0.865->0.865, @16 0.875->0.875, @20 0.885->0.885
Rang changé : 0 questions ; meilleur 0, pire 0
  pire : 
  meilleur : 
