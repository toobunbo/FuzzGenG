# FuzzGen — Stage Extract & Stage 3 Implementation Plan

## Tổng quan

```
Stage 2 (hiện tại)
    │
    ▼
┌─── Stage Extract ──────────────────────────────────────────┐
│  Tích hợp body_extractor + chạy 4 CodeQL queries mới      │
│  Output: enriched CSV artifacts                            │
└────────────────────────────────────────────────────────────┘
    │
    ▼
┌─── Stage 3: Harness Repair ────────────────────────────────┐
│  Step 1: Dry-run Validation                                │
│  Step 2: Error Classification                              │
│  Step 3: Context Fetch (dùng Stage Extract output)         │
│  Step 4: Repair Loop (max 3 attempts, LLM-driven)          │
│  Step 5: Write fixed harness                               │
└────────────────────────────────────────────────────────────┘
```

---

## Phần 1 — Stage Extract

### 1.1 Tích hợp `body_extractor.py`

**Hiện trạng:** `body_extractor.py` đã có logic đọc `functions.csv` và cắt đúng dòng code trong repo, nhưng chưa được integrate vào pipeline chính thức.

**Việc cần làm:**
- Expose `get_function_body(func_name, repo_name, lang)` như một utility có thể gọi từ Stage 3
- Đảm bảo hàm này handle được cả top-level functions lẫn class methods (dùng `scope` column để build fully-qualified name)
- Viết unit test với ít nhất 2 cases: top-level function và class method

**Input:** `functions.csv` (đã có) + repo source files
**Output:** function body string, dùng trực tiếp trong repair prompt

---

### 1.2 Bốn CodeQL Queries Mới

> **Điều kiện:** Cần CodeQL database cho Python repo đã được tạo trước.

#### Query 1 — `decorators.ql`

**Mục đích:** Detect `@app.route`, `@login_required`, `@has_access_api` để classify Gap 2 (framework context).

```ql
import python

from Function f, Call decorator
where decorator = f.getADecorator()
select
    f.getName()                                    as function_name,
    f.getLocation().getFile().getRelativePath()    as function_file,
    decorator.toString()                           as decorator_name,
    decorator.getLocation().getStartLine()         as decorator_line
```

**Output CSV schema:**
```
function_name, function_file, decorator_name, decorator_line
upload,        views/core.py, @login_required, 45
upload,        views/core.py, @expose,         44
```

---

#### Query 2 — `init_signatures.ql`

**Mục đích:** Lấy `__init__` signature của class để biết cần arguments gì khi instantiate — resolve Gap 1 (class method import).

```ql
import python

from ClassDef c, Function init, Parameter p
where
    init = c.getAMethod() and
    init.getName() = "__init__" and
    p = init.getAnArg() and
    p.getName() != "self"
select
    c.getName()                                    as class_name,
    c.getLocation().getFile().getRelativePath()    as class_file,
    p.getName()                                    as param_name,
    p.getPosition()                                as param_index,
    p.getAnnotation().toString()                   as param_type
```

**Output CSV schema:**
```
class_name, class_file,              param_name,  param_index, param_type
Endpoint,   gradio_client/client.py, client,      0,           Client
Endpoint,   gradio_client/client.py, fn_index,    1,           int
Endpoint,   gradio_client/client.py, dependency,  2,           dict
```

---

#### Query 3 — `callee_return_types.ql`

**Mục đích:** Biết return type của callees để generate đúng mock return value — resolve Gap 3 (precondition).

```ql
import python

from Function caller, Call call, Function callee
where
    call.getEnclosingFunction() = caller and
    callee = call.getACallee()
select
    caller.getName()                               as caller_name,
    caller.getLocation().getFile().getRelativePath() as caller_file,
    callee.getName()                               as callee_name,
    callee.getLocation().getFile().getRelativePath() as callee_file,
    callee.getReturnAnnotation().toString()        as return_type
```

**Output CSV schema:**
```
caller_name, caller_file,   callee_name,  callee_file,   return_type
shortner,    views/core.py, get,          db/session.py, Session
shortner,    views/core.py, add,          db/session.py, None
```

---

#### Query 4 — `caller_chains.ql`

**Mục đích:** Build call chain depth >= 2 để detect Gap 4 (chained call) và tìm đúng entry point.

