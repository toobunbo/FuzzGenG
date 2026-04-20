# Stage 1: Oracle Reasoner — Implementation Plan

## Mục tiêu

Nhận `findings.json` + context CSVs → gọi LLM qua LiteLLM → sinh ra `oracle_spec.json`
mô tả oracle để dùng trong Stage 2.

---

## Cấu trúc thư mục

```
FuzzGen/
├── stage1/
│   ├── __init__.py
│   ├── oracle_reasoner.py      # pipeline chính
│   ├── csv_loader.py           # load signatures + functions CSV
│   ├── signature_builder.py    # build function_signature & input_strategy
│   ├── prompt_builder.py       # render system + user prompt
│   └── llm_client.py           # LiteLLM wrapper
├── prompts/
│   ├── stage1_system.txt       # system prompt (static)
│   └── stage1_user.txt         # user prompt template
├── config/
│   └── stage1_config.yaml      # model, temperature, paths
└── run_stage1.py               # CLI: python run_stage1.py --finding <path>
```

---

## Config (`config/stage1_config.yaml`)

```yaml
model: "ollama/qwen3-coder-flash"   # LiteLLM model identifier

temperature: 0.2
max_tokens: 1024
timeout: 60

prompts_dir: "prompts"

signatures_csv: "output/{lang}/{repo}/context/signatures_function.csv"
functions_csv:  "output/{lang}/{repo}/context/functions.csv"

oracle_spec_out: "output/{lang}/{repo}/verifycation_result/oracle_spec.json"
```

---

## Prompt Files

### `prompts/stage1_system.txt`

```
You are a fuzzing oracle designer for Python security vulnerabilities.

## Task
Given a verified security finding, design an oracle that detects the
vulnerability at runtime during Atheris fuzzing. Output oracle_spec JSON only.

## What to Reason From

Use the finding fields in this order of priority:
  1. rule_id   → you know the vulnerability class; determine what "bad behavior"
                 looks like at runtime for this specific rule
  2. message   → CodeQL's own sink/source description (most precise)
  3. answers   → data flow already traced:
                   [0] tainted source & param name
                   [1] full data flow path to sink
                   [2] what validation is absent
                   [3] sink description
                   [4] concrete attack scenario
  4. reasoning → attack narrative for context

## How to Choose Oracle Strategy

Ask yourself:
  A. Where does the vulnerability MANIFEST at runtime?
     - In the return value?     → inspect_return
     - In a side-effect call?   → patch_call (redirect, log, db, eval, open...)
     - In an exception raised?  → catch_exception

  B. What is the MINIMAL observable signal confirming exploitation?
     - Tainted input appears unescaped in output/call?
     - Dangerous pattern survives sanitization?
     - Unexpected call is made with tainted data?

  C. Is any patching needed, or can I just inspect the return value?
     Choose the SIMPLEST strategy that reliably detects the rule.

## Input Strategy (provided)
  - "direct_params" → function has explicit params; fuzz input maps to params
  - "flask_view"    → class method reading request.args/json/form;
                       fuzz input injected via test_request_context

## Output Format

Output ONLY valid JSON, no markdown, no prose:

{
  "oracle_type": "<UPPER_SNAKE_CASE>",
  "attack_scenario": "<one sentence>",
  "tainted_params": [
    {
      "name": "<param name from answers[0]>",
      "index": <0-based int, -1 if flask_view>,
      "type": "<type from signature>"
    }
  ],
  "monitor": {
    "strategy": "<inspect_return | patch_call | catch_exception>",
    "patch_target": "<fully.qualified.name if patch_call, else null>",
    "capture_what": "<what to capture or inspect>",
    "additional_imports": ["<module if needed>"]
  },
  "oracle_check": {
    "condition_description": "<human-readable trigger condition>",
    "trigger_patterns": ["<patterns if applicable, else []>"],
    "raise_type": "RuntimeError",
    "raise_message_template": "<ORACLE_TYPE: short description>"
  },
  "expected_exceptions": ["<ExceptionClass>"],
  "cleanup_needed": <true|false>,
  "cleanup_description": "<what to restore, or null>"
}
```

