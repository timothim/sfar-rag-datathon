"""K3 - Supplies `continuation_gap` to table_parser.parse_html_table without editing chunker.py.

chunker.py (owned by another agent at the time) calls parse_html_table without the text that sits
between two tables. `install()` wraps, in this process only, chunker._chunk_table_aware_sota (to
know the current document and split its text exactly as the chunker does) and
chunker.parse_html_table (to pass `continuation_gap` = the text between the immediately preceding
table and this one, unless that preceding table is itself a headerless table of the same width
that was refused the same headers: the chain of continuations is then broken). A preceding
table of another width (e.g. a narrower sub-table whose empty columns the OCR dropped) neither
carries nor breaks the chain. Production use would need the same two values computed
at the chunker's call site.
"""
from __future__ import annotations

import re

import rag_sfar.ingestion.chunker as ch

_TABLE_SPLIT = re.compile(r"(<table\b.*?</table>)", re.S | re.I)


def install() -> None:
    orig_parse = ch.parse_html_table
    orig_chunk = ch._chunk_table_aware_sota
    st: dict = {}

    def chunk(doc, *args, **kwargs):
        opts = kwargs.get("options") or ch.ChunkOptions()
        text = doc.text
        if opts.clean_ocr and "\x00" in text:
            text = (kwargs.get("nul_repairer") or ch.NulRepairer())(text)
        st.clear()
        st.update(tokens=_TABLE_SPLIT.split(text), pos=0, last_tok=None, last_carried=None, before=None)
        return orig_chunk(doc, *args, **kwargs)

    def parse(tok, previous_headers=None, previous_is_contiguous=True, carry_first_cell=None, continuation_gap=None):
        toks = st.get("tokens") or []
        try:
            ti = toks.index(tok, st.get("pos", 0))
        except ValueError:
            ti = -1
        if ti >= 0 and ti == st.get("last_tok"):
            # Re-parse of the same table (carry undo): restore the state seen by the first parse.
            last_tok, last_carried = st["before"]
        else:
            last_tok, last_carried = st.get("last_tok"), st.get("last_carried")
            st["before"] = (last_tok, last_carried)
        gap = None
        if (
            previous_headers
            and ti >= 0
            and last_tok is not None
            and last_carried != ("refused", tuple(previous_headers))
        ):
            gap = "".join(toks[last_tok + 1: ti])
        t = orig_parse(tok, previous_headers=previous_headers, previous_is_contiguous=previous_is_contiguous,
                       carry_first_cell=carry_first_cell, continuation_gap=gap)
        if ti >= 0:
            st["pos"] = ti
            st["last_tok"] = ti
            refused = (
                previous_headers and not t.has_explicit_headers and not t.inherited_headers
                and t.num_cols == len(previous_headers)
            )
            st["last_carried"] = ("refused", tuple(previous_headers)) if refused else None
        return t

    ch._chunk_table_aware_sota = chunk
    ch.parse_html_table = parse
