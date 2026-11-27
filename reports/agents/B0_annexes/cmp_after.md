## multirfe_synth dev (n=94)  before=20261127-011526_multirfe_synth_dev_b0fz_before.json  after=20261127-012247_multirfe_synth_dev_b0fz_after.json

### C9_simple_hybrid_rerank
| métrique | avant | après | diff [IC95] | P(après<=avant) |
|---|---:|---:|---:|---:|
| passage_hit@8 | 0.855 | 0.855 | +0.000 [+0.000, +0.000] | 1.00 |
| passage_mrr | 0.678 | 0.688 | +0.010 [+0.000, +0.030] | 0.38 |
| hit_ctx | 0.855 | 0.855 | +0.000 [+0.000, +0.000] | 1.00 |
| doc_hit | 0.974 | 0.974 | +0.000 [+0.000, +0.000] | 1.00 |
| obsolete_intrusion | 0.000 | 0.000 | +0.000 [+0.000, +0.000] | 1.00 |

Rang du passage (trouvés) : médiane 1 -> 1, moyenne 1.71 -> 1.66
Courbe passage hit@k : @1 0.579->0.592, @3 0.789->0.803, @5 0.829->0.829, @8 0.855->0.855, @12 0.855->0.855, @16 0.855->0.855, @20 0.855->0.855
Rang changé : 1 questions ; meilleur 1, pire 0
  pire : 
  meilleur : MR-gc6eabc0b647f3aa1afca:4->1

### C9_simple_hybrid_rerank-final_top_k=16+context_window=1+expand_table_parent=true
| métrique | avant | après | diff [IC95] | P(après<=avant) |
|---|---:|---:|---:|---:|
| passage_hit@8 | 0.882 | 0.882 | +0.000 [+0.000, +0.000] | 1.00 |
| passage_mrr | 0.658 | 0.670 | +0.012 [+0.000, +0.035] | 0.38 |
| hit_ctx | 1.000 | 1.000 | +0.000 [+0.000, +0.000] | 1.00 |
| doc_hit | 0.921 | 0.921 | +0.000 [+0.000, +0.000] | 1.00 |
| obsolete_intrusion | 0.000 | 0.000 | +0.000 [+0.000, +0.000] | 1.00 |

Rang du passage (trouvés) : médiane 1.0 -> 1.0, moyenne 4.17 -> 4.08
Courbe passage hit@k : @1 0.579->0.592, @3 0.697->0.711, @5 0.763->0.776, @8 0.882->0.882, @12 0.908->0.908, @16 0.934->0.934, @20 0.947->0.947
Rang changé : 1 questions ; meilleur 1, pire 0
  pire : 
  meilleur : MR-gc6eabc0b647f3aa1afca:8->1
## abp171 dev (n=102)  before=20261127-011648_abp171_dev_b0fz_before.json  after=20261127-012336_abp171_dev_b0fz_after.json

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
| passage_hit@8 | 0.902 | 0.912 | +0.010 [+0.000, +0.029] | 0.39 |
| passage_mrr | 0.712 | 0.714 | +0.002 [+0.000, +0.005] | 0.39 |
| hit_ctx | 0.980 | 0.990 | +0.010 [+0.000, +0.029] | 0.39 |
| doc_hit | 1.000 | 1.000 | +0.000 [+0.000, +0.000] | 1.00 |
| obsolete_intrusion | 0.000 | 0.000 | +0.000 [+0.000, +0.000] | 1.00 |

Rang du passage (trouvés) : médiane 1.0 -> 1, moyenne 2.71 -> 2.74
Courbe passage hit@k : @1 0.637->0.637, @3 0.735->0.735, @5 0.824->0.824, @8 0.902->0.912, @12 0.971->0.980, @16 0.980->0.990, @20 0.980->0.990
Rang changé : 1 questions ; meilleur 1, pire 0
  pire : 
  meilleur : Q139:None->6
## abpe171 dev (n=102)  before=20261127-011759_abpe171_dev_b0fz_before.json  after=20261127-012434_abpe171_dev_b0fz_after.json

