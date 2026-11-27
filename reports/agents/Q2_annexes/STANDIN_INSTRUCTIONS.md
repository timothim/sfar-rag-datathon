# Instructions for a stand-in agent (query rewriting before retrieval, Q2)

You are standing in for the language model of a retrieval-augmented question-answering system built on French medical guidelines. Before the system searches its documents, it sends the user's question to the model with a short instruction: rewrite the question for the search (or, for one kind of prompt, write the passage one expects to find). We measure what the search does with the answers of a capable model. Your task message gives you one folder, `<PART>`: a `part_NN` sub-folder of an export.

## Input
`<PART>/input.json` is a JSON list of about 40 cases. Each case has three fields:
- `case_id`, an opaque identifier;
- `system`, the system prompt, in French: it states the task, what is allowed and forbidden, and the exact output format;
- `user`, the user message: `Question :` followed by a question as a clinician typed it (possibly with typos, missing accents or abbreviations, or already well written).

All cases of one part share the same system prompt. Read it completely before the first case. Then read the cases one at a time, for example:

`.venv/bin/python -c "import json; d=json.load(open('<PART>/input.json')); c=d[K]; print(c['case_id']); print(c['user'])"`

and print `c['system']` once (first case) to read the instruction.

## Task
For each case, write the answer exactly as the model would if `system` were its system prompt and `user` the message it received:
- the system prompt is the only rule: do what it asks, respect everything it forbids, nothing more. If it forbids adding, removing or replacing information, then do not add, remove or replace anything, even something you believe would help. If it asks for a passage written as a guideline would write it, write that passage with your own knowledge;
- the answer is a single line that starts with one of the keywords the system prompt names (`INCHANGEE`, `NORMALISEE:`, `REFORMULEE:` or `PASSAGE:`), with no other text, no explanation, no quotation marks, no Markdown;
- write in French; the options of a multiple-choice question are never shown to you: do not invent any;
- do not answer the question unless the system prompt asks for a passage.

Judge each case on its own: cases are shuffled, unrelated, and you must not let one case influence another (do not reuse a spelling or a term seen in another case to correct this one). Write each answer yourself after reading the case: do not generate answers with a script, a template, a spell-checker or a find-and-replace.

## Isolation
Other agents are answering the other parts at the same time.
- Read and write only inside `<PART>`. Do not open the parent export folder or any other `part_*` folder, and no other file of the repository.
- Do not write anything in the session scratch directory or in /tmp.

## Output
Write `<PART>/output.json`: a JSON list with one object per case, in the same order as the input: `{"case_id": "<same id>", "answer": "<your one-line answer>"}`.

Then verify with a short script that the file parses, has as many objects as the input, the `case_id` values match the input in the same order, and every answer is exactly one non-empty line that is either `INCHANGEE` or starts with the keyword of its system prompt followed by `:` and the text. The import refuses the whole export if one answer breaks the format.

Do not modify any other file and do not run git commands. Final message, two lines at most: the number of answers written, and anything that prevented you from answering a case.

## For the orchestrator
Export `r1`: `eval_internal/work/q2/exports/r1/part_00` … `part_45` (git-ignored: the prompts contain benchmark questions). Parts 00–17: conservative normalisation; 18–35: free reformulation; 36–45: hypothetical passage. One Haiku agent per part, message: "Follow `reports/agents/Q2_annexes/STANDIN_INSTRUCTIONS.md` with `<PART>` = `eval_internal/work/q2/exports/r1/part_NN`." Then:

```bash
.venv/bin/python eval_internal/q2_rewrite_eval.py import --name r1
scripts/with_gpu_lock.sh Q2 env HF_HUB_OFFLINE=1 .venv/bin/python eval_internal/q2_rewrite_eval.py run --answers r1 --tag r1
.venv/bin/python eval_internal/q2_rewrite_eval.py analyze --tag r1
```
Id mapping: `eval_internal/work/q2/keys/r1.json` (outside the export folder).
