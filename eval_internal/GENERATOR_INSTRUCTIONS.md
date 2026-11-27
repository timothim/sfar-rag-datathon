# Instructions for a stand-in generator agent

You are standing in for the language model of a retrieval-augmented question-answering system, so that we can measure how a strong model answers the exact prompts our engine produces. Your task message gives you a folder `<DIR>` and a part number `<I>`.

Input: `<DIR>/gen_input_<I>.json`, a JSON list of at most 12 cases, each with `case_id`, `suite`, `system` (the system prompt, in French) and `user` (the user message: excerpts of medical guidelines followed by a question). The file is large (up to about 350,000 characters): do not print it whole. Read the cases one at a time, for example with
`.venv/bin/python -c "import json; d=json.load(open('<DIR>/gen_input_<I>.json')); c=d[K]; print(c['case_id']); print(c['system']); print(c['user'])"`.
Read each case's `system` and `user` text completely before answering it.

For each case, write the answer exactly as the model would if `system` were its system prompt and `user` the message it received: follow the system prompt's rules and output format to the letter, answer in French, and use only the excerpts contained in `user`. Do not use your own medical knowledge, do not look anything up, do not open any other file of the repository, and do not let one case influence another. If the excerpts do not allow an answer, do what the system prompt says to do in that situation. Write each answer yourself after reading the case: do not generate answers with a script or a template.

Isolation: other agents do the same job on other files at the same time, and a previous run was ruined because agents saved drafts under the same names in the shared scratch directory and overwrote each other. Do not write anything in the session scratch directory or in /tmp. If you need intermediate files, create and use only `<DIR>/work_<I>/` (yours alone). Never read a `gen_out_*.json` or a `work_*` directory that is not yours.

Output: `<DIR>/gen_out_<I>.json`, a JSON list with one object per case in the same order: `{"case_id": "<same id>", "answer": "<the full text of your answer>"}`. Then verify: the file parses, has as many objects as the input, the `case_id` values match the input in order, and, for each case, re-read the question at the end of its `user` text and confirm that your answer is about that question.

Do not modify any other file and do not run git commands. Final message, two lines at most: the number of answers written and anything that prevented you from answering a case.
