"""03 - Éditions et supersession.

1) Regroupe les fichiers en « recommandations » (landing_url / titre normalisé) et repère
   les recommandations à plusieurs fichiers (texte court/long, traduction, fiches...).
2) Repère génériquement les paires d'éditions candidates : similarité de titre entre
   documents d'années différentes + mention explicite dans le texte d'une version antérieure
   (« actualisation / réactualisation / mise à jour / remplace / révision ... de 20xx »).
3) Compare au graphe de supersession calculé par le loader (out/loader_metadata.json,
   produit par 02b_dump_loader.py) : lignées correctes, douteuses, éditions manquées.

Relancer : .venv/bin/python reports/agents/data_audit_scripts/03_editions.py
Sorties  : out/editions.json (+ stdout)
"""
from __future__ import annotations

import collections
import json
import re
from pathlib import Path

from common import OUT, ROOT, norm_for_match, read

inv = {r["md"]: r for r in json.loads((OUT / "inventory.json").read_text())["rows"]}
lm = json.loads((OUT / "loader_metadata.json").read_text())
for r in lm:
    r["md"] = str(Path(r["md_path"]).resolve().relative_to(ROOT))
by_md = {r["md"]: r for r in lm}

STOP = set("""de des du la le les l d un une et en au aux a à pour par sur chez dans avec sans ou
recommandations recommandation rfe rpp prise charge sfar formalisees experts expert patient patients
adulte adultes gestion""".split())


def title_tokens(t: str) -> set[str]:
    t = norm_for_match(t or "")
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    return {w for w in t.split() if w not in STOP and len(w) > 2}


# ------------------------------------------------------------ 1. familles
fam = collections.defaultdict(list)
for md, r in inv.items():
    key = r.get("landing_url") or ("title:" + norm_for_match(r.get("title") or ""))
    fam[key].append(md)
multi = {k: v for k, v in fam.items() if len(v) > 1}

# ------------------------------------------------------------ 2a. mentions explicites
MENTION = re.compile(
    r"[^.\n]{0,200}\b(actualis\w*|r[ée]actualis\w*|mise à jour|mettre à jour|remplac\w+|abrog\w+|annule\w*|se substitu\w+|r[ée]vision|nouvelle version|updat\w+|replac\w+|supersed\w+)\b[^.\n]{0,250}", re.I)
YEAR = re.compile(r"\b(19[89]\d|20[0-2]\d)\b")
mentions = {}
for md, r in inv.items():
    txt = read(ROOT / md)
    head = re.sub(r"<[^>]+>", " ", txt[:25000])
    found = []
    for m in MENTION.finditer(head):
        s = m.group(0)
        yrs = [int(y) for y in YEAR.findall(s)]
        if yrs and re.search(r"recommandation|conf[ée]rence|rfe|rpp|guideline|propositions|r[ée]f[ée]rentiel|texte", s, re.I):
            found.append({"years": yrs, "snippet": re.sub(r"\s+", " ", s.strip())[:260],
                          "line": txt[:txt.find(s[:40]) if s[:40] in txt else 0].count("\n") + 1})
    if found:
        mentions[md] = found

# ------------------------------------------------------------ 2b. paires par titre
items = [(md, r) for md, r in by_md.items()]
pairs = []
for i in range(len(items)):
    for j in range(i + 1, len(items)):
        a, b = items[i][1], items[j][1]
        ya, yb = a["effective_year"], b["effective_year"]
        if not ya or not yb or ya == yb:
            continue
        ta, tb = title_tokens(a["title"]), title_tokens(b["title"])
        if not ta or not tb:
            continue
        inter = len(ta & tb)
        jac = inter / len(ta | tb)
        cont = inter / min(len(ta), len(tb))
        if jac >= 0.45 or (cont >= 0.75 and inter >= 2):
            old, new = (a, b) if ya < yb else (b, a)
            pairs.append({"old": old["md"], "new": new["md"], "old_year": old["effective_year"], "new_year": new["effective_year"],
                          "old_title": old["title"], "new_title": new["title"], "jac": round(jac, 2), "cont": round(cont, 2),
                          "same_lineage": bool(old["topic_lineage"]) and old["topic_lineage"] == new["topic_lineage"],
                          "loader_old_superseded": not old["is_latest_edition"],
                          "text_mentions_old_year": any(old["effective_year"] in m["years"] for m in mentions.get(new["md"], []))})

# ------------------------------------------------------------ 3. évaluation des lignées du loader
lineages = collections.defaultdict(list)
for r in lm:
    if r["topic_lineage"]:
        lineages[r["topic_lineage"]].append(r)
lin_eval = []
for lin, docs in lineages.items():
    latest_year = max(d["effective_year"] or 0 for d in docs if d["language"] != "en")
    for d in docs:
        if d["is_latest_edition"]:
            continue
        sup = by_md.get(next((x["md"] for x in lm if x["doc_id"] == d["superseded_by"]), ""), {})
        tj = title_tokens(d["title"]) & title_tokens(sup.get("title", ""))
        ment = [m for m in mentions.get(sup.get("md", ""), []) if d["effective_year"] in m["years"]]
        lin_eval.append({"lineage": lin, "old": d["md"], "old_year": d["effective_year"], "old_title": d["title"],
                         "new": sup.get("md"), "new_year": d["superseded_by_year"], "new_title": sup.get("title"),
                         "title_overlap": sorted(tj), "explicit_mention_in_new": [m["snippet"][:180] for m in ment][:1]})
missed = [p for p in pairs if not p["same_lineage"] and not p["loader_old_superseded"]]

out = {"families_multi_files": {k: v for k, v in multi.items()}, "n_families": len(fam), "n_families_multi": len(multi),
       "mentions": mentions, "title_pairs": pairs, "lineage_eval": lin_eval, "missed_candidates": missed,
       "lineages": {k: [(d["effective_year"], d["language"], d["doc_role"], d["is_latest_edition"], d["title"][:70]) for d in sorted(v, key=lambda x: x["effective_year"] or 0)] for k, v in lineages.items()}}
(OUT / "editions.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str))

print("familles (landing_url/titre):", len(fam), "dont multi-fichiers:", len(multi))
print("docs avec mention explicite d'une version antérieure datée:", len(mentions))
print("paires de titres inter-années:", len(pairs), "| dans la même lignée loader:", sum(p["same_lineage"] for p in pairs),
      "| ancienne non marquée superseded:", len(missed))
print("\n=== Éditions candidates manquées par le loader (titre similaire, année différente) ===")
for p in sorted(missed, key=lambda x: -x["jac"]):
    print(f"  {p['old_year']}→{p['new_year']} J={p['jac']} C={p['cont']} mention={p['text_mentions_old_year']}\n     OLD {p['old_title'][:90]}\n     NEW {p['new_title'][:90]}")
print("\n=== Supersessions du loader : recouvrement de titre / mention explicite ===")
for e in sorted(lin_eval, key=lambda x: x["lineage"]):
    print(f"  [{e['lineage']}] {e['old_year']}→{e['new_year']} overlap={e['title_overlap'][:4]} mention={'OUI' if e['explicit_mention_in_new'] else 'non'}\n     OLD {e['old_title'][:80]}\n     NEW {(e['new_title'] or '')[:80]}")
print("\n=== Mentions explicites (extraits) ===")
for md, ms in list(mentions.items()):
    for m in ms[:2]:
        print(f"  {md}:{m['line']} {m['years']}  «{m['snippet'][:200]}»")
