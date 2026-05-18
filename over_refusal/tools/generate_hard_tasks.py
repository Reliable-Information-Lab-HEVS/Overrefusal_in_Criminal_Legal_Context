"""Auto-generate task_hard_* columns for the BGer prompts CSV.

For each row that does NOT already have task_hard_fr filled in, this script
sends the case facts to an LLM with the standardised methodology prompt
(see over_refusal/data/task_hard_generator_prompt.txt) and stores the
4-language JSON output in task_hard_fr / task_hard_de / task_hard_it /
task_hard_en.

This is the reproducible procedure: one prompt template, one LLM, one output
schema per case. Anyone re-running this script on the same CSV with the same
prompt and LLM will get equivalent hard tasks (LLMs sample, so not literally
identical, but methodologically the same).

Usage examples:
  # Test the rendered prompt without calling the LLM
  python -m over_refusal.tools.generate_hard_tasks --dry-run

  # Generate using GPT-4.1 (recommended, see README)
  python -m over_refusal.tools.generate_hard_tasks --model gpt

  # Try with Claude on the first 3 rows only
  python -m over_refusal.tools.generate_hard_tasks --model claude --limit 3

  # Force regeneration even when task_hard_* are already filled
  python -m over_refusal.tools.generate_hard_tasks --model gpt --overwrite

  # Write the output to a different file (does not modify the input)
  python -m over_refusal.tools.generate_hard_tasks --model gpt \
      --output data/bger_with_hard_gpt.csv
"""

import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path
from typing import Dict, Optional

from over_refusal.clients import ClaudeClient, GeminiClient, OpenAIClient
from over_refusal.config import (
    CLAUDE_DEFAULT_MODEL,
    GEMINI_DEFAULT_MODEL,
    OPENAI_DEFAULT_MODEL,
    PROJECT_ROOT,
)


# Path to the methodology prompt template. The script just substitutes the
# placeholders {{or_category}}, {{bger_source}}, {{text_original}}.
PROMPT_TEMPLATE_FILE = (
    Path(__file__).resolve().parent.parent / "data" / "task_hard_generator_prompt.txt"
)

# Keys we expect in the LLM's JSON output, in this exact order.
EXPECTED_KEYS = ["task_hard_fr", "task_hard_de", "task_hard_it", "task_hard_en"]

# Available backends; "gpt" is the default for reasons explained in the README.
BACKENDS = {
    "gpt": (OpenAIClient, OPENAI_DEFAULT_MODEL),
    "claude": (ClaudeClient, CLAUDE_DEFAULT_MODEL),
    "gemini": (GeminiClient, GEMINI_DEFAULT_MODEL),
}

# Be polite to the API between calls
SLEEP_BETWEEN_CALLS = 0.5


def load_template() -> str:
    """Read the methodology prompt from disk."""
    if not PROMPT_TEMPLATE_FILE.exists():
        raise FileNotFoundError(
            f"Methodology prompt not found: {PROMPT_TEMPLATE_FILE}\n"
            f"Place the prompt template at this path before running the script."
        )
    return PROMPT_TEMPLATE_FILE.read_text(encoding="utf-8")


def pick_original_text(row: Dict[str, str]) -> str:
    """Return the most informative facts text for this row.

    Priority: orginal_language column, then fr/de/it/en in that order.
    """
    orig = (row.get("orginal_language") or "").strip().lower()
    if orig and row.get(f"text_{orig}"):
        return row[f"text_{orig}"]
    for lang in ("fr", "de", "it", "en"):
        if row.get(f"text_{lang}"):
            return row[f"text_{lang}"]
    return ""


def render_prompt(template: str, row: Dict[str, str]) -> str:
    """Substitute the placeholders in the template with this row's values."""
    return (
        template.replace("{{or_category}}", row.get("or_category", ""))
                .replace("{{bger_source}}", row.get("bger_source", ""))
                .replace("{{text_original}}", pick_original_text(row))
    )


# Greedy regex: match from the first '{' to the LAST '}'. Required because
# the JSON values may themselves contain '}' characters in legal prose.
_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def _strip_code_fences(text: str) -> str:
    """Remove any markdown code fences around the response."""
    cleaned = text.strip()
    # Remove a leading ```json or ``` line if present
    cleaned = re.sub(r"^```[a-zA-Z]*\s*\n?", "", cleaned)
    # Remove a trailing ``` if present
    cleaned = re.sub(r"\n?```\s*$", "", cleaned)
    return cleaned.strip()


