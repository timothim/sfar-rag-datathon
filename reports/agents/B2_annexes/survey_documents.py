import sys,pickle,re,collections,sqlite3,json
sys.path.insert(0,'src'); sys.path.insert(0,'scripts')
from rag_sfar.ingestion.chunker import _chunk_table_aware_sota, ChunkOptions
from rag_sfar.schemas import Chunk
docs=pickle.load(open(sys.argv[1],'rb'))
con=sqlite3.connect('index/tas_v3_errata/metadata.sqlite')
ids=sys.argv[2].split(',')
def shingles(t,n=8):
    w=re.findall(r'\w+',t.lower()); return [tuple(w[i:i+n]) for i in range(0,max(0,len(w)-n+1),4)]
for pref in ids:
    did=[k for k in docs if k.startswith(pref)][0]; d=docs[did]
    old=[Chunk.model_validate_json(r[0]) for r in con.execute('select payload_json from chunks where doc_id=? order by idx',(did,))]
    new=_chunk_table_aware_sota(d, options=ChunkOptions())
    def stats(cs):
        ty=collections.Counter(c.chunk_type for c in cs)
        cnt=collections.Counter(g for c in cs if c.chunk_type in('prose','recommendation_box','callout_footnote') for g in set(shingles(c.text)))
        dup=sum(1 for g,v in cnt.items() if v>1)/max(1,len(cnt))
        res=sum(len(re.findall(r'\\\\(?:geq|leq|text)|&gt;|<sub>|<sup>|\x00|!\[',c.text)) for c in cs)
        return f"n={len(cs)} {dict(ty)} max={max((len(c.text) for c in cs),default=0)} dup8g={dup:.2%} residus={res} pops={collections.Counter(p for c in cs for p in c.populations)}"
    print(f"== {did} ({len(d.text)} car., {d.metadata.table_count} tableaux, {d.metadata.doc_role}, {d.metadata.language})")
    print("  avant:", stats(old)); print("  après:", stats(new))
