# Architecture & Design-Science Positioning

*For the DSR evaluators and the Federal Tribunal IT team.*

## 1. Purpose

This artifact is a **model- and dataset-agnostic pipeline that measures the
over-refusal behavior of LLMs on legal tasks**. Given a set of cases (a CSV of
legal/benchmark prompts in one to four languages) and a set of models declared
in `models.yaml`, it runs each case — optionally framed with an authority/role
prefix — through every model, classifies each response as a refusal or an
answer, and writes per-response results to `results/`. It targets two audiences:
researchers measuring refusal bias, and an institution (the Swiss Federal
Tribunal) that wants to run the same evaluation on its own confidential cases,
on-premises, with its own models.

## 2. Separation of concerns (HELM-aligned)

The artifact instances the **scenario / adapter / metric** separation of
concerns from HELM (Liang et al., 2023). This is an **analogy of design**, not a
use of HELM's codebase: the mapping below is *conceptual*, and the package is
kept **flat** (8 files, no physical `scenario/` `adapter/` `metric/` folders) on
purpose — for an 8-module package and an IT audience, flat is clearer than a
layered folder tree.

| Conceptual layer (HELM) | Module(s) in this artifact | Role |
|---|---|---|
| **Scenario** (what is tested) | `prompts.py` + the canonical CSV schema (`data/INPUT_FORMAT.md`) + `TASK_REGISTRY` | loads a case = dataset row + task instruction, in 1–4 languages |
| **Adapter** (how a case becomes a model request) | `prefixes.py` + `roles.yaml` + `apply_prefix` | optionally prepends an authority/role prefix per language; assembles the final prompt |
| **Metric** (scoring) | `detector.py` (keyword first-pass) + `judge.py` (LLM-as-judge, 3-class) | classifies each response as refusal / answer |
| **Model access** (backend-agnostic) | `clients/` + `models.yaml` + `registry.py` | runs the prompt on any Ollama or OpenAI-compatible model declared in `models.yaml` |

Each layer is extended by configuration/data, not code: a new **case set** is a
new CSV with the canonical header; a new **role** is a `roles.yaml` entry; a new
**task** is a `TASK_REGISTRY` entry plus `task_<name>_<lang>` columns; a new
**model** is a `models.yaml` entry.

## 3. Refusal detection (OR-Bench-based)

Scoring is **two-stage**, following OR-Bench (Cui et al., 2025):

1. **Keyword first-pass** (`detector.py`): a fast, reproducible, language-aware
   scan of the response opening for refusal phrases (EN/FR/DE/IT).
2. **LLM-as-judge** (`judge.py`): the verbatim OR-Bench **3-class taxonomy** —
   `direct_answer` / `direct_refusal` / `indirect_refusal` — where both refusal
   classes count as a rejection.

**Where we extend OR-Bench (deliberate design choice).** OR-Bench's
*response-stage* detection pairs keyword matching with a **single GPT-4 judge**
using the 3-class taxonomy; its **3-model majority-vote ensemble**
(GPT-4-turbo + Llama-3-70b + Gemini-1.5-pro) is used for **prompt moderation
during dataset construction**, not for scoring responses. Our `judge.py` instead
runs a **heterogeneous majority-vote ensemble on the responses themselves**.
This is *our own extension*, inspired by OR-Bench's moderation-stage ensemble
philosophy and motivated by robustness: a single judge can be idiosyncratic on
borderline legal phrasings, so we require agreement across heterogeneous judges
(an odd number, to avoid ties). The taxonomy and the keyword method are
OR-Bench's; the response-stage ensemble is ours.

## 4. Evaluation approach (DSR)

We evaluate the artifact at two distinct granularities (we say **output-level**
vs **artifact-level**, deliberately avoiding "Level 1/2", which Gregor & Hevner
(2013) reserve for contribution-abstraction levels — and this artifact is itself
their Level 1 *situated implementation*):

- **Output-level** — running the pipeline on real cases and measuring LLM
  refusal behavior (the experiments in the paper). In our reading of Peffers et
  al. (2007), this is **Demonstration** (activity 4: the artifact solves
  instances of the problem).
- **Artifact-level** — assessing the pipeline's own quality against its design
  objectives: usability for the TF, extensibility (new model/role/task/case by
  config), and detector/judge fidelity. In our reading of Peffers et al. (2007),
  this is **Evaluation** (activity 5). *This Peffers mapping is our
  interpretation, not a quotation.*

The artifact-level evaluation follows the **Technical Risk & Efficacy** strategy
of FEDS (Venable et al., 2016), which legitimately emphasizes *artificial,
criteria-based* evaluation (here, a small structured expert evaluation) when the
artifact's dominant risks are technical rather than social — which is our case.
This is why a large survey or field study is not required to evaluate the
artifact itself.

In Gregor & Hevner's (2013) terms, the knowledge contribution is best read as
**Exaptation**: transferring a known evaluation architecture (HELM-style
separation of concerns; OR-Bench's refusal-detection method) into a new domain —
multilingual Swiss legal text.

## References

- Liang, P., Bommasani, R., Lee, T., et al. (2023). *Holistic Evaluation of Language Models.* TMLR. arXiv:2211.09110.
- Cui, J., Chiang, W.-L., Stoica, I., & Hsieh, C.-J. (2025). *OR-Bench: An Over-Refusal Benchmark for Large Language Models.* ICML 2025 (PMLR Vol. 267). arXiv:2405.20947.
- Hevner, A. R., March, S. T., Park, J., & Ram, S. (2004). *Design Science in Information Systems Research.* MIS Quarterly, 28(1), 75–105.
- Peffers, K., Tuunanen, T., Rothenberger, M. A., & Chatterjee, S. (2007). *A Design Science Research Methodology for Information Systems Research.* JMIS, 24(3), 45–77.
- Gregor, S., & Hevner, A. R. (2013). *Positioning and Presenting Design Science Research for Maximum Impact.* MIS Quarterly, 37(2), 337–355.
- Venable, J., Pries-Heje, J., & Baskerville, R. (2016). *FEDS: A Framework for Evaluation in Design Science Research.* EJIS, 25(1), 77–89.
