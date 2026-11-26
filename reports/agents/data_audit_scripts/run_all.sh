#!/usr/bin/env bash
# Relance tout l'audit des données (lecture seule du corpus ; sorties dans ./out). ~30 s, CPU léger.
set -euo pipefail
cd "$(dirname "$0")/../../.."
PY=.venv/bin/python
export PYTHONPATH=src
D=reports/agents/data_audit_scripts
$PY $D/01_inventory.py        > $D/out/01_stdout.txt
$PY $D/02_ocr_quality.py      > $D/out/02_stdout.txt
$PY $D/02b_dump_loader.py     > $D/out/02b_stdout.txt
$PY $D/03_editions.py         > $D/out/03_stdout.txt
$PY $D/03a_domain_check.py    > $D/out/03a_stdout.txt
$PY $D/04_reco_markers.py     > $D/out/04_stdout.txt
$PY $D/05_tables.py           > $D/out/05_stdout.txt
$PY $D/06_references_share.py > $D/out/06_stdout.txt
echo "OK — résultats dans $D/out/"
