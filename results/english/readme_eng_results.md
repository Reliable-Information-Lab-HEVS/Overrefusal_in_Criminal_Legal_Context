# English Results

Per-topic refusal results for the English experiments. Each file consolidates
all four models and all four prefix conditions for one OR-Bench category.

## Files

`final/orbench_<topic>200_all.csv` — one file per category (violence, sexual,
harmful, unethical, illegal). Each contains 3,200 rows:
200 prompts × 4 models × 4 conditions.

## Columns

| Column | Meaning |
|---|---|
| `prompt_id` | Stable prompt identifier (e.g. `orbench_harmful_0001`); the same id appears once per condition, which is how baseline and prefixed runs are paired |
| `domain` | Source domain tag (`general`) |
| `category` | OR-Bench category (matches the file topic) |
| `task_variant` | Task phrasing variant (`normal`) |
| `lang` | Language (`en`) |
| `model` | Model that produced the response |
| `backend` | Serving backend (`ollama`) |
| `prompt` | The full prompt sent to the model, including any prefix |
| `response_preview` | Truncated response (first ~300 chars) |
| `response_full` | Full model response (may be empty in some rows) |
| `is_refused` | `True` if the keyword detector flagged a refusal |
| `is_error` | `True` if the run errored; these rows are excluded from analysis |
| `condition` | Prefix condition: `none`, `lawyer`, `supreme`, or `jailbreak` |

## Models

- `llama3.1:8b`
- `gemma4:e4b`
- `qwen3:8b`
- `hf.co/bartowski/swiss-ai_Apertus-8B-Instruct-2509-GGUF:Q4_K_M`

## Conditions

| Value | Meaning |
|---|---|
| `none` | No prefix (baseline) |
| `lawyer` | Defense-lawyer authority prefix |
| `supreme` | Supreme-court authority prefix |
| `jailbreak` | Developer-mode jailbreak prefix |

## Notes

- Refusal labels come from the keyword detector in `over_refusal/detector.py`.
- To pair conditions for statistical tests, match rows on `prompt_id` within a
  model, keeping only ids present in both conditions.
