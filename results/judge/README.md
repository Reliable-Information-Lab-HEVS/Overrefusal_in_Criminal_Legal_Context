# LLM-as-a-judge labels

A second, independent pass over every response, produced by `run_judge.py` with
`qwen2.5:14b` served locally (temperature 0). It answers the limitation stated
in the paper: keyword matching is fast and reproducible but undercounts
indirect refusals.

```
orbench.csv              OR-Bench arm, 4 models x 5 categories x en/fr/de   (31 914 rows)
bger_para/<model>.csv    BGer paragraph arm, one file per model             (46 250 rows)
bger_sample.csv          the 20 judgments evaluated as whole documents
US_sample.csv            the "Epstein Files" documents
```

Columns: `prompt_id, category, lang, model, prefix, is_refused_keyword, judge,
judge_label, judge_reason` (`orbench.csv` adds `judge_saw_request`, below).
They join to the corresponding result files on
`(prompt_id, lang, model, prefix)`.

Labels are the three OR-Bench classes — `direct_answer`, `direct_refusal`,
`indirect_refusal` — plus `empty_no_answer` for a strictly empty response, which
is recorded without calling the judge. Only Apertus produces those.

```bash
python helpers/judge_agreement.py            # keyword vs judge, per language and model
```

## Two things to know before quoting a judge number

**1. `indirect_refusal` is not comparable across models.** On Llama it marks
genuine refusals and agrees with the keyword detector (Cohen's κ = 0.94 on the
BGer paragraphs, 0.93 for French OR-Bench). On Gemma, Qwen and Apertus the judge
frequently applies it to a *complete answer that carries a caveat*, which
inflates the rate and, on some cells, reverses the direction of the prefix
effect. `helpers/judge_agreement.py` therefore prints a third measure, `strict`:
a refusal is `direct_refusal`, an empty response, or an `indirect_refusal` that
the keyword detector also flags. Report `judge` for those models only next to
`strict`.

**2. The French and German prefixed OR-Bench rows are not usable.** The judge is
given the request and the response. For those rows the request was rebuilt from
the `prompt` field stored by the runner, which is truncated to 200 characters —
and in French and German the authority prefix alone is longer than that, so the
judge received the prefix with no question behind it and graded answers against
an empty request. Their rates run to 80–98 % and mean nothing. The labels are
released as produced, flagged by `judge_saw_request=False` (7 959 of 31 914
rows); `helpers/judge_agreement.py` shows those cells as `n/a`. English rows are
unaffected: there the prefix and the question sit in the same field, so the
question is present. `run_judge.py` now rebuilds the request from the prompts
file instead, so a re-run does not repeat this.

## What the judge sees on the BGer arm

By design, the judge receives the instruction and the prefix but **never the
judgment text** (`--request instruction`): the corpus is the object under study
and is not handed to a second model. Refusals here are refusals to carry out the
extraction task, which is exactly what is being measured, and the agreement with
the keyword detector on Llama (κ = 0.94) confirms the measurement holds.
