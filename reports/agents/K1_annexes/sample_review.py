"""K1 — Prints, for a seeded sample of 35 current documents spread over the classes (ABP excluded),
three chunks each (a statement chunk if any, a table row card if any, a random prose chunk) with
type, section path, grade_levels, start of text (300 chars). Output: sample_review.txt (read by hand).
The texts are SFAR's: this file is a working annex, the report quotes at most 40 words."""
import json, random, sqlite3, sys
sys.path.insert(0, '.')
from corpus_structure_audit import REC_STMT_RE
M = json.load(open('doc_metrics.json'))
quota = {'G1_gradee_numerotee': 8, 'G2_gradee_sans_numero': 8, 'O_ancienne_non_gradee': 5, 'E_anglais': 4,
         'T_tableaux_dominants': 3, 'F_fiche_algo_annexe': 4, 'X_recente_non_gradee': 3}
rng = random.Random(11)
con = sqlite3.connect('../../../index/tas_v6/metadata.sqlite')
out = []
for cls, k in quota.items():
    pool = sorted(m['doc_id'] for m in M if m['cls'] == cls and m['latest'] and m['active'])
    for d in rng.sample(pool, min(k, len(pool))):
        cs = [json.loads(p) for (p,) in con.execute("select payload_json from chunks where doc_id=? and is_reference_section=0 order by idx", (d,))]
        st = [c for c in cs if REC_STMT_RE.search(c['text'])]
        rc = [c for c in cs if c['chunk_type'] == 'table_row_card']
        pr = [c for c in cs if c['chunk_type'] == 'prose']
        pick = ([rng.choice(st)] if st else []) + ([rng.choice(rc)] if rc else []) + ([rng.choice(pr)] if pr else [])
        out.append(f"\n##### {cls} | {d} | chunks={len(cs)}")
        for c in pick:
            out.append(f"--- {c['chunk_id'][-14:]} | {c['chunk_type']} | grades={c['grade_levels']} | SP: {c['section_path'][-110:]}")
            out.append("    " + c['text'][:300].replace("\n", " / "))
open('sample_review.txt', 'w').write("\n".join(out))
print(len([l for l in out if l.startswith('#####')]), 'documents')
