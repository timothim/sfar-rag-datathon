"""Principle 2: test splits are sealed. Any change to a test file (or an unregistered one) fails."""

from __future__ import annotations

import os
from pathlib import Path

from rag_sfar.evaluation import datasets

ROOT = Path(__file__).resolve().parents[1]


def test_lockbox_intact():
    cwd = os.getcwd()
    os.chdir(ROOT)
    try:
        if not datasets.LOCKBOX_PATH.exists():
            return
        problems = datasets.verify_lockbox()
    finally:
        os.chdir(cwd)
    assert not problems, "Lockbox violated: " + "; ".join(problems)


def test_split_is_deterministic_and_disjoint():
    items = [
        datasets.EvalItem(id=f"q{i}", suite="t", question=f"question numero {i} sur le sujet {i % 7}",
                          question_type="open" if i % 3 else "mcq", provenance="team_written",
                          source_doc_ids=[f"d{i % 5}"])
        for i in range(60)
    ]
    dev1, test1, _ = datasets.make_split(items, 0.4, holdout_doc_fraction=0.2)
    dev2, test2, _ = datasets.make_split(items, 0.4, holdout_doc_fraction=0.2)
    assert [i.id for i in test1] == [i.id for i in test2]
    assert not {i.id for i in dev1} & {i.id for i in test1}
    held = {d for it in test1 if "unseen_doc" in it.tags for d in it.source_doc_ids}
    assert held and not any(set(it.source_doc_ids) & held for it in dev1)