```ql
import python

from Function target, Function caller1, Function caller2
where
    caller1.calls(target) and
    caller2.calls(caller1)
select
    target.getName()                                as target_name,
    target.getLocation().getFile().getRelativePath() as target_file,
    caller1.getName()                               as layer1_name,
    caller1.getLocation().getFile().getRelativePath() as layer1_file,
    caller2.getName()                               as layer2_name,
    caller2.getLocation().getFile().getRelativePath() as layer2_file
```

**Output CSV schema:**
```
target_name,  target_file,   layer1_name, layer1_file,      layer2_name, layer2_file
get_df,       viz.py,        get_viz,     views/utils.py,   explore_json, views/core.py
```

---

### 1.3 Module Python chạy queries

**File mới:** `src/stage_extract/extractor.py`

**Nhiệm vụ:**
1. Nhận `repo_name`, `lang`, `codeql_db_path`
2. Chạy từng `.ql` query qua CodeQL CLI
3. Decode BQRS output ra CSV
4. Write vào `output/{lang}/{repo}/context/`

**CLI:**
```bash
python src/run_extract.py --repo gradio --lang python
python src/run_extract.py --repo superset --lang python --query decorators
```

**Config mới** `src/config/extract_config.yaml`:
```yaml
codeql_path: "codeql"              # hoặc path tuyệt đối
queries_dir: "queries/python/"
output_base: "output/"
queries:
  - decorators.ql
  - init_signatures.ql
  - callee_return_types.ql
  - caller_chains.ql
```

---

### 1.4 Directory Structure sau Stage Extract

```
output/{lang}/{repo}/
├── verification/
│   └── harness_{rule_id}.py          ← Stage 2 output
└── context/
    ├── functions.csv                  ← đã có (CodeQL)
    ├── signatures_function.csv        ← đã có (CodeQL)
    ├── caller.csv                     ← đã có (CodeQL)
    ├── callee.csv                     ← đã có (CodeQL)
    ├── decorators.csv                 ← Stage Extract mới
    ├── init_signatures.csv            ← Stage Extract mới
    ├── callee_return_types.csv        ← Stage Extract mới
    └── caller_chains.csv              ← Stage Extract mới
```

---

## Phần 2 — Stage 3: Harness Repair

### 2.1 Step 1 — Dry-run Validation

**File:** `src/stage3/validator.py`

Chạy harness với `-runs=1` và timeout 30 giây:

```python
result = subprocess.run(
    ["python", harness_path, "-runs=1"],
    capture_output=True,
    timeout=30
)
```

**3 outcome:**

| Outcome | Condition | Action |
|---|---|---|
| ✅ SUCCESS | exit non-zero + "oracle" trong stderr | Không cần Stage 3 |
| 🔧 REPAIR | exit non-zero + Error trong stderr | Trigger Stage 3 |
| ❓ NO_CRASH | exit 0, không có crash | Log warning, skip (coverage — để sau) |

---

### 2.2 Step 2 — Error Classification

**File:** `src/stage3/error_classifier.py`

**Gap mapping:**

| Gap ID | Error Pattern | Mô tả |
|---|---|---|
| `GAP_1_CLASS_METHOD` | `ImportError: cannot import name` | Import class method sai |
| `GAP_1_CLASS_METHOD` | `TypeError: __init__() missing` | Class cần args để instantiate |
| `GAP_2_FRAMEWORK` | `Working outside of application context` | Thiếu Flask/FastAPI context |
| `GAP_2_FRAMEWORK` | `No application found` | Thiếu Flask/FastAPI context |
| `GAP_3_PRECONDITION` | `NoneType.*has no attribute` | Thiếu dependency |
| `GAP_3_PRECONDITION` | `missing \d+ required positional` | Thiếu precondition args |
| `GAP_4_CHAINED` | Không có error nhưng fuzz data không reach sink | Coverage issue (để sau) |
| `GAP_5_TYPE_MISMATCH` | `TypeError: argument must be str` | Sai type wiring |

**Output — `error_report.json`:**
```json
{
  "gap_type": "GAP_1_CLASS_METHOD",
  "raw_error": "TypeError: Endpoint.__init__() missing 3 required positional arguments: 'client', 'fn_index', and 'dependency'",
  "traceback_line": "harness_py_full-ssrf.py:23",
  "harness_path": "output/python/gradio/verification/harness_py_full-ssrf.py",
  "rule_id": "py/full-ssrf",
  "function_name": "_download_file",
  "class_name": "Endpoint"
}
```

---

### 2.3 Step 3 — Context Fetch

**File:** `src/stage3/context_fetcher.py`

Fetch đúng context theo gap — **không fetch tất cả**:

