"""Count current-edition documents on which the guarded population rule can fire: >= 3 table
row cards of each population (adult / paediatric), with the same population function as the
pipeline (`populations` when the index has it, else `population_hint`)."""
import json, sqlite3, sys, collections
from rag_sfar.retrieval.pipeline import _chunk_population
from rag_sfar.schemas import Chunk
idx = sys.argv[1]
db = sqlite3.connect(f"index/{idx}/metadata.sqlite")
cnt = collections.defaultdict(collections.Counter)
titles = {}
for doc, payload in db.execute("select doc_id, payload_json from chunks where is_latest_edition=1 and chunk_type='table_row_card'"):
    c = Chunk.model_validate_json(payload)
    cnt[doc][_chunk_population(c)] += 1
    titles[doc] = c.doc_title
docs = [d for d, c in cnt.items() if c["adulte"] >= 3 and c["pediatrie"] >= 3]
print(f"{idx}: {len(cnt)} documents with row cards; guard true on {len(docs)}")
for d in docs:
    print(f"  {titles[d][:90]} adulte={cnt[d]['adulte']} pediatrie={cnt[d]['pediatrie']}")
