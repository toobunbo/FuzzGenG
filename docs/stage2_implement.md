# Stage 2: Fuzzing Harness Generator — Implementation Plan

## Mục tiêu
Nhận `findings.json` + `oracle_spec.json` (output của Stage 1) →
pre-fill template skeleton → gọi LLM → sinh ra `harness_<rule_id>.py`
chạy trực tiếp bằng Atheris.

---

## Cấu trúc thư mục

```
FuzzGen/
├── stage2/
│   ├── __init__.py
│   ├── harness_generator.py     # pipeline chính (orchestrator)
│   ├── template_builder.py      # pre-fill skeleton trước khi đưa LLM
│   ├── import_resolver.py       # file path → import statement
│   └── llm_client.py            # LiteLLM wrapper (extract code block)
├── prompts/
│   ├── stage2_system.txt        # system prompt (static)
│   └── stage2_user.txt          # user prompt template (nhận pre-filled skeleton)
├── config/
│   └── stage2_config.yaml
└── run_stage2.py                # CLI: python run_stage2.py --finding <path> --spec <path>
```

---

## Config (`config/stage2_config.yaml`)

```yaml
model: "ollama/qwen3-coder-flash"
temperature: 0.2
max_tokens: 2048
timeout: 120
prompts_dir: "prompts"
harness_out: "output/{lang}/{repo}/verification/harness_{rule_id}.py"
repo_root: "/home/caterpie/ProjectFzz/VulnHunterX-main/repos/{repo}"
```

---

## Prompt Files

### `prompts/stage2_system.txt`

```
You are an expert fuzzing engineer specializing in Python security testing with Atheris.

## Your Task
You will receive a PARTIAL harness Python script with a skeleton already filled in.
Your job is to complete ONLY the body of the `TestOneInput` function.
Do NOT modify imports, do NOT modify the atheris.Setup/Fuzz lines.
Output the COMPLETE final Python script, no markdown, no prose.

## What is pre-filled for you (do not change)
- All import statements (atheris, re, target function)
- The function signature being fuzzed
- The oracle_spec fields as comments for your reference
- The atheris.Setup() and atheris.Fuzz() calls

## What you must fill in inside TestOneInput()

### 1. FDP Block — Generate fuzz inputs
Use `fdp = atheris.FuzzedDataProvider(data)` (already declared).
Map each tainted_param by type:
  - str   → fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 4096))
  - bytes → fdp.ConsumeBytes(fdp.ConsumeIntInRange(0, 4096))
  - int   → fdp.ConsumeInt(4)
  - float → fdp.ConsumeFloat()
  - bool  → fdp.ConsumeBool()
  - list  → [] or build from fdp based on context
  - dict  → {} or build from fdp based on context
For non-tainted params that the function still requires, use safe/minimal defaults.

### 2. Function Call Block
Call the target function with the generated inputs.
Wrap in try/except per the expected_exceptions list.
If expected_exceptions is empty, use a bare `except Exception: return`
to swallow unexpected crashes and focus only on the oracle.

### 3. Oracle Check Block — Implement per monitor.strategy

#### strategy: inspect_return
  result = <function_call>
  Apply trigger_patterns as regex search on result (re.IGNORECASE).
  If any pattern matches → raise RuntimeError(raise_message_template).

#### strategy: patch_call
  Use unittest.mock.patch as context manager around the function call.
  Capture calls to patch_target.
  After call, inspect call_args for tainted data presence.
  If found → raise RuntimeError(raise_message_template).

#### strategy: catch_exception
  Wrap call in try/except.
  If an UNEXPECTED exception is raised (not in expected_exceptions) → raise RuntimeError.
  If NO exception is raised when one was expected → raise RuntimeError.

## Key Rules
- Never use `atheris.instrument_func` decorator on TestOneInput — it is not needed.
- Always use `with atheris.instrument_imports():` block (already pre-filled).
- If cleanup_needed is true, use try/finally to restore state.
- Keep the harness minimal — no print statements, no logging.
- The oracle RuntimeError must be DISTINCT from normal exceptions so Atheris reports it as a bug.
```

---

### `prompts/stage2_user.txt`