### `prompts/stage1_user.txt`

```
## Security Finding

{finding_json}

## Target Function Signature

{function_signature}

## Input Strategy: {input_strategy}

Produce oracle_spec JSON only.
```

---

## Module chi tiết

### `stage1/csv_loader.py`

```python
import csv
from typing import NamedTuple

class SigRow(NamedTuple):
    name: str; file: str
    start_line: int; end_line: int
    param_name: str; param_type: str

class FuncRow(NamedTuple):
    name: str; file: str
    start_line: int; end_line: int
    scope: str

def load_signatures(path: str) -> list[SigRow]:
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(SigRow(
                name=r["name"], file=r["file"],
                start_line=int(r["start_line"]), end_line=int(r["end_line"]),
                param_name=r["param_name"], param_type=r.get("param_type", ""),
            ))
    return rows

def load_functions(path: str) -> list[FuncRow]:
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(FuncRow(
                name=r["name"], file=r["file"],
                start_line=int(r["start_line"]), end_line=int(r["end_line"]),
                scope=r.get("scope", ""),
            ))
    return rows
```

---

### `stage1/signature_builder.py`

```python
from .csv_loader import SigRow, FuncRow

def build_signature(function_name: str, file: str, signatures: list[SigRow]) -> str:
    params = [r for r in signatures
              if r.name == function_name and r.file == file
              and r.param_name not in ("self", "cls")]
    if not params:
        return f"def {function_name}(self)"
    parts = [f"{r.param_name}: {r.param_type}" if r.param_type
             else r.param_name for r in params]
    return f"def {function_name}({', '.join(parts)})"

def get_input_strategy(function_name: str, file: str,
                        signatures: list[SigRow], functions: list[FuncRow]) -> str:
    has_params = any(r for r in signatures
                     if r.name == function_name and r.file == file
                     and r.param_name not in ("self", "cls"))
    if has_params:
        return "direct_params"
    func = next((r for r in functions
                 if r.name == function_name and r.file == file), None)
    if func and "Class" in func.scope:
        return "flask_view"
    return "direct_params"
```

---

### `stage1/prompt_builder.py`

```python
import json
from pathlib import Path

def load_system_prompt(prompts_dir: str) -> str:
    return Path(prompts_dir, "stage1_system.txt").read_text(encoding="utf-8")

def build_user_prompt(finding: dict, function_signature: str,
                       input_strategy: str, prompts_dir: str) -> str:
    template = Path(prompts_dir, "stage1_user.txt").read_text(encoding="utf-8")
    return template.format(
        finding_json       = json.dumps(finding, indent=2, ensure_ascii=False),
        function_signature = function_signature,
        input_strategy     = input_strategy,
    )
```

---

### `stage1/llm_client.py`

```python
import json, re
from litellm import completion

def call_llm(system_prompt: str, user_prompt: str, model: str,
             temperature: float = 0.2, max_tokens: int = 1024, timeout: int = 60) -> str:
    response = completion(
        model=model,
        messages=[{"role": "system", "content": system_prompt},
                  {"role": "user",   "content": user_prompt}],
        temperature=temperature, max_tokens=max_tokens, timeout=timeout,
    )
    return response.choices[0].message.content

def parse_oracle_spec(raw_text: str) -> dict:
    text = raw_text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if fence:
        text = fence.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM output not valid JSON:\n{raw_text}\n\nError: {e}")

def validate_oracle_spec(spec: dict) -> None:
    required = ["oracle_type", "tainted_params", "monitor",
                "oracle_check", "expected_exceptions"]
    missing = [f for f in required if f not in spec]
    if missing:
        raise ValueError(f"oracle_spec missing fields: {missing}")
```

---

### `stage1/oracle_reasoner.py`

