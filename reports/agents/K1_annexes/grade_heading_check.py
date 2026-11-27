"""K1 — Chunks presented under a heading that is a grade line ("### GRADE 2 (Accord fort)").
Counts how many of them hold a different statement, or a different question, than the one the
grade belongs to, and whether the grade in the heading differs from the grade in the chunk text.
Read-only on index/tas_v6."""
import collections, json, re, sqlite3, sys
sys.path.insert(0, '.')
from corpus_structure_audit import GRADE_ANY, REC_STMT_RE, is_abp
con = sqlite3.connect('../../../index/tas_v6/metadata.sqlite')
HEAD_GRADE = re.compile(r"(?:^|> )\W*(?:GRADE|Grade|AVIS|Avis|ACCORD|Accord|G[12][+\-])[^>]*$")
norm = lambda g: re.sub(r"\W+", " ", g.lower()).strip()
c = collections.Counter(); docs = collections.defaultdict(set); ex = []
for (p,) in con.execute("select payload_json from chunks where is_reference_section=0 order by idx"):
    ch = json.loads(p)
    if is_abp(ch['doc_title'], ch['doc_id']):
        continue
    sp = ch['section_path']
    parts = sp.split(' > ')
    gparts = [x for x in parts if GRADE_ANY.search(x) and HEAD_GRADE.search(x)]
    if not gparts:
        continue
    c['chunks_under_grade_heading'] += 1; docs['all'].add(ch['doc_id'])
    if ch['is_latest_edition']:
        c['current'] += 1; docs['current'].add(ch['doc_id'])
    t = ch['text']
    if REC_STMT_RE.search(t):
        c['holding_a_statement'] += 1; docs['stmt'].add(ch['doc_id'])
        own = [norm(m.group(0)) for m in GRADE_ANY.finditer(t)]
        hg = norm(GRADE_ANY.search(gparts[-1]).group(0))
        if own and hg not in own:
            c['statement_grade_differs_from_heading_grade'] += 1; docs['differs'].add(ch['doc_id'])
            if len(ex) < 15:
                ex.append((ch['chunk_id'], gparts[-1][:40], own[:3]))
    if re.search(r"(?im)^\W*Question\s*\d", t) and re.search(r"Question\s*\d", sp):
        qs_t = re.findall(r"Question\s*(\d+(?:\.\d+)?)", t)
        qs_p = re.findall(r"Question\s*(\d+(?:\.\d+)?)", sp)
        if qs_t and qs_p and qs_t[0] != qs_p[-1]:
            c['chunk_question_differs_from_path_question'] += 1; docs['qdiff'].add(ch['doc_id'])
out = {**c, **{f'docs_{k}': len(v) for k, v in docs.items()}, 'examples': ex}
json.dump(out, open('grade_heading_check.json', 'w'), ensure_ascii=False, indent=1)
print(json.dumps(out, ensure_ascii=False, indent=1))