### C9_simple_hybrid_rerank
| métrique | avant | après | diff [IC95] | P(après<=avant) |
|---|---:|---:|---:|---:|
| passage_hit@8 | 0.961 | 0.961 | +0.000 [-0.029, +0.029] | 0.67 |
| passage_mrr | 0.806 | 0.804 | -0.002 [-0.020, +0.013] | 0.58 |
| hit_ctx | 0.961 | 0.961 | +0.000 [-0.029, +0.029] | 0.67 |
| evidence_hit | 0.948 | 0.948 | +0.000 [-0.031, +0.031] | 0.64 |
| evidence_recall | 0.902 | 0.897 | -0.005 [-0.031, +0.016] | 0.73 |
| sufficiency | 0.844 | 0.833 | -0.010 [-0.031, +0.000] | 1.00 |
| doc_hit | 1.000 | 1.000 | +0.000 [+0.000, +0.000] | 1.00 |
| obsolete_intrusion | 0.000 | 0.000 | +0.000 [+0.000, +0.000] | 1.00 |

Rang du passage (trouvés) : médiane 1.0 -> 1.0, moyenne 1.54 -> 1.51
Courbe passage hit@k : @1 0.706->0.696, @3 0.882->0.892, @5 0.931->0.941, @8 0.961->0.961, @12 0.961->0.961, @16 0.961->0.961, @20 0.961->0.961
Courbe evidence_recall_curve : @1 0.581->0.581, @3 0.807->0.818, @5 0.878->0.883, @8 0.902->0.897, @12 0.902->0.897, @16 0.902->0.897, @20 0.902->0.897
Courbe sufficiency_curve : @1 0.469->0.469, @3 0.729->0.729, @5 0.812->0.812, @8 0.844->0.833, @12 0.844->0.833, @16 0.844->0.833, @20 0.844->0.833
Rang changé : 4 questions ; meilleur 2, pire 2
  pire : Q149:6->None, Q158:1->3
  meilleur : Q42:3->2, Q139:None->2

### C9_simple_hybrid_rerank-final_top_k=16+context_window=1+expand_table_parent=true
| métrique | avant | après | diff [IC95] | P(après<=avant) |
|---|---:|---:|---:|---:|
| passage_hit@8 | 0.931 | 0.941 | +0.010 [+0.000, +0.029] | 0.39 |
| passage_mrr | 0.775 | 0.770 | -0.005 [-0.020, +0.006] | 0.79 |
| hit_ctx | 0.980 | 0.980 | +0.000 [+0.000, +0.000] | 1.00 |
| evidence_hit | 0.969 | 0.958 | -0.010 [-0.031, +0.000] | 1.00 |
| evidence_recall | 0.928 | 0.928 | +0.000 [-0.026, +0.021] | 0.53 |
| sufficiency | 0.875 | 0.885 | +0.010 [-0.021, +0.042] | 0.38 |
| doc_hit | 1.000 | 1.000 | +0.000 [+0.000, +0.000] | 1.00 |
| obsolete_intrusion | 0.000 | 0.000 | +0.000 [+0.000, +0.000] | 1.00 |

Rang du passage (trouvés) : médiane 1.0 -> 1.0, moyenne 2.22 -> 2.16
Courbe passage hit@k : @1 0.706->0.696, @3 0.824->0.814, @5 0.892->0.902, @8 0.931->0.941, @12 0.961->0.971, @16 0.980->0.980, @20 0.980->0.980
Courbe evidence_recall_curve : @1 0.581->0.581, @3 0.699->0.704, @5 0.809->0.825, @8 0.861->0.877, @12 0.902->0.918, @16 0.923->0.923, @20 0.928->0.928
Courbe sufficiency_curve : @1 0.469->0.469, @3 0.594->0.594, @5 0.719->0.729, @8 0.792->0.812, @12 0.844->0.865, @16 0.865->0.875, @20 0.875->0.885
Rang changé : 4 questions ; meilleur 2, pire 2
  pire : Q149:2->8, Q158:1->2
  meilleur : Q42:7->4, Q139:14->4