| Gap | Context cần fetch | Source |
|---|---|---|
| `GAP_1_CLASS_METHOD` | `init_signatures` của class | `init_signatures.csv` |
| `GAP_1_CLASS_METHOD` | Constructor body | `body_extractor` |
| `GAP_2_FRAMEWORK` | Decorators của function | `decorators.csv` |
| `GAP_2_FRAMEWORK` | Caller body (route handler) | `body_extractor` |
| `GAP_3_PRECONDITION` | Callee return types | `callee_return_types.csv` |
| `GAP_3_PRECONDITION` | Callee bodies | `body_extractor` |
| `GAP_4_CHAINED` | Caller chain | `caller_chains.csv` + `body_extractor` |
| `GAP_5_TYPE_MISMATCH` | Function body của target | `body_extractor` |

**Output — `repair_context.json`:**
```json
{
  "gap_type": "GAP_1_CLASS_METHOD",
  "attempt": 1,
  "error_report": { "...": "..." },

  "base_context": {
    "oracle_spec": { "...": "..." },
    "function_signature": "def _download_file(self, url, ...)",
    "tainted_params": [{"name": "url", "index": 0, "type": "str"}],
    "current_harness": "...harness code..."
  },

  "gap_context": {
    "class_name": "Endpoint",
    "init_params": [
      {"name": "client",     "index": 0, "type": "Client"},
      {"name": "fn_index",   "index": 1, "type": "int"},
      {"name": "dependency", "index": 2, "type": "dict"}
    ],
    "constructor_body": "def __init__(self, client, fn_index, dependency):\n    self.client = client\n    ..."
  },

  "llm_response_schema": {
    "status": "needs_more_context | confident",
    "reasoning": "string",
    "context_needed": [
      {
        "type": "function_body | caller_body | callee_body | init_body",
        "target": "Client.__init__",
        "file": "gradio_client/client.py"
      }
    ],
    "fix": "Python code string hoặc null"
  }
}
```

---

### 2.4 Step 4 — Repair Loop

**File:** `src/stage3/repair_loop.py`

**Logic 3 attempts:**

```
Attempt 1:
  Prompt = base_context + gap_context (minimal từ Step 3)
  LLM response:
    → "needs_more_context": fetch thêm items trong context_needed
    → "confident": validate fix → done

Attempt 2:
  Prompt = attempt 1 context + fetched items
  LLM response:
    → "needs_more_context": fetch thêm lần 2
    → "confident": validate fix → done

Attempt 3:
  Prompt = full context tất cả đã fetch
  System prompt: "You MUST return status=confident. No more context available."
  LLM response: bắt buộc "confident" + fix
```

**LLM Response Schema — trái tim của repair loop:**

```json
// Attempt 1 hoặc 2 — chưa đủ thông tin
{
  "status": "needs_more_context",
  "reasoning": "Need to see Client.__init__ to understand how to mock it properly",
  "context_needed": [
    {
      "type": "init_body",
      "target": "Client",
      "file": "gradio_client/client.py"
    }
  ],
  "fix": null
}

// Attempt cuối — đã đủ thông tin
{
  "status": "confident",
  "reasoning": "Client can be mocked with MagicMock, fn_index=0, dependency as empty dict",
  "context_needed": [],
  "fix": "import atheris\nimport sys\n..."
}
```

**Prompt system cho attempt 3:**
```
You have received all available context. You MUST provide a fix now.
Return status="confident" with working harness code.
Do not request additional context.
```

---

### 2.5 Step 5 — Write Fixed Harness

**File:** `src/stage3/harness_writer.py`

**Sequence:**
1. Extract `fix` code từ LLM response
2. `compile()` syntax check
3. Dry-run `-runs=1` để verify fix thực sự work
4. Write `harness_{rule_id}_fixed.py`
5. Write `repair_log.json`

**`repair_log.json`:**
```json
{
  "rule_id": "py/full-ssrf",
  "function": "_download_file",
  "gap_type": "GAP_1_CLASS_METHOD",
  "attempts_used": 2,
  "success": true,
  "context_fetched": [
    "init_signatures:Endpoint",
    "constructor_body:Endpoint.__init__",
    "init_body:Client"
  ],
  "final_harness": "output/python/gradio/verification/harness_py_full-ssrf_fixed.py",
  "timestamp": "2026-04-07T10:00:00"
}
```

---

## Phần 3 — Directory Structure Hoàn Chỉnh