```
Complete the following partial Atheris harness by filling in the TestOneInput body.
Output the complete Python script only. No markdown, no explanation.

{skeleton}
```

---

## Module chi tiết

### `stage2/import_resolver.py`

```python
import os

def resolve_import(file_path: str, function_name: str, repo_root: str) -> str:
    """
    Convert file path + function name → Python import statement.

    Examples:
      "superset/utils/core.py" + "sanitize_svg_content"
      → "from superset.utils.core import sanitize_svg_content"
    """
    # Strip repo_root prefix if present
    rel = file_path
    if repo_root and file_path.startswith(repo_root):
        rel = file_path[len(repo_root):].lstrip(os.sep)

    # Strip .py extension
    module_path = rel.replace(os.sep, "/").removesuffix(".py")

    # Convert to dot notation
    module = module_path.replace("/", ".")

    # Strip trailing __init__
    if module.endswith(".__init__"):
        module = module[: -len(".__init__")]

    return f"from {module} import {function_name}"
```

---

### `stage2/template_builder.py`

```python
import json
from pathlib import Path
from .import_resolver import resolve_import


def build_skeleton(finding: dict, spec: dict, repo_root: str) -> str:
    """
    Pre-fill the harness skeleton with all deterministic information.
    LLM only needs to fill in TestOneInput body.
    """
    f = finding["finding"]
    meta = spec["_meta"]
    monitor = spec["monitor"]
    oracle = spec["oracle_check"]

    rule_id       = f["rule_id"]
    function_name = meta["function"]
    file_path     = meta["file"]
    input_strategy  = meta["input_strategy"]
    monitor_strategy = monitor["strategy"]
    function_signature = meta["function_signature"]

    # --- Resolve import ---
    import_stmt = resolve_import(file_path, function_name, repo_root)

    # --- Additional imports ---
    extra_imports = "\n".join(
        f"import {m}" for m in monitor.get("additional_imports", [])
    )
    if monitor_strategy == "patch_call":
        extra_imports += "\nfrom unittest.mock import patch, MagicMock"

    # --- Oracle spec as comments (LLM reference) ---
    oracle_comment = f"""\
# === ORACLE SPEC ===
# oracle_type      : {spec['oracle_type']}
# input_strategy   : {input_strategy}
# monitor_strategy : {monitor_strategy}
# patch_target     : {monitor.get('patch_target')}
# capture_what     : {monitor.get('capture_what')}
# tainted_params   : {json.dumps(spec['tainted_params'])}
# trigger_patterns : {json.dumps(oracle.get('trigger_patterns', []))}
# expected_exceptions: {json.dumps(spec.get('expected_exceptions', []))}
# raise_message    : {oracle['raise_message_template']}
# cleanup_needed   : {spec.get('cleanup_needed', False)}
# cleanup_desc     : {spec.get('cleanup_description')}
# attack_scenario  : {spec['attack_scenario']}
# function_signature: {function_signature}"""

    skeleton = f"""\
# AUTO-GENERATED ATHERIS HARNESS SKELETON
# rule_id  : {rule_id}
# function : {function_name}
# file     : {file_path}
# ================================================================

import atheris
import sys
import re
{extra_imports}

with atheris.instrument_imports():
    {import_stmt}

{oracle_comment}

def TestOneInput(data):
    fdp = atheris.FuzzedDataProvider(data)

    # [TODO: LLM fills FDP block, function call, and oracle check here]

atheris.Setup(sys.argv, TestOneInput)
atheris.Fuzz()
"""
    return skeleton
```

---

### `stage2/llm_client.py`

```python
import re
from litellm import completion


def call_llm(system_prompt: str, user_prompt: str, model: str,
             temperature: float = 0.2, max_tokens: int = 2048,
             timeout: int = 120) -> str:
    response = completion(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
    )
    return response.choices[0].message.content


def extract_code(raw: str) -> str:
    """Strip markdown fences, return clean Python source."""
    fence = re.search(r"```(?:python)?\s*([\s\S]+?)\s*```", raw)
    if fence:
        return fence.group(1).strip()
    return raw.strip()


def validate_harness(code: str) -> None:
    """Fail fast: syntax check before writing to disk."""
    try:
        compile(code, "<harness>", "exec")
    except SyntaxError as e:
        raise ValueError(f"LLM generated invalid Python:\n{e}\n\n{code}")
```

