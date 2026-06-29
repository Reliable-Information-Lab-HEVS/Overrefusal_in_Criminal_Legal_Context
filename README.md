# Over-refusal evaluation tool

A local pipeline that measures how often small LLMs refuse to help on legal
texts. It runs entirely on your own machine, on your own cases.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Install [Ollama](https://ollama.com) (>= 0.18) and pull the local models listed
in `models.yaml`:

```bash
ollama pull llama3.1:8b
ollama pull qwen2.5:7b
ollama pull gemma3:4b
ollama pull hf.co/bartowski/swiss-ai_Apertus-8B-Instruct-2509-GGUF:Q4_K_M
```

`models.yaml` is the single source of truth for which models run — pull whatever
it lists.

## Check the install

First reflex — an offline smoke test. No API key, no model server, no network;
it must print `PASS`:

```bash
python tests/smoke_test.py
```

## Run on your own cases

Copy the template and fill one row per case (see `data/INPUT_FORMAT.md` for the
column contract):

```bash
cp data/sample_TF.csv data/tf_cases.csv
# edit data/tf_cases.csv
```

Run a baseline, then the same cases with an authority prefix:

```bash
python run.py --prompts-file data/tf_cases.csv --ollama-only --languages fr de
python run.py --prompts-file data/tf_cases.csv --ollama-only --languages fr de --prefix supreme-court
```

## Add your own model

Append one entry to `models.yaml` — no code change. A local Ollama model:

```yaml
- name: "mistral:7b"
  backend: ollama
```

…or an internal OpenAI-compatible endpoint:

```yaml
- name: "tf-internal-llm"
  backend: openai_compatible
  base_url: "https://llm.internal.example/v1/chat/completions"
  api_key_env: TF_LLM_API_KEY    # the key stays in your environment, never in this file
```

## Results & confidentiality

Each run writes a CSV under `results/` (created on first run), one row per model
response with a refusal flag. Your documents never leave the machine — only
these local result files are produced.

## More

- `data/INPUT_FORMAT.md` — the input CSV contract (required/optional columns).
- `docs/ARCHITECTURE_DSR.md` — module map and design-science positioning.
