# FuzzGen — AI-Powered Fuzzing Harness Generator

FuzzGen is an **LLM-driven pipeline** that automatically generates [Atheris](https://github.com/google/atheris) fuzzing harnesses from CodeQL security findings. It combines static analysis context with LLM reasoning to produce executable Python harnesses that can detect vulnerabilities at runtime.

Part of the **XXXXXXXXXXX** security research project.

---

## How It Works

```
CodeQL Findings
      │
      ▼
┌─────────────────────┐
│  Stage 1            │  LLM reasons about the vulnerability,
│  Oracle Reasoner    │  selects detection strategy, derives
│                     │  oracle patterns → oracle_spec.json
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Stage 2            │  Jinja2 pre-fills deterministic skeleton,
│  Harness Generator  │  LLM fills TestOneInput body
│                     │  → harness_<rule_id>.py
└──────────┬──────────┘
           │
           ▼
    Atheris Fuzzer
    (coverage-guided runtime)
```

**Stage 3** (coverage-guided refinement loop) is planned — see [`docs/plan/stage3_design.md`](docs/plan/stage3_design.md).

---

## Prerequisites

- Python **3.10** or **3.11** (required for Atheris compatibility with target libraries)
- An LLM provider (Ollama local, OpenAI, Google Gemini, Anthropic, etc.)

```bash
pip install atheris litellm jinja2 pyyaml python-dotenv
```

---

## Configuration

### LLM Provider (`.env`)

Create a `.env` file at the project root. FuzzGen uses [LiteLLM](https://github.com/BerriAI/litellm) so any supported provider works.

```properties
# Ollama (local)
LLM_PROVIDER=ollama
LLM_MODEL=deepseek-r1:7b

# Google Gemini
LLM_PROVIDER=gemini
LLM_MODEL=gemini-2.5-pro-preview-03-25
GEMINI_API_KEY=your_api_key_here

# Anthropic Claude
LLM_PROVIDER=anthropic
LLM_MODEL=claude-sonnet-4-5
ANTHROPIC_API_KEY=your_api_key_here

# OpenAI
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o
OPENAI_API_KEY=your_api_key_here
```

If `LLM_PROVIDER`/`LLM_MODEL` are set, they override the `model` field in the YAML configs.

### Stage Configs

| File | Description |
|---|---|
| `src/config/stage1_config.yaml` | Model, temperature, CSV paths, oracle_spec output path |
| `src/config/stage2_config.yaml` | Model, temperature, harness output path, repo root |

Default model in both configs: `ollama/deepseek-r1:7b`.

---

## Input Data Layout

The framework expects CodeQL output to be organized as:

```
output/
└── {lang}/
    └── {repo}/
        ├── context/
        │   ├── signatures_function.csv   # Function parameter signatures
        │   └── functions.csv             # Function scope metadata
        └── verification_result/
            └── findings.json             # CodeQL finding to analyze
```

### `findings.json` format

```json
{
  "finding": {
    "repo_name": "superset",
    "lang": "python",
    "rule_id": "py/ssrf",
    "function_name": "warm_up_cache",
    "file": "superset/views/utils.py",
    "message": "...",
    "answers": [
      "tainted source & param name",
      "full data flow path to sink",
      "what validation is absent",
      "sink description",
      "concrete attack scenario"
    ]
  }
}
```

### `signatures_function.csv` format

```csv
name,file,start_line,end_line,param_name,param_type
sanitize_svg_content,superset/utils/core.py,124,142,svg_content,str
```

### `functions.csv` format

```csv
name,file,start_line,end_line,scope
warm_up_cache,superset/views/utils.py,210,235,Class:CacheWarmUpView
```

The repo source must be present at `repos/{lang}/{repo}/` (path referenced in `stage2_config.yaml`).

---

## Running the Pipeline

All commands run from the **project root** (`/path/to/FuzzGen`).

### Step 1 — Oracle Reasoner

```bash
python src/run_stage1.py \
  --finding output/python/superset/verification_result/findings.json

# With debug log
python src/run_stage1.py \
  --finding output/python/superset/verifycation_result/findings.json \
  --log-file stage1_debug.log
```

Output: `output/python/superset/verification_result/oracle_spec.json`

### Step 2 — Harness Generator

```bash
python src/run_stage2.py \
  --finding output/python/superset/verification_result/findings.json \
  --spec    output/python/superset/verification_result/oracle_spec.json

# With debug log
python src/run_stage2.py \
  --finding output/python/superset/verifycation_result/findings.json \
  --spec    output/python/superset/verifycation_result/oracle_spec.json \
  --log-file stage2_debug.log
```

Output: `output/python/superset/verification/harness_py_ssrf.py`

### Step 3 — Run Atheris

```bash
# Install target library's dependencies first
export PYTHONPATH="/path/to/FuzzGen/repos/python/superset:$PYTHONPATH"
cd repos/python/superset && pip install -r requirements.txt && cd -

# Run fuzzer
mkdir -p corpus/
python output/python/superset/verification/harness_py_ssrf.py \
  corpus/ \
  -max_total_time=300

# Or with fixed run count
python output/python/superset/verification/harness_py_ssrf.py \
  corpus/ \
  -runs=50000
```

When the oracle fires, Atheris will print `RuntimeError` and write a crash file (`crash-xxxxxxxx`) to the working directory.

---

## Supported Strategies

### Input Strategies (Stage 1 detection, Stage 2 harness wiring)

| Strategy | Description | Status |
|---|---|---|
| `direct_params` | Function has explicit parameters; fuzz data maps directly to params | ✅ Supported |
| `flask_view` | Class method reading `request.args` / `request.json` / `request.form`; fuzz data injected via Flask test request context | ✅ Supported |
| `stdin` | Function reads from `sys.stdin` | ⚠️ Detected, harness logic not specialized |
| `env` | Function reads from `os.environ` | ⚠️ Detected, harness logic not specialized |

Detection is done via AST analysis of the function body (`signature_builder.py`). For `stdin` and `env`, the framework falls back to `direct_params` harness wiring.

### Monitor Strategies (Oracle types)

| Strategy | Description | Status |
|---|---|---|
| `inspect_return` | Inspect the return value of the target function; oracle fires if trigger patterns survive sanitization | ✅ Supported |
| `patch_call` | Mock a downstream sink (e.g., `httpx.get`, `cursor.execute`); oracle fires if tainted data reaches the sink argument | ✅ Supported |
| `catch_exception` | Oracle fires if an unexpected exception is raised (or expected one is not raised) | ⚠️ Schema defined, Stage 2 harness skeleton not specialized |

---

## Known Limitations

### Input Handling
- **`stdin` / `env` strategies**: The framework correctly detects when a function reads from `sys.stdin` or `os.environ`, but the generated harness does not inject fuzz data through those channels. The LLM falls back to direct parameter injection, which may miss the actual data flow.

### Oracle Coverage
- **`catch_exception` strategy**: The `oracle_spec.json` schema includes this strategy and Stage 1 will reason about it correctly, but Stage 2 does not select a specialized system prompt for it (falls back to `inspect_return` prompt). Generated harnesses may not implement exception-based oracles correctly.

### Harness Validation
- **One-shot generation**: Stage 2 generates a harness and validates syntax (`py_compile`) but does not execute it. Runtime errors (e.g., `ImportError`, wrong function call signature) are only discovered when you run Atheris manually.
- **No repair loop**: If the generated harness fails at runtime, you must re-run Stage 2 or fix manually. Stage 3 (planned) addresses this with a coverage-guided refinement loop.

### Context Limitations
- **No function body in Stage 1 prompt**: LLM reasons from the function signature only. For complex functions with non-obvious preconditions, oracle pattern derivation may be less accurate.
- **No call graph**: Framework does not trace callers or callees beyond the target function. Vulnerabilities that require specific caller state may produce incomplete harnesses.

### Coverage
- **No coverage measurement post-generation**: The framework does not verify whether generated harnesses actually reach the vulnerable code path. Stage 3 (planned) adds coverage measurement via `coverage.py` and a 3-attempt LLM refinement loop.

---

## Output Structure

```
output/
└── python/
    └── {repo}/
        └── verification_result/
            ├── findings.json
            └── oracle_spec.json     ← Stage 1 output
output/
└── python/
    └── {repo}/
        └── verification/
            ├── harness_{rule_id}.py  ← Stage 2 output
            └── corpus/
                └── {rule_id}/        ← Seed corpus (if fuzz_guidance provided)
                    ├── seed_000
                    └── seed_001
```

---

## Project Structure

```
FuzzGen/
├── src/
│   ├── stage1/
│   │   ├── oracle_reasoner.py     # Stage 1 pipeline
│   │   ├── csv_loader.py          # Load CodeQL CSV context
│   │   ├── signature_builder.py   # Build signature + detect input strategy (AST)
│   │   ├── prompt_builder.py      # Render system/user prompts
│   │   └── llm_client.py          # LiteLLM wrapper + JSON parsing
│   ├── stage2/
│   │   ├── harness_generator.py   # Stage 2 pipeline
│   │   ├── template_builder.py    # Jinja2 skeleton pre-fill
│   │   ├── import_resolver.py     # file path → import statement
│   │   ├── llm_client.py          # LiteLLM wrapper + code extraction
│   │   └── templates/
│   │       └── base_harness.j2    # Atheris harness template
│   ├── prompts/
│   │   ├── stage1_system.txt      # Oracle reasoning prompt
│   │   ├── stage1_user.txt        # User prompt template
│   │   ├── stage2_system_inspectreturn.txt
│   │   ├── stage2_system_patchcall.txt
│   │   └── stage2_user.txt
│   ├── config/
│   │   ├── stage1_config.yaml
│   │   └── stage2_config.yaml
│   ├── run_stage1.py              # CLI entry point — Stage 1
│   └── run_stage2.py              # CLI entry point — Stage 2
├── output/                        # Generated artifacts
├── repos/                         # Target repository source code
├── docs/
│   ├── introduction.md
│   ├── stage1_implement.md
│   ├── stage2_implement.md
│   └── plan/
│       └── stage3_design.md       # Planned: coverage-guided refinement
└── .env                           # LLM provider configuration
```

---

## Roadmap

| Stage | Status | Description |
|---|---|---|
| Stage 1 — Oracle Reasoner | ✅ Implemented | LLM-driven oracle spec generation from CodeQL findings |
| Stage 2 — Harness Generator | ✅ Implemented | Skeleton-based harness synthesis with LLM body completion |
| Stage 3 — Coverage Refinement | 🔲 Planned | Coverage measurement + LLM repair loop (max 3 attempts) |

---

## References

- [Atheris Python Fuzzer](https://github.com/google/atheris) — Google's coverage-guided Python fuzzer built on LibFuzzer
- [LiteLLM](https://github.com/BerriAI/litellm) — Unified LLM provider interface
- [OSS-Fuzz-Gen](https://github.com/google/oss-fuzz-gen) — LLM-based fuzz target generation for OSS-Fuzz
- [CoverUp (2024)](https://arxiv.org/abs/2403.23930) — Coverage-guided LLM test generation with on-demand context retrieval
- [HarnessAgent (2025)](https://arxiv.org/abs/2506.00348) — Tool-augmented agentic harness construction framework