---

### `stage2/harness_generator.py`

```python
import json
import yaml
from pathlib import Path

from .template_builder import build_skeleton
from .llm_client       import call_llm, extract_code, validate_harness


def run(finding_path: str, spec_path: str,
        config_path: str = "config/stage2_config.yaml") -> str:

    config  = yaml.safe_load(Path(config_path).read_text())
    finding = json.loads(Path(finding_path).read_text(encoding="utf-8"))
    spec    = json.loads(Path(spec_path).read_text(encoding="utf-8"))

    f        = finding["finding"]
    repo     = f["repo_name"]
    lang     = f["lang"]
    rule_id  = f["rule_id"].replace("/", "_")
    function = f["function_name"]

    repo_root = config.get("repo_root", "").format(repo=repo)

    print(f"[Stage2] function  : {function}")
    print(f"[Stage2] rule_id   : {f['rule_id']}")
    print(f"[Stage2] strategy  : {spec['_meta']['input_strategy']} / {spec['monitor']['strategy']}")

    # 1. Pre-fill skeleton
    skeleton = build_skeleton(finding, spec, repo_root)
    print(f"[Stage2] skeleton built, calling {config['model']} ...")

    # 2. Load prompts
    prompts_dir = config["prompts_dir"]
    system_p = Path(prompts_dir, "stage2_system.txt").read_text(encoding="utf-8")
    user_tmpl = Path(prompts_dir, "stage2_user.txt").read_text(encoding="utf-8")
    user_p   = user_tmpl.format(skeleton=skeleton)

    # 3. Call LLM
    raw  = call_llm(system_p, user_p, config["model"],
                    config["temperature"], config["max_tokens"], config["timeout"])
    code = extract_code(raw)

    # 4. Validate syntax
    validate_harness(code)

    # 5. Write output
    out_path = Path(
        config["harness_out"].format(lang=lang, repo=repo, rule_id=rule_id)
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(code, encoding="utf-8")

    print(f"[Stage2] output    : {out_path}")
    print(f"\n[Stage2] Run with:")
    print(f"  python {out_path} -atheris_runs=10000")
    print(f"  python {out_path} corpus/  # with corpus dir")

    return str(out_path)
```

---

### `run_stage2.py`

```python
#!/usr/bin/env python3
import argparse
from stage2.harness_generator import run

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FuzzGen Stage 2: Harness Generator")
    parser.add_argument("--finding", required=True, help="Path to findings.json")
    parser.add_argument("--spec",    required=True, help="Path to oracle_spec.json")
    parser.add_argument("--config",  default="config/stage2_config.yaml")
    args = parser.parse_args()

    out = run(args.finding, args.spec, args.config)
    print(f"\n[Stage2] harness ready: {out}")
```

---

## Skeleton mẫu LLM nhận được (py/bad-tag-filter)

Đây là input thực tế LLM nhận — minh họa rõ phần nào code fill, phần nào LLM fill:

```python
# AUTO-GENERATED ATHERIS HARNESS SKELETON
# rule_id  : py/bad-tag-filter
# function : sanitize_svg_content
# file     : superset/utils/core.py
# ================================================================

import atheris
import sys
import re

with atheris.instrument_imports():
    from superset.utils.core import sanitize_svg_content

# === ORACLE SPEC ===
# oracle_type      : BAD_TAG_FILTER
# input_strategy   : direct_params
# monitor_strategy : inspect_return
# patch_target     : None
# capture_what     : returned sanitized SVG content
# tainted_params   : [{"name": "svg_content", "index": 0, "type": "str"}]
# trigger_patterns : ["</script\\s*>"]
# expected_exceptions: []
# raise_message    : BAD_TAG_FILTER: Malformed script tag detected in sanitized SVG content
# cleanup_needed   : False
# cleanup_desc     : None
# attack_scenario  : Attacker provides SVG with malformed script tags not filtered by regex
# function_signature: def sanitize_svg_content(svg_content: str)

def TestOneInput(data):
    fdp = atheris.FuzzedDataProvider(data)

    # [TODO: LLM fills FDP block, function call, and oracle check here]

atheris.Setup(sys.argv, TestOneInput)
atheris.Fuzz()
```

