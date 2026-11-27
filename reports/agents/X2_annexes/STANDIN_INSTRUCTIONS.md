# Instructions for a stand-in agent (multi-query retrieval prompts, X2)

You are standing in for the language model of a retrieval-augmented question-answering system. Before the system searches its documents, it asks the model a short question about the search itself (whether a question has several parts, or whether the passages found so far miss a part). We measure what the search does with the answers of a strong model. Your task message gives you one folder, `<PART>`: a `part_NN` sub-folder of an export.

## Input
`<PART>/input.json` is a JSON list of at most 20 cases. Each case has three fields:
- `case_id`, an opaque identifier;
- `system`, the system prompt, in French: it states the task and the exact output format;
- `user`, the user message: a question (and, for one kind of prompt, a list of passages reduced to their title, section and first line).

Read the cases one at a time, for example:

`.venv/bin/python -c "import json; d=json.load(open('<PART>/input.json')); c=d[K]; print(c['case_id']); print(c['system']); print(c['user'])"`

Read the `system` text of the first case completely; read it again whenever it differs from the previous case (two different system prompts may appear in an export).

## Task
For each case, write the answer exactly as the model would if `system` were its system prompt and `user` the message it received:
- follow the rules of the system prompt and its output format to the letter: the first line is one of the keywords it names, the following lines (if any) have exactly the form it shows, there is no other text, no explanation, no Markdown;
- write sub-questions or search queries in French;
- do not answer the medical question itself; do not add medical information that is not in the question; do not use your own medical knowledge to name a drug, a value or a guideline that the question does not name.

Judge each case on its own; do not let one case influence another. Write each answer yourself after reading the case: do not generate answers with a script or a template.

## Isolation
Other agents are answering the other parts at the same time.
- Read and write only inside `<PART>`. Do not open the parent export folder or any other `part_*` folder, and no other file of the repository.
- Do not write anything in the session scratch directory or in /tmp.

## Output
Write `<PART>/output.json`: a JSON list with one object per case, in the same order as the input: `{"case_id": "<same id>", "answer": "<your answer, lines separated by \n>"}`.

Then verify with a short script that the file parses, has as many objects as the input, the `case_id` values match the input in order, and every answer's first line is one of the keywords allowed by its system prompt. The import refuses the whole export if one answer breaks the format.

Do not modify any other file and do not run git commands. Final message, two lines at most: the number of answers written, and anything that prevented you from answering a case.

## For the orchestrator
```bash
.venv/bin/python eval_internal/multi_query_eval.py import --name <NAME>
```
Exports live in `eval_internal/work/x2/exports/<NAME>/` (git-ignored: the prompts contain benchmark questions); id mappings in `eval_internal/work/x2/keys/<NAME>.json`.