def parse_response(raw: str) -> Optional[Dict[str, str]]:
    """Extract and validate the JSON payload returned by the LLM.

    Returns the dict {task_hard_fr, task_hard_de, task_hard_it, task_hard_en}
    or None if parsing or validation fails.
    """
    if not raw or raw.startswith("[ERROR]"):
        return None

    cleaned = _strip_code_fences(raw)

    # First try to parse the whole cleaned string as JSON
    parsed = None
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        # Fall back: extract the largest {...} block in the response
        match = _JSON_BLOCK.search(cleaned)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None

    if not isinstance(parsed, dict):
        return None

    # All four keys must be present, be strings, and be non-empty
    for k in EXPECTED_KEYS:
        v = parsed.get(k)
        if not isinstance(v, str) or not v.strip():
            return None

    return {k: parsed[k].strip() for k in EXPECTED_KEYS}


def needs_generation(row: Dict[str, str], overwrite: bool) -> bool:
    """Decide whether this row needs to be (re)generated."""
    if overwrite:
        return True
    return not all((row.get(k) or "").strip() for k in EXPECTED_KEYS)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate task_hard_* columns for a BGer prompts CSV "
                    "using a standardised methodology prompt."
    )
    parser.add_argument(
        "--csv",
        default=str(PROJECT_ROOT / "data" / "bger_sample_0421_translated.csv"),
        help="Path to the prompts CSV (default: data/bger_sample_0421_translated.csv)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output CSV path. If omitted, the input CSV is overwritten in place.",
    )
    parser.add_argument(
        "--model",
        choices=list(BACKENDS),
        default="gpt",
        help="Which backend to use (default: gpt)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process the first N rows that need generation",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Regenerate task_hard_* even when already filled",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the rendered prompt for the first eligible row and exit",
    )
    args = parser.parse_args()

    template = load_template()
    csv_path = Path(args.csv)
    if not csv_path.exists():
        sys.exit(f"CSV not found: {csv_path}")

    # 1. Read the CSV
    with open(csv_path, "r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
        base_fields = list(reader.fieldnames or [])

    # 2. Make sure task_hard_* columns exist in the schema, and put each
    #    task_hard_<lang> right after the matching task_<lang>.
    for k in EXPECTED_KEYS:
        if k not in base_fields:
            lang = k.split("_")[-1]
            sibling = f"task_{lang}"
            if sibling in base_fields:
                base_fields.insert(base_fields.index(sibling) + 1, k)
            else:
                base_fields.append(k)

    # 3. Dry run: render the first eligible prompt and exit
    if args.dry_run:
        target = next((r for r in rows if needs_generation(r, args.overwrite)), None)
        if target is None:
            print("Nothing to generate (all rows already filled). "
                  "Use --overwrite to force.")
            return
        print(render_prompt(template, target))
        return

    # 4. Build the LLM client
    client_cls, default_model = BACKENDS[args.model]
    client = client_cls()
    model_name = default_model
    print(f"Using {args.model} ({model_name}) as generator.")

    # 5. Process rows one by one
    processed = 0
    failures = 0
    for i, row in enumerate(rows, 1):
        if not needs_generation(row, args.overwrite):
            continue
        if args.limit is not None and processed >= args.limit:
            break

        prompt = render_prompt(template, row)
        print(f"[{i}] {row.get('prompt_id','?')} ({row.get('or_category','?')})...",
              end=" ", flush=True)

        raw = client.query(prompt, model_name)
        parsed = parse_response(raw)

        if parsed is None:
            failures += 1
            print("FAIL")
            print(f"    raw output (first 300 chars): {raw[:300]!r}")
            continue

        for k, v in parsed.items():
            row[k] = v
        processed += 1
        print("OK")
        time.sleep(SLEEP_BETWEEN_CALLS)

    # 6. Write back the CSV
    out_path = Path(args.output) if args.output else csv_path
    with open(out_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=base_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nDone. Processed: {processed}, failures: {failures}. Wrote: {out_path}")


if __name__ == "__main__":
    main()
