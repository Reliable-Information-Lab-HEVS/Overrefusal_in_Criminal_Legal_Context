# Real legal documents

Three runs on real documents rather than OR-Bench prompts, all with the same two
conditions: no prefix vs. the supreme-court prefix.

| file | unit | documents | rows per model |
|---|---|---|---|
| `bger_para/<model>.csv` | one fact **paragraph** | 192 BGer judgments, 1 652 paragraphs | 9 912 (en/fr/de) or 13 216 (+ it) |
| `bger_sample.csv` | one **whole** judgment | the first 20 judgments | 120 |
| `US_sample.csv` | one whole document | 10 public "Epstein Files" documents | 60 |

`bger_para/` is the paper's Table 2. Reproduce it with:

```bash
python helpers/table_realtext.py
```

## Columns

`prompt_id, category, lang, model, prefix, is_refused, is_empty, is_error,
response_preview`

- `prompt_id` joins to `data/bger_para200.csv` (`bgr_014_p03` = judgment 14,
  paragraph 3).
- `prefix` is `none` or `supreme-court`.
- `is_refused` is the keyword detector's verdict, precomputed.
- `is_empty` marks a strictly empty generation. Only Apertus produces them, and
  the paper counts them as functional refusals; `helpers/table_realtext.py`
  prints its rates both ways.
- `response_preview` holds the first 500 characters of the response — enough for
  the opening-window detector and for inspection. Full responses are not
  released for this arm: they run to about 95 MB.

Llama 3.1 and Apertus were also run in Italian, which is why their files are
larger; the paper reports en/fr/de, the three languages covered by all four
models.
