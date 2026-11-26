# RAG-SFAR — Résultats d'Ablation Comparative

## Benchmark : `antibioprophylaxie_171`

| Config | Strategy | Edition Hit@8 | Obsolète Intrusion | Evidence Recall | Allergie Recall | MRR | Latence (ms) | ~Tokens |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `C0_naive_fixed_bm25` | naive_fixed | **94.7%** | 62.0% | **92.0%** | **83.3%** | 0.803 | 0.9 | 2393 |
| `C2_hierarchical_bm25_no_refs` | hierarchical_markdown | **97.1%** | 64.3% | **94.2%** | **83.3%** | 0.862 | 0.9 | 1792 |
| `C3_table_sota_bm25_lexicon` | table_aware_sota | **95.3%** | 55.0% | **94.2%** | **66.7%** | 0.836 | 2.1 | 1469 |
| `C4_table_sota_dense` | table_aware_sota | **98.8%** | 87.7% | **87.0%** | **100.0%** | 0.831 | 21.7 | 985 |
| `C5_table_sota_hybrid_rrf` | table_aware_sota | **99.4%** | 76.0% | **95.7%** | **100.0%** | 0.917 | 12.3 | 1151 |
| `C6_hybrid_temporal_metadata` | table_aware_sota | **100.0%** | 0.0% | **97.8%** | **100.0%** | 0.983 | 13.6 | 1030 |
| `C7_sota_rerank_callouts` | table_aware_sota | **100.0%** | 0.0% | **99.3%** | **100.0%** | 0.985 | 216.7 | 1263 |
| `C8_frontier_2026_tri_dbsf_crag` | table_aware_sota | **99.4%** | 0.0% | **99.3%** | **100.0%** | 0.982 | 209.9 | 1142 |

## Benchmark : `multi_rfe_stress_30`

| Config | Strategy | Edition Hit@8 | Obsolète Intrusion | Evidence Recall | Allergie Recall | MRR | Latence (ms) | ~Tokens |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `C0_naive_fixed_bm25` | naive_fixed | **100.0%** | 35.7% | **96.7%** | **100.0%** | 0.956 | 1.0 | 2379 |
| `C2_hierarchical_bm25_no_refs` | hierarchical_markdown | **100.0%** | 57.1% | **93.3%** | **75.0%** | 0.931 | 1.1 | 1953 |
| `C3_table_sota_bm25_lexicon` | table_aware_sota | **96.7%** | 35.7% | **90.0%** | **50.0%** | 0.903 | 2.2 | 1609 |
| `C4_table_sota_dense` | table_aware_sota | **100.0%** | 53.6% | **96.7%** | **100.0%** | 0.967 | 12.0 | 1282 |
| `C5_table_sota_hybrid_rrf` | table_aware_sota | **100.0%** | 39.3% | **96.7%** | **100.0%** | 0.983 | 14.3 | 1392 |
| `C6_hybrid_temporal_metadata` | table_aware_sota | **100.0%** | 0.0% | **93.3%** | **75.0%** | 1.000 | 13.2 | 1286 |
| `C7_sota_rerank_callouts` | table_aware_sota | **100.0%** | 0.0% | **96.7%** | **100.0%** | 1.000 | 190.4 | 1403 |
| `C8_frontier_2026_tri_dbsf_crag` | table_aware_sota | **100.0%** | 0.0% | **96.7%** | **100.0%** | 1.000 | 241.2 | 1326 |