```
FuzzGen/
├── src/
│   ├── stage1/                          ← không thay đổi
│   ├── stage2/                          ← giữ nguyên các fix đã làm
│   ├── stage_extract/                   ← MỚI
│   │   ├── extractor.py                 # chạy CodeQL queries + parse CSV
│   │   └── body_extractor.py            # integrate từ code cũ
│   ├── stage3/                          ← MỚI
│   │   ├── repair_pipeline.py           # orchestrator
│   │   ├── validator.py                 # dry-run
│   │   ├── error_classifier.py          # classify gap
│   │   ├── context_fetcher.py           # fetch context theo gap
│   │   ├── repair_loop.py               # LLM repair loop
│   │   ├── harness_writer.py            # write output
│   │   └── llm_client.py                # LiteLLM wrapper (giống Stage 1/2)
│   ├── config/
│   │   ├── stage1_config.yaml
│   │   ├── stage2_config.yaml
│   │   └── extract_config.yaml          ← MỚI
│   ├── prompts/
│   │   ├── stage1_system.txt
│   │   ├── stage2_system_*.txt
│   │   ├── stage3_system_gap1.txt       ← MỚI — class method
│   │   ├── stage3_system_gap2.txt       ← MỚI — framework context
│   │   ├── stage3_system_gap3.txt       ← MỚI — precondition
│   │   └── stage3_system_gap5.txt       ← MỚI — type mismatch
│   ├── queries/python/                  ← MỚI
│   │   ├── decorators.ql
│   │   ├── init_signatures.ql
│   │   ├── callee_return_types.ql
│   │   └── caller_chains.ql
│   ├── run_stage1.py
│   ├── run_stage2.py
│   ├── run_extract.py                   ← MỚI
│   ├── run_stage3.py                    ← MỚI
│   └── run_test_cases.py                ← update để chạy full pipeline
└── output/{lang}/{repo}/
    ├── verification/
    │   ├── harness_{rule_id}.py         ← Stage 2
    │   └── harness_{rule_id}_fixed.py  ← Stage 3
    ├── context/
    │   ├── functions.csv
    │   ├── signatures_function.csv
    │   ├── caller.csv
    │   ├── callee.csv
    │   ├── decorators.csv               ← Stage Extract
    │   ├── init_signatures.csv          ← Stage Extract
    │   ├── callee_return_types.csv      ← Stage Extract
    │   └── caller_chains.csv            ← Stage Extract
    └── repair/
        ├── error_report.json
        ├── repair_context.json
        └── repair_log.json
```

---

## Phần 4 — Implementation Order

### Ưu tiên 1 — Stage Extract (prerequisite cho Stage 3)
1. Integrate `body_extractor.py` → expose `get_function_body()` utility
2. Viết 4 CodeQL queries
3. Viết `extractor.py` — chạy queries + parse BQRS → CSV
4. Viết `run_extract.py` CLI
5. Test với repo gradio

### Ưu tiên 2 — Stage 3 Core
6. `validator.py` — dry-run harness
7. `error_classifier.py` — parse + classify error
8. `context_fetcher.py` — fetch context theo gap type
9. `repair_loop.py` — LLM loop với schema `needs_more_context | confident`
10. `harness_writer.py` — validate + write output

### Ưu tiên 3 — Prompts & Integration
11. Viết 4 system prompts cho từng gap
12. Update `run_test_cases.py` để chạy full pipeline Stage 1 → 2 → Extract → 3
13. Test end-to-end với `_download_file` finding (GAP_1_CLASS_METHOD)
14. Test với flask_view finding (GAP_2_FRAMEWORK)

---

## Phần 5 — Gaps Chưa Handle (để sau)

| Gap | Mô tả | Lý do defer |
|---|---|---|
| `GAP_4_CHAINED` | Coverage issue — fuzz data không reach sink | Cần coverage measurement |
| `catch_exception` strategy | Stage 2 fallback về `inspect_return` | Cần system prompt riêng |
| `stdin` / `env` input strategy | Không inject fuzz data qua đúng channel | Ít gặp trong web app |
| FastAPI framework | Chỉ handle Flask hiện tại | Gradio dùng FastAPI |

---

## Notes

- **Schema versioning:** Thêm `"schema_version": "1.0"` vào `repair_context.json` ngay từ đầu
- **GAP_4_CHAINED:** Caller chains query vẫn chạy để collect data, nhưng repair logic chưa implement
- **Typo config:** Fix `verifycation_result` → `verification_result` trong `stage1_config.yaml` khi có dịp
- **`.env` security:** Không commit API keys — nhắc lại khi setup môi trường mới