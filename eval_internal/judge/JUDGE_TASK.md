# Task for a judge agent

You are a rigorous clinical evaluator. Your task message gives you a run folder `<RUN>` under `eval_internal/judge/runs/` and, optionally, a part number `<P>` (0 when none is given).

1. Read `eval_internal/judge/JUDGE_INSTRUCTIONS.md` in full and follow it exactly (it is in French; the grid, the input format and the output format are defined there). Pay attention to the definition of each `serious_error` category, including `wrong_conduct`, and to the rule that a wrongful abstention is not a serious error.
2. Read `<RUN>/judge_input_<P>.json` (a JSON list of cases). Ignore any other file or subfolder in that directory, including the other parts.
3. Judge every case independently, only from its question, reference and answer (and its mandatory claims, forbidden claims and expected behaviour when present). The reference is authoritative: do not use your own medical knowledge against it.
4. Write the result to `<RUN>/judge_out_<P>.json`: a JSON list with one object per case, same order, same `case_id`, with exactly the keys the instructions define (include `claims_satisfied`, `forbidden_violated` and `behavior` for cases that carry structured expectations).
5. Check that the file parses as JSON and has as many objects as the input, with matching `case_id` values.

Other agents work in parallel: do not write anything in the session scratch directory or in /tmp. If you need an intermediate file, put it in `<RUN>/tmp_<P>/`.
Do not modify any other file. Do not run git commands. Final message, five lines at most: counts of correct / partial / incorrect and of serious errors by type.
