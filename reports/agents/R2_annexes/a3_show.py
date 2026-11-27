"""Print sampled additions (question, gold doc, added chunk) for manual relevance reading."""
import sys, os, json, random
sys.path.insert(0, os.path.dirname(__file__))
from common import items, chunks
byid, _ = chunks()
S = json.load(open(os.path.join(os.path.dirname(__file__), f"samples_{sys.argv[1]}.json")))
key = sys.argv[2]; n = int(sys.argv[3]); random.seed(int(sys.argv[4]) if len(sys.argv) > 4 else 0)
lst = S[key]
for qid, cid in (random.sample(lst, min(n, len(lst)))):
    suite = key.split("|")[0]
    it = items(suite)[qid]; c = byid[cid]
    print(f"--- {qid} pop? | Q: {it.formatted_query()[:260]!r}")
    print(f"    gold_docs: {[g[:60] for g in it.gold_doc_ids]}")
    print(f"    ADDED [{c.chunk_type}] doc={c.doc_id[:60]} pops={getattr(c,'populations',None)} hint={c.population_hint}")
    print(f"    section: {c.section_path[:160]}")
    print(f"    text: {c.text[:350]!r}")