### Output LLM sinh ra (expected)

```python
# AUTO-GENERATED ATHERIS HARNESS SKELETON
# rule_id  : py/bad-tag-filter
# function : sanitize_svg_content
# file     : superset/utils/core.py
# ================================================================

import atheris
import sys
import re

with atheris.instrument_imports():
    from superset.utils.core import sanitize_svg_content

# === ORACLE SPEC ===
# ...

def TestOneInput(data):
    fdp = atheris.FuzzedDataProvider(data)

    # FDP block: tainted_params → [{"name": "svg_content", "type": "str"}]
    svg_content = fdp.ConsumeUnicodeNoSurrogates(
        fdp.ConsumeIntInRange(0, 4096)
    )

    # Function call: inspect_return strategy
    try:
        result = sanitize_svg_content(svg_content)
    except Exception:
        return

    # Oracle check: trigger_patterns on return value
    for pattern in [r"</script\s*>"]:
        if re.search(pattern, result, re.IGNORECASE):
            raise RuntimeError(
                "BAD_TAG_FILTER: Malformed script tag detected in sanitized SVG content"
            )

atheris.Setup(sys.argv, TestOneInput)
atheris.Fuzz()
```

---

## Chạy thử

```bash
cd /home/caterpie/FuzzGen

# Chain Stage 1 → Stage 2
python run_stage1.py \
  --finding output/python/superset/verifycation_result/findings.json

python run_stage2.py \
  --finding output/python/superset/verifycation_result/findings.json \
  --spec    output/python/superset/verifycation_result/oracle_spec.json

# Validate syntax
python -m py_compile output/python/superset/verification/harness_py_bad-tag-filter.py

# Smoke run
python output/python/superset/verification/harness_py_bad-tag-filter.py \
  -atheris_runs=100
```

---

## Checklist triển khai

```
Phase A — Core
  [ ] stage2/__init__.py (rỗng)
  [ ] stage2/import_resolver.py
  [ ] stage2/template_builder.py
  [ ] stage2/llm_client.py
  [ ] stage2/harness_generator.py

Phase B — Prompts & Config
  [ ] prompts/stage2_system.txt
  [ ] prompts/stage2_user.txt
  [ ] config/stage2_config.yaml

Phase C — CLI
  [ ] run_stage2.py

Phase D — Test cases
  [ ] direct_params + inspect_return  → py/bad-tag-filter / sanitize_svg_content
  [ ] flask_view    + inspect_return  → py/url-redirection / warm_up_cache
  [ ] patch_call case                 → khi có finding phù hợp

Phase E — Validation
  [ ] py -m py_compile harness.py           # syntax check
  [ ] python harness.py -atheris_runs=100   # smoke run không crash
  [ ] Verify oracle trigger với known-bad input
```

---

## Notes

> **Phân chia trách nhiệm rõ ràng**: Code fill những gì deterministic
> (import, boilerplate, oracle spec dạng comment). LLM chỉ reasoning
> cách wire FDP → function call → oracle check. Giảm tối đa surface
> area LLM có thể hallucinate.

> **Comment-as-spec pattern**: Oracle spec được embed dưới dạng comment
> trong skeleton. LLM đọc trực tiếp từ source thay vì từ system prompt
> dài → giảm "lost in the middle" problem với long context.

> **validate_harness() fail fast**: Syntax error từ LLM bị bắt trước
> khi ghi file. Không để harness lỗi nằm im trong output dir.

> **Future — Example-based prompting**: Khi gặp case phức tạp
> (multi-function call chain, class instantiation, async), thêm
> few-shot example vào `stage2_system.txt` theo oracle_type hoặc
> input_strategy. Không cần thay đổi architecture.

> **Future — Corpus seed generation**: Từ `trigger_patterns` có thể
> generate known-bad seeds để inject vào Atheris corpus dir, giúp
> fuzzer tìm bug nhanh hơn trong những lần chạy đầu.