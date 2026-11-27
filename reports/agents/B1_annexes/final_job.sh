#!/bin/bash
# B1 final job: notes (new walk) vs current C10, two C10 candidates on tas_v3_errata,
# then C9 / C9+windows / both C10 candidates on the newest index with a manifest.
cd /Users/tim/Me/SFAR-datathon
export HF_HUB_OFFLINE=1
PY=".venv/bin/python -u /private/tmp/claude-501/-Users-tim--claude-spares-spare-xXtqK0/fdfce601-0588-4326-8d77-e9ea020e9a31/scratchpad/b1eval.py"
$PY "R_NS2:final_top_k=16+context_window=1+expand_table_parent=true+attach_table_notes=true+max_chunks_per_doc=16+population_quota=1+population_counterpart=true+table_notes_mode=called_scope" "F0:final_top_k=16+context_window=1+expand_table_parent=true+attach_table_notes=true+max_chunks_per_doc=16+table_notes_mode=called_scope+context_hygiene=true" "FG:final_top_k=16+context_window=1+expand_table_parent=true+attach_table_notes=true+max_chunks_per_doc=16+table_notes_mode=called_scope+context_hygiene=true+population_quota=1+population_guard=true"
NEW=tas_v5; [ -f index/tas_v6/manifest.json ] && NEW=tas_v6
echo "NEWEST_INDEX $NEW"
$PY "${NEW}_C9:" "${NEW}_C9W:final_top_k=16+context_window=1+expand_table_parent=true" "${NEW}_F0:final_top_k=16+context_window=1+expand_table_parent=true+attach_table_notes=true+max_chunks_per_doc=16+table_notes_mode=called_scope+context_hygiene=true" "${NEW}_FG:final_top_k=16+context_window=1+expand_table_parent=true+attach_table_notes=true+max_chunks_per_doc=16+table_notes_mode=called_scope+context_hygiene=true+population_quota=1+population_guard=true" --index $NEW
echo "COVERAGE_HOLDOUT"
.venv/bin/python reports/agents/B1_annexes/cov_holdout.py tas_v3_errata reports/agents/B1_annexes/ood_medical_queries.txt C9 2>&1 | grep -v -i -E "warn|Loading|Redirect"