```python
import json, yaml
from pathlib import Path
from .csv_loader        import load_signatures, load_functions
from .signature_builder import build_signature, get_input_strategy
from .prompt_builder    import load_system_prompt, build_user_prompt
from .llm_client        import call_llm, parse_oracle_spec, validate_oracle_spec

def run(finding_path: str, config_path: str = "config/stage1_config.yaml") -> dict:
    config       = yaml.safe_load(Path(config_path).read_text())
    finding_full = json.loads(Path(finding_path).read_text(encoding="utf-8"))
    f     = finding_full["finding"]
    repo  = f["repo_name"]; lang = f["lang"]
    func  = f["function_name"]; file_ = f["file"]

    sigs  = load_signatures(config["signatures_csv"].format(lang=lang, repo=repo))
    funcs = load_functions(config["functions_csv"].format(lang=lang, repo=repo))

    sig      = build_signature(func, file_, sigs)
    strategy = get_input_strategy(func, file_, sigs, funcs)
    print(f"[Stage1] function  : {func}")
    print(f"[Stage1] signature : {sig}")
    print(f"[Stage1] strategy  : {strategy}")

    sys_p  = load_system_prompt(config["prompts_dir"])
    user_p = build_user_prompt(finding_full, sig, strategy, config["prompts_dir"])

    print(f"[Stage1] calling   : {config['model']} ...")
    raw  = call_llm(sys_p, user_p, config["model"],
                    config["temperature"], config["max_tokens"], config["timeout"])
    spec = parse_oracle_spec(raw)
    validate_oracle_spec(spec)

    spec["_meta"] = {
        "function": func, "file": file_,
        "input_strategy": strategy, "function_signature": sig,
        "model": config["model"],
    }
    out = Path(config["oracle_spec_out"].format(lang=lang, repo=repo))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(spec, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[Stage1] output    : {out}")
    return spec
```

---

### `run_stage1.py`

```python
#!/usr/bin/env python3
import argparse, json
from stage1.oracle_reasoner import run

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FuzzGen Stage 1: Oracle Reasoner")
    parser.add_argument("--finding", required=True)
    parser.add_argument("--config",  default="config/stage1_config.yaml")
    args = parser.parse_args()
    spec = run(args.finding, args.config)
    print("\n[Stage1] oracle_spec:")
    print(json.dumps(spec, indent=2, ensure_ascii=False))
```

---

## Output Location

```
output/{lang}/{repo}/verifycation_result/oracle_spec.json
```

Cùng thư mục với `findings.json` → Stage 2 chain trực tiếp không cần config thêm.

---

## Checklist triển khai

- [ ] `stage1/__init__.py` (rỗng)
- [ ] `stage1/csv_loader.py`
- [ ] `stage1/signature_builder.py`
- [ ] `stage1/prompt_builder.py`
- [ ] `stage1/llm_client.py`
- [ ] `stage1/oracle_reasoner.py`
- [ ] `prompts/stage1_system.txt`
- [ ] `prompts/stage1_user.txt`
- [ ] `config/stage1_config.yaml`
- [ ] `run_stage1.py`
- [ ] Test: `py/bad-tag-filter` → `sanitize_svg_content` (direct_params)
- [ ] Test: `py/url-redirection` → `warm_up_cache` (flask_view)
- [ ] Validate `oracle_spec.json` đúng schema

---

## Chạy thử

```bash
cd /home/caterpie/FuzzGen

/home/caterpie/ProjectFzz/VulnHunterX-main/.venv/bin/python \
  run_stage1.py \
  --finding output/python/superset/verifycation_result/findings.json \
  --config  config/stage1_config.yaml
```

---

## Notes

> **JSON fence stripping**: `parse_oracle_spec` tự strip markdown fences trước
> `json.loads()`. Nhiều model vẫn bọc output trong triple-backticks.

> **temperature: 0.2**: Giữ thấp để oracle_spec deterministic, tránh LLM
> hallucinate check condition không match rule_id.

> **validate_oracle_spec**: Fail fast tại Stage 1 nếu thiếu field.
> Không để Stage 2 nhận input lỗi và sinh harness sai im lặng.

> **`_meta` field**: Stage 2 đọc `_meta.function_signature` và
> `_meta.input_strategy` trực tiếp mà không cần đọc lại CSVs.
