# Instructions for a stand-in generator agent

You are standing in for the language model of a retrieval-augmented question-answering system, so that we can measure how a strong model answers the exact prompts our engine produces. Your task message gives you one folder, `<PART>`: a `part_NN` sub-folder of an export.

## Input
`<PART>/gen_input.json` is a JSON list of at most 8 cases. Each case has three fields:
- `case_id`, an opaque identifier;
- `system`, the system prompt, in French;
- `user`, the user message: excerpts of medical guidelines followed by a question.

The file is large: do not print it whole. Read the cases one at a time, for example with:

`.venv/bin/python -c "import json; d=json.load(open('<PART>/gen_input.json')); c=d[K]; print(c['case_id']); print(c['system']); print(c['user'])"`

Read each case's `system` and `user` text completely before answering it.

## Task
For each case, write the answer exactly as the model would if `system` were its system prompt and `user` the message it received:
- follow the system prompt's rules and output format to the letter;
- answer in French;
- use only the excerpts contained in `user`;
- if the excerpts do not allow an answer, do what the system prompt says to do in that situation.

Do not use your own medical knowledge and do not look anything up. Do not let one case influence another. Write each answer yourself after reading the case: do not generate answers with a script or a template.

## Isolation
Other agents are answering the other parts at the same time.
- Read and write only inside `<PART>`. Do not open the parent export folder or any other `part_*` folder.
- Do not open `eval_internal/work/replay/frontier_keys/`, the datasets, the reports or any other file of the repository.
- Do not write anything in the session scratch directory or in /tmp. If you need intermediate files, create them in `<PART>/work/`.

## Output
Write `<PART>/gen_out.json`: a JSON list with one object per case, in the same order as the input. Each object is `{"case_id": "<same id>", "answer": "<the full text of your answer>"}`.

Then verify:
- the file parses;
- it has as many objects as the input;
- the `case_id` values match the input, in order;
- for each case, re-read the question at the end of its `user` text and confirm that your answer is about that question.

The import refuses the whole export if an answer is missing, filed in the wrong part or duplicated, or if two different cases get the same long answer.

Do not modify any other file and do not run git commands. Final message, two lines at most: the number of answers written, and anything that prevented you from answering a case.

## For the orchestrator
Export and import:

```bash
.venv/bin/python eval_internal/gen_replay.py run --cache <CACHE> --suite <S1,S2> [--split test --allow-test] \
    --profile production --backend record --tag <TAG> --export-frontier eval_internal/work/replay/frontier/<NAME>
# one agent per eval_internal/work/replay/frontier/<NAME>/part_NN, given these instructions
.venv/bin/python eval_internal/gen_replay.py import-frontier --dir eval_internal/work/replay/frontier/<NAME> \
    --model-label <MODEL> --tag <TAG>
```

The export writes, outside the export folder, the file `eval_internal/work/replay/frontier_keys/<NAME>.json`. It holds the mapping from opaque id to real id, the prompts and the replay rows.

The import:
- checks that every prompt contains its own question;
- maps the answers back to the questions;
- computes the deterministic answer check (`check_flag`) for each answer;
- writes one report per suite in `reports/eval/b3/`.
