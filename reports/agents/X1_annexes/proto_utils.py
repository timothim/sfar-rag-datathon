import re, unicodedata
CTX = ("Tableau :", "Section :", "Sous-catégorie :", "Périmètre :", "Note")
def cell_line(t):
    for l in t.splitlines():
        if " | " in l and not l.startswith(CTX): return l
    return ""
def fold(s):
    s = unicodedata.normalize("NFKD", s); s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower().replace("\\", "")
    s = re.sub(r"[*#†‡]", " ", s); s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())
def label(t):
    cell = cell_line(t).split(" | ")[0]
    h, sep, v = cell.partition(" : ")
    if not sep: return None, None
    return fold(h.split(" / ")[0]), v
