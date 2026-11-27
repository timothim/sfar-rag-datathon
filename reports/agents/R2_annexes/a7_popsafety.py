"""Clinical-safety proxy: contexts holding an adult row and a paediatric row of the same act
(similar act label) with different molecule/dose cells. Does the chunk text or only the section
heading (shown in the source header) say which population each row is for?"""
import sys, os, re, collections
sys.path.insert(0, os.path.dirname(__file__))
from common import rows, items, chunks, attribute
from rag_sfar.retrieval.medical_lexicon import tokenize_medical_french
byid, _ = chunks()
POP_TXT = re.compile(r"\b(enfants?|p[ée]diatri\w*|nourrissons?|nouveau-n[ée]s?|n[ée]onat\w*|adultes?)\b|mg\s*/\s*kg", re.I)
POP_SEC = re.compile(r"p[ée]diatri|n[ée]onat|enfant|adulte", re.I)
def field(text, name):
    m = re.search(rf"{name}[^:]*:\s*([^|\n]+)", text, re.I)
    return m.group(1).strip() if m else ""
def act(text):
    return set(tokenize_medical_french(field(text, "Actes")))
def sec_pop(c):
    s = c.section_path.lower()
    if re.search(r"p[ée]diatri|n[ée]onat", s): return "ped"
    if "adulte" in s: return "adult"
    return None
for name in sys.argv[1:] or ["WN", "C10"]:
    for suite in ("abpe171", "abp171", "multirfe_synth"):
        R, I = rows(name, suite), items(suite)
        if not R: continue
        st = collections.Counter(); examples = []
        for qid, row in R.items():
            pop = row.get("pop")
            cards = [(byid[c], o) for c, o in zip(row["chunks"], attribute(row) if "reasons" in row else ["?"] * len(row["chunks"])) if byid[c].chunk_type == "table_row_card"]
            ad = [(c, o) for c, o in cards if sec_pop(c) == "adult"]
            pe = [(c, o) for c, o in cards if sec_pop(c) == "ped"]
            if ad and pe:
                st["q_both_pops"] += 1
                if pop == "non_specifie": st["q_both_pops_pop_unstated"] += 1
            found = False
            for a, oa in ad:
                for p, op in pe:
                    A, P = act(a.text), act(p.text)
                    if not A or not P: continue
                    j = len(A & P) / len(A | P)
                    if j < 0.5: continue
                    ma, mp = field(a.text, "Mol"), field(p.text, "Mol")
                    da, dp = field(a.text, "Dose"), field(p.text, "Dose")
                    if (ma, da) == (mp, dp): continue
                    if not found:
                        found = True
                        st["q_same_act_diff_conduct"] += 1
                        txt_ok = bool(POP_TXT.search(a.text)) or bool(POP_TXT.search(p.text))
                        st["  ...text_disambiguates(either)"] += txt_ok
                        st["  ...text_disambiguates(both)"] += bool(POP_TXT.search(a.text)) and bool(POP_TXT.search(p.text))
                        st["  ...section_heading_disambiguates"] += bool(POP_SEC.search(a.section_path)) and bool(POP_SEC.search(p.section_path))
                        st["  ...question_pop=" + str(pop)] += 1
                        st["  ...added_by_population_rule"] += (oa.startswith("population") or op.startswith("population"))
                        if len(examples) < 4:
                            examples.append((qid, pop, a.text[:200], p.text[:200]))
        print(name, suite, "n=", len(R), dict(st))
        for e in examples: print("     ", e)
