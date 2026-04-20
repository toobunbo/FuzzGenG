# FuzzGen — Stage 3: Extract — Implementation Chi Tiết

> **Rename:** Stage Extract → Stage 3 | Compile/Repair Loop → Stage 4  
> **Mục tiêu:** Enrich context từ CodeQL database + source code, output structured artifacts cho Stage 4 dùng.

---

## Tổng quan Stage 3

```
Input:
  - CodeQL database (Python repo)
  - functions.csv, caller.csv, callee.csv (đã có từ trước)
  - Repo source files

Stage 3 làm:
  1. Integrate body_extractor → get_function_body() utility
  2. Chạy 4 CodeQL queries mới → 4 CSV files
  3. Expose ExtractContext API cho Stage 4 dùng

Output:
  - decorators.csv
  - init_signatures.csv
  - callee_return_types.csv
  - caller_chains.csv
  - get_function_body() callable (không phải file, dùng trực tiếp)
```

---

## Directory Structure

```
FuzzGen/
├── src/
│   ├── stage3/                          ← MỚI (Stage Extract)
│   │   ├── __init__.py
│   │   ├── extract_pipeline.py          # Orchestrator
│   │   ├── body_extractor.py            # Integrate từ code cũ
│   │   ├── codeql_runner.py             # Chạy queries + parse BQRS → CSV
│   │   └── extract_context.py           # API cho Stage 4 dùng
│   ├── queries/
│   │   └── python/                      ← MỚI
│   │       ├── decorators.ql
│   │       ├── init_signatures.ql
│   │       ├── callee_return_types.ql
│   │       └── caller_chains.ql
│   ├── config/
│   │   └── stage3_config.yaml           ← MỚI
│   └── run_stage3.py                    ← MỚI CLI entry point
├── tests/
│   └── stage3/                          ← MỚI
│       ├── test_body_extractor.py
│       ├── test_codeql_runner.py
│       ├── test_extract_context.py
│       └── fixtures/
│           ├── mock_functions.csv
│           ├── mock_caller.csv
│           ├── mock_callee.csv
│           └── mock_repo/
│               └── gradio_client/
│                   └── client.py        # snippet để test body extraction
└── output/{lang}/{repo}/
    └── context/
        ├── functions.csv                ← đã có
        ├── signatures_function.csv      ← đã có
        ├── caller.csv                   ← đã có
        ├── callee.csv                   ← đã có
        ├── decorators.csv               ← Stage 3 output
        ├── init_signatures.csv          ← Stage 3 output
        ├── callee_return_types.csv      ← Stage 3 output
        └── caller_chains.csv            ← Stage 3 output
```

---

## Module 1 — `body_extractor.py`

> Integrate từ code đã có, thêm xử lý class method và error handling.

### Interface

```python
class BodyExtractor:
    def __init__(self, repo_root: str, functions_csv: str):
        """
        repo_root     : đường dẫn đến thư mục gốc của repo
        functions_csv : đường dẫn đến functions.csv
        """

    def get_function_body(
        self,
        func_name: str,
        class_name: str | None = None,
    ) -> str:
        """
        Trả về source code của function.

        Nếu class_name được cung cấp → tìm method trong class đó.
        Nếu không tìm thấy → trả về "[Function not found: {func_name}]"
        """

    def get_bodies_for_list(
        self,
        targets: list[dict],  # [{"func": "X", "class": "Y"}, ...]
    ) -> dict[str, str]:
        """
        Batch version — dùng cho Stage 4 khi LLM request nhiều bodies.
        """
```

### Logic chi tiết

```python
def get_function_body(self, func_name, class_name=None):
    rows = self._load_functions_csv()

    for row in rows:
        name  = row.get("name", "")
        scope = row.get("scope", "")

        # Match theo class_name nếu có
        if class_name:
            if name != func_name or scope != class_name:
                continue
        else:
            if name != func_name:
                continue

        file_path  = row.get("file", "")
        start_line = int(row.get("start_line", 0))
        end_line   = int(row.get("end_line", 0))

        if start_line > 0 and end_line >= start_line:
            full_path = os.path.join(self.repo_root, file_path)
            code = self._read_lines(full_path, start_line, end_line)
            return (
                f"# Function: {func_name}\n"
                f"# File: {file_path}:{start_line}-{end_line}\n"
                f"# Class: {class_name or 'module-level'}\n"
                f"{code}"
            )

    return f"[Function not found: {func_name}" \
           f"{f' in class {class_name}' if class_name else ''}]"
```

### Edge cases cần handle

| Case | Xử lý |
|---|---|
| `func_name` trùng tên ở nhiều class | Dùng `class_name` để disambiguate |
| File không tồn tại trong repo_root | Log warning, return `[File not found: {path}]` |
| `start_line > end_line` | Log warning, return `[Invalid line range]` |
| `scope` là nested class `"Outer.Inner"` | Split lấy phần cuối để match |
| Encoding lỗi trong source file | Dùng `errors='replace'` khi đọc file |

---

## Module 2 — `codeql_runner.py`

### Interface

```python
class CodeQLRunner:
    def __init__(self, codeql_path: str, db_path: str, output_dir: str):
        """
        codeql_path : path đến CodeQL CLI binary
        db_path     : path đến CodeQL database của repo
        output_dir  : nơi write CSV output
        """

    def run_query(self, query_path: str, output_csv: str) -> bool:
        """
        Chạy một .ql query, decode BQRS → CSV.
        Return True nếu thành công.
        """

    def run_all(self, queries_dir: str) -> dict[str, bool]:
        """
        Chạy tất cả queries trong queries_dir.
        Return dict {query_name: success}.
        """
```

### Logic chạy query

```python
def run_query(self, query_path, output_csv):
    bqrs_path = output_csv.replace(".csv", ".bqrs")

    # Step 1: Compile + chạy query
    run_cmd = [
        self.codeql_path, "query", "run",
        "--database", self.db_path,
        "--output", bqrs_path,
        query_path
    ]
    result = subprocess.run(run_cmd, capture_output=True, timeout=120)
    if result.returncode != 0:
        logger.error(f"Query failed: {result.stderr.decode()}")
        return False

    # Step 2: Decode BQRS → CSV
    decode_cmd = [
        self.codeql_path, "bqrs", "decode",
        "--format", "csv",
        "--output", output_csv,
        bqrs_path
    ]
    result = subprocess.run(decode_cmd, capture_output=True, timeout=60)
    if result.returncode != 0:
        logger.error(f"Decode failed: {result.stderr.decode()}")
        return False

    logger.info(f"Query OK → {output_csv}")
    return True
```

### Fallback nếu không có CodeQL DB

Một số findings có thể không cần enrichment — nếu `db_path` không tồn tại, `codeql_runner` skip và log warning. Stage 4 sẽ dùng context tối thiểu (chỉ có `functions.csv` + `body_extractor`).

---

## Module 3 — Bốn CodeQL Queries

### `queries/python/decorators.ql`

```ql
/**
 * @name Function decorators
 * @description Extract decorators applied to Python functions
 * @kind table
 * @id py/extract/decorators
 */

import python

from Function f, Expr decorator
where decorator = f.getADecorator()
select
    f.getName()                                      as function_name,
    f.getLocation().getFile().getRelativePath()      as function_file,
    f.getLocation().getStartLine()                   as function_line,
    decorator.toString()                             as decorator_name
order by function_file, function_line
```

**Output CSV:**
```
function_name, function_file,   function_line, decorator_name
upload,        views/core.py,   44,            login_required
upload,        views/core.py,   44,            expose("/upload/")
shortner,      views/core.py,   88,            has_access_api
shortner,      views/core.py,   88,            expose("/shortner/")
```

---

### `queries/python/init_signatures.ql`

```ql
/**
 * @name Class __init__ signatures
 * @description Extract __init__ parameters for all classes
 * @kind table
 * @id py/extract/init-signatures
 */

import python

from ClassDef c, Function init, Parameter p
where
    init = c.getAMethod() and
    init.getName() = "__init__" and
    p = init.getAnArg() and
    p.getName() != "self"
select
    c.getName()                                      as class_name,
    c.getLocation().getFile().getRelativePath()      as class_file,
    c.getLocation().getStartLine()                   as class_line,
    p.getName()                                      as param_name,
    p.getPosition()                                  as param_index,
    p.getAnnotation().toString()                     as param_type,
    p.getDefault().toString()                        as default_value
order by class_file, class_name, param_index
```

**Output CSV:**
```
class_name, class_file,              class_line, param_name,  param_index, param_type, default_value
Endpoint,   gradio_client/client.py, 312,        client,      0,           Client,     
Endpoint,   gradio_client/client.py, 312,        fn_index,    1,           int,        
Endpoint,   gradio_client/client.py, 312,        dependency,  2,           dict,       
Client,     gradio_client/client.py, 45,         src,         0,           str,        
Client,     gradio_client/client.py, 45,         hf_token,    1,           str | None, None
```

---

### `queries/python/callee_return_types.ql`

```ql
/**
 * @name Callee return types
 * @description Extract return type annotations of called functions
 * @kind table
 * @id py/extract/callee-return-types
 */

import python

from Function caller, Call call, Function callee
where
    call.getEnclosingFunction() = caller and
    callee = call.getACallee() and
    // Chỉ lấy callees có return annotation — tránh noise
    exists(callee.getReturnAnnotation())
select
    caller.getName()                                 as caller_name,
    caller.getLocation().getFile().getRelativePath() as caller_file,
    callee.getName()                                 as callee_name,
    callee.getLocation().getFile().getRelativePath() as callee_file,
    callee.getReturnAnnotation().toString()          as return_type
order by caller_file, caller_name
```

**Output CSV:**
```
caller_name, caller_file,   callee_name,    callee_file,        return_type
shortner,    views/core.py, get,            flask_sqlalchemy.py, scoped_session
shortner,    views/core.py, add,            flask_sqlalchemy.py, None
export_csv,  views/core.py, get_df_payload, viz.py,             pd.DataFrame
```

---

### `queries/python/caller_chains.ql`

```ql
/**
 * @name Caller chains (depth 2)
 * @description Find functions called through 2 layers
 * @kind table
 * @id py/extract/caller-chains
 */

import python

from Function target, Function layer1, Function layer2
where
    layer1.calls(target) and
    layer2.calls(layer1) and
    // Loại bỏ self-calls và test functions
    layer1 != target and
    layer2 != layer1 and
    not layer2.getName().matches("test_%")
select
    target.getName()                                 as target_name,
    target.getLocation().getFile().getRelativePath() as target_file,
    layer1.getName()                                 as layer1_caller,
    layer1.getLocation().getFile().getRelativePath() as layer1_file,
    layer2.getName()                                 as layer2_caller,
    layer2.getLocation().getFile().getRelativePath() as layer2_file
order by target_file, target_name
```

**Output CSV:**
```
target_name,     target_file, layer1_caller, layer1_file,      layer2_caller, layer2_file
get_df_payload,  viz.py,      get_viz,       views/utils.py,   explore_json,  views/core.py
execute_query,   db/core.py,  process,       services/sql.py,  run_query,     api/sql.py
```

---

## Module 4 — `extract_context.py`

API chính mà Stage 4 sẽ gọi — abstract hóa toàn bộ data access.

### Interface

```python
class ExtractContext:
    """
    Unified API để Stage 4 access tất cả enriched context.
    Không cần biết data đến từ CSV hay body_extractor.
    """

    def __init__(
        self,
        repo_name: str,
        lang: str,
        context_dir: str,   # output/{lang}/{repo}/context/
        repo_root: str,     # repos/{lang}/{repo}/
    ):

    # === Body extraction ===
    def get_function_body(self, func_name: str, class_name: str | None = None) -> str:
        """Trả về source code của function."""

    def get_bodies_for_list(self, targets: list[dict]) -> dict[str, str]:
        """Batch body fetch — dùng khi LLM request nhiều bodies."""

    # === Decorator info ===
    def get_decorators(self, func_name: str) -> list[dict]:
        """
        Return: [{"name": "login_required", "args": []}, ...]
        """

    def is_route_handler(self, func_name: str) -> bool:
        """True nếu function có @app.route / @expose / @router.get ..."""

    def get_route_info(self, func_name: str) -> dict | None:
        """
        Return: {"path": "/upload/", "methods": ["POST"], "framework": "flask"}
        """

    # === Class init info ===
    def get_init_params(self, class_name: str) -> list[dict]:
        """
        Return: [{"name": "client", "index": 0, "type": "Client", "default": None}, ...]
        """

    def needs_instantiation(self, class_name: str) -> bool:
        """True nếu __init__ có required params (không có default value)."""

    # === Callee info ===
    def get_callee_return_types(self, func_name: str) -> list[dict]:
        """
        Return: [{"callee": "db.session.get", "return_type": "Model | None"}, ...]
        """

    def has_db_dependency(self, func_name: str) -> bool:
        """True nếu function gọi bất kỳ db.session.* / cursor.execute."""

    def has_framework_dependency(self, func_name: str) -> bool:
        """True nếu function gọi current_app / g. / flask.g."""

    # === Caller chain ===
    def get_caller_chain(self, func_name: str) -> list[dict]:
        """
        Return: [
            {"name": "explore_json", "file": "views/core.py", "depth": 2},
            {"name": "get_viz",      "file": "views/utils.py", "depth": 1},
        ]
        """

    def get_chain_depth(self, func_name: str) -> int:
        """Số caller layers. 0 = top-level, 1 = direct caller, 2+ = chained."""

    # === Gap classification ===
    def classify_gap(self, func_name: str, class_name: str | None, error_type: str) -> str:
        """
        Kết hợp error_type + context data để confirm gap classification.
        Return: "GAP_1_CLASS_METHOD" | "GAP_2_FRAMEWORK" | ...
        """
```

---

## Module 5 — `extract_pipeline.py`

Orchestrator chạy toàn bộ Stage 3.

```python
class ExtractPipeline:
    def __init__(self, config: dict):
        self.codeql_runner = CodeQLRunner(
            codeql_path=config["codeql_path"],
            db_path=config["db_path"],
            output_dir=config["context_dir"],
        )
        self.body_extractor = BodyExtractor(
            repo_root=config["repo_root"],
            functions_csv=config["functions_csv"],
        )

    def run(self) -> bool:
        """
        Chạy toàn bộ Stage 3:
        1. Run 4 CodeQL queries
        2. Verify output CSVs exist + non-empty
        3. Log summary

        Return True nếu thành công.
        """
        results = self.codeql_runner.run_all(queries_dir=config["queries_dir"])

        success_count = sum(results.values())
        logger.info(f"Stage 3 Extract: {success_count}/4 queries succeeded")

        # Partial success vẫn OK — Stage 4 dùng được gì có được nấy
        return success_count > 0
```

---

## Config — `stage3_config.yaml`

```yaml
# Stage 3: Extract Configuration

codeql:
  path: "codeql"                        # hoặc /absolute/path/to/codeql
  db_base: "codeql_dbs/{lang}/{repo}"   # CodeQL database location
  timeout_query: 120                    # seconds per query
  timeout_decode: 60                    # seconds for BQRS decode

queries:
  dir: "src/queries/python"
  files:
    - decorators.ql
    - init_signatures.ql
    - callee_return_types.ql
    - caller_chains.ql

output:
  context_dir: "output/{lang}/{repo}/context"

repo:
  root: "repos/{lang}/{repo}"
  functions_csv: "output/{lang}/{repo}/context/functions.csv"
```

---

## CLI — `run_stage3.py`

```bash
# Chạy toàn bộ Stage 3 cho một repo
python src/run_stage3.py --repo gradio --lang python

# Chỉ chạy một query cụ thể
python src/run_stage3.py --repo gradio --lang python --query decorators

# Dry run — kiểm tra config mà không chạy thật
python src/run_stage3.py --repo gradio --lang python --dry-run

# Với log file
python src/run_stage3.py --repo gradio --lang python --log-file debug.log
```

---

## Tests

### Test 1 — `test_body_extractor.py`

```python
# tests/stage3/test_body_extractor.py
import pytest
from src.stage3.body_extractor import BodyExtractor

FIXTURE_DIR = "tests/stage3/fixtures"

@pytest.fixture
def extractor():
    return BodyExtractor(
        repo_root=f"{FIXTURE_DIR}/mock_repo",
        functions_csv=f"{FIXTURE_DIR}/mock_functions.csv",
    )

# --- Test cases ---

def test_top_level_function(extractor):
    """Lấy body của top-level function thành công."""
    body = extractor.get_function_body("build_hf_headers")
    assert "def build_hf_headers" in body
    assert "[Function not found" not in body

def test_class_method_with_class_name(extractor):
    """Lấy body của class method khi cung cấp class_name."""
    body = extractor.get_function_body("_download_file", class_name="Endpoint")
    assert "def _download_file" in body
    assert "# Class: Endpoint" in body

def test_class_method_without_class_name_ambiguous(extractor):
    """
    Nếu không có class_name và có nhiều function cùng tên,
    trả về match đầu tiên và log warning.
    """
    body = extractor.get_function_body("__init__")
    # Không crash, trả về kết quả nào đó
    assert "[Function not found" not in body

def test_function_not_found(extractor):
    """Function không tồn tại → return sentinel string."""
    body = extractor.get_function_body("nonexistent_function")
    assert "[Function not found: nonexistent_function]" == body

def test_function_wrong_class(extractor):
    """Function tồn tại nhưng sai class → not found."""
    body = extractor.get_function_body("_download_file", class_name="WrongClass")
    assert "[Function not found" in body

def test_file_not_in_repo(extractor):
    """functions.csv trỏ đến file không tồn tại trong repo_root."""
    body = extractor.get_function_body("ghost_function")
    assert "[File not found" in body or "[Function not found" in body

def test_invalid_line_range(extractor):
    """start_line > end_line → return error string."""
    # Mock functions.csv có entry với start=100, end=50
    body = extractor.get_function_body("bad_range_function")
    assert "[Invalid line range" in body

def test_batch_get_bodies(extractor):
    """Batch fetch nhiều functions cùng lúc."""
    targets = [
        {"func": "build_hf_headers", "class": None},
        {"func": "_download_file",   "class": "Endpoint"},
        {"func": "nonexistent",      "class": None},
    ]
    results = extractor.get_bodies_for_list(targets)
    assert len(results) == 3
    assert "def build_hf_headers" in results["build_hf_headers"]
    assert "def _download_file"   in results["_download_file"]
    assert "[Function not found"  in results["nonexistent"]
```

---

### Test 2 — `test_codeql_runner.py`

```python
# tests/stage3/test_codeql_runner.py
import pytest
from unittest.mock import patch, MagicMock
from src.stage3.codeql_runner import CodeQLRunner

@pytest.fixture
def runner(tmp_path):
    return CodeQLRunner(
        codeql_path="codeql",
        db_path="/fake/db/path",
        output_dir=str(tmp_path),
    )

def test_run_query_success(runner, tmp_path):
    """Query chạy thành công → trả về True + tạo CSV."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr=b"")
        result = runner.run_query(
            query_path="src/queries/python/decorators.ql",
            output_csv=str(tmp_path / "decorators.csv"),
        )
    assert result is True
    # subprocess.run phải được gọi 2 lần: query run + bqrs decode
    assert mock_run.call_count == 2

def test_run_query_fail_on_query_step(runner, tmp_path):
    """Query step thất bại → trả về False."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr=b"Error: DB not found")
        result = runner.run_query(
            query_path="src/queries/python/decorators.ql",
            output_csv=str(tmp_path / "decorators.csv"),
        )
    assert result is False

def test_run_query_fail_on_decode_step(runner, tmp_path):
    """Decode step thất bại → trả về False."""
    with patch("subprocess.run") as mock_run:
        # First call (query) succeeds, second call (decode) fails
        mock_run.side_effect = [
            MagicMock(returncode=0, stderr=b""),
            MagicMock(returncode=1, stderr=b"Decode error"),
        ]
        result = runner.run_query(
            query_path="src/queries/python/decorators.ql",
            output_csv=str(tmp_path / "decorators.csv"),
        )
    assert result is False

def test_run_all_partial_success(runner, tmp_path):
    """Một số queries fail → vẫn trả về dict với mixed results."""
    with patch.object(runner, "run_query") as mock_query:
        mock_query.side_effect = [True, False, True, True]
        results = runner.run_all(queries_dir="src/queries/python")
    assert sum(results.values()) == 3
    assert len(results) == 4

def test_run_query_timeout(runner, tmp_path):
    """Subprocess timeout → trả về False, không crash pipeline."""
    import subprocess
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("codeql", 120)):
        result = runner.run_query(
            query_path="src/queries/python/decorators.ql",
            output_csv=str(tmp_path / "decorators.csv"),
        )
    assert result is False
```

---

### Test 3 — `test_extract_context.py`

```python
# tests/stage3/test_extract_context.py
import pytest
import csv
import os
from src.stage3.extract_context import ExtractContext

FIXTURE_DIR = "tests/stage3/fixtures"

@pytest.fixture
def ctx(tmp_path):
    """
    Setup ExtractContext với mock CSV files.
    """
    # Copy fixture CSVs vào tmp_path để test không mutate fixtures
    import shutil
    context_dir = tmp_path / "context"
    context_dir.mkdir()
    for csv_file in ["decorators.csv", "init_signatures.csv",
                     "callee_return_types.csv", "caller_chains.csv",
                     "functions.csv"]:
        src = os.path.join(FIXTURE_DIR, csv_file)
        if os.path.exists(src):
            shutil.copy(src, context_dir / csv_file)

    return ExtractContext(
        repo_name="gradio",
        lang="python",
        context_dir=str(context_dir),
        repo_root=f"{FIXTURE_DIR}/mock_repo",
    )

# --- Decorator tests ---

def test_get_decorators_flask_route(ctx):
    """Function có @login_required và @expose → trả về cả hai."""
    decorators = ctx.get_decorators("upload")
    names = [d["name"] for d in decorators]
    assert "login_required" in names
    assert "expose" in names

def test_is_route_handler_true(ctx):
    """Function có @expose hoặc @app.route → True."""
    assert ctx.is_route_handler("upload") is True

def test_is_route_handler_false(ctx):
    """Utility function không có route decorator → False."""
    assert ctx.is_route_handler("build_hf_headers") is False

def test_get_route_info(ctx):
    """Trả về route path và methods từ decorator args."""
    info = ctx.get_route_info("shortner")
    assert info["path"] == "/superset/shortner/"
    assert "POST" in info["methods"]
    assert info["framework"] == "flask"

def test_get_route_info_no_route(ctx):
    """Function không có route decorator → None."""
    assert ctx.get_route_info("build_hf_headers") is None

# --- Init signature tests ---

def test_get_init_params_with_required_args(ctx):
    """Endpoint cần 3 required args → trả về list đúng."""
    params = ctx.get_init_params("Endpoint")
    assert len(params) == 3
    assert params[0]["name"] == "client"
    assert params[1]["name"] == "fn_index"
    assert params[1]["type"] == "int"

def test_needs_instantiation_true(ctx):
    """Class có required __init__ params → True."""
    assert ctx.needs_instantiation("Endpoint") is True

def test_needs_instantiation_false(ctx):
    """Class có __init__ với tất cả default values → False."""
    # SimpleClass(name="default") → không cần args
    assert ctx.needs_instantiation("SimpleClass") is False

def test_get_init_params_class_not_found(ctx):
    """Class không có trong init_signatures.csv → empty list."""
    assert ctx.get_init_params("NonExistentClass") == []

# --- Callee return type tests ---

def test_get_callee_return_types(ctx):
    """Trả về return types của tất cả callees."""
    callees = ctx.get_callee_return_types("shortner")
    callee_names = [c["callee"] for c in callees]
    assert "get" in callee_names or any("session" in n for n in callee_names)

def test_has_db_dependency_true(ctx):
    """Function gọi db.session.* → True."""
    assert ctx.has_db_dependency("shortner") is True

def test_has_db_dependency_false(ctx):
    """Function không gọi DB → False."""
    assert ctx.has_db_dependency("build_hf_headers") is False

def test_has_framework_dependency_true(ctx):
    """Function gọi current_app → True."""
    assert ctx.has_framework_dependency("get_chart") is True

# --- Caller chain tests ---

def test_get_caller_chain_depth_2(ctx):
    """Function được gọi qua 2 layers → chain có 2 entries."""
    chain = ctx.get_caller_chain("get_df_payload")
    assert len(chain) >= 2
    depths = [c["depth"] for c in chain]
    assert 1 in depths
    assert 2 in depths

def test_get_chain_depth(ctx):
    """Đếm đúng depth của caller chain."""
    assert ctx.get_chain_depth("get_df_payload") == 2

def test_get_chain_depth_direct(ctx):
    """Function chỉ có direct caller → depth 1."""
    assert ctx.get_chain_depth("validate_sql") == 1

def test_get_chain_depth_top_level(ctx):
    """Function không có caller trong codebase → depth 0."""
    assert ctx.get_chain_depth("build_hf_headers") == 0

# --- Gap classification tests ---

def test_classify_gap_class_method(ctx):
    """ImportError + class method scope → GAP_1."""
    gap = ctx.classify_gap(
        func_name="_download_file",
        class_name="Endpoint",
        error_type="ImportError: cannot import name '_download_file'",
    )
    assert gap == "GAP_1_CLASS_METHOD"

def test_classify_gap_framework(ctx):
    """App context error + route handler → GAP_2."""
    gap = ctx.classify_gap(
        func_name="upload",
        class_name=None,
        error_type="RuntimeError: Working outside of application context",
    )
    assert gap == "GAP_2_FRAMEWORK"

def test_classify_gap_precondition(ctx):
    """NoneType error + db dependency → GAP_3."""
    gap = ctx.classify_gap(
        func_name="shortner",
        class_name=None,
        error_type="AttributeError: 'NoneType' object has no attribute 'add'",
    )
    assert gap == "GAP_3_PRECONDITION"

def test_classify_gap_type_mismatch(ctx):
    """TypeError argument + no special context → GAP_5."""
    gap = ctx.classify_gap(
        func_name="validate_sql",
        class_name=None,
        error_type="TypeError: argument must be str, not bytes",
    )
    assert gap == "GAP_5_TYPE_MISMATCH"
```

---

### Fixture files cần tạo

#### `fixtures/mock_functions.csv`
```csv
name,file,start_line,end_line,scope
build_hf_headers,gradio_client/client.py,10,25,
_download_file,gradio_client/client.py,350,380,Endpoint
__init__,gradio_client/client.py,312,340,Endpoint
__init__,gradio_client/client.py,45,80,Client
validate_sql,utils/sql.py,10,20,
ghost_function,nonexistent/file.py,1,10,
bad_range_function,gradio_client/client.py,100,50,
```

#### `fixtures/mock_repo/gradio_client/client.py`
```python
# Mock snippet — chỉ cần đủ để test body extraction

def build_hf_headers(token=None):
    """Build headers for HuggingFace API."""
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers

class Client:
    def __init__(self, src: str, hf_token: str | None = None):
        self.src = src
        self.hf_token = hf_token

class Endpoint:
    def __init__(self, client, fn_index: int, dependency: dict):
        self.client = client
        self.fn_index = fn_index
        self.dependency = dependency

    def _download_file(self, url: str, save_dir: str) -> str:
        import httpx
        response = httpx.get(url)
        # ... save file
        return save_dir
```

#### `fixtures/decorators.csv`
```csv
function_name,function_file,function_line,decorator_name
upload,views/core.py,44,login_required
upload,views/core.py,44,"expose(""/upload/"", methods=[""POST""])"
shortner,views/core.py,88,has_access_api
shortner,views/core.py,88,"expose(""/superset/shortner/"", methods=[""POST""])"
get_chart,views/core.py,120,has_access_api
```

#### `fixtures/init_signatures.csv`
```csv
class_name,class_file,class_line,param_name,param_index,param_type,default_value
Endpoint,gradio_client/client.py,312,client,0,Client,
Endpoint,gradio_client/client.py,312,fn_index,1,int,
Endpoint,gradio_client/client.py,312,dependency,2,dict,
Client,gradio_client/client.py,45,src,0,str,
Client,gradio_client/client.py,45,hf_token,1,str | None,None
SimpleClass,utils/simple.py,5,name,0,str,default
```

#### `fixtures/callee_return_types.csv`
```csv
caller_name,caller_file,callee_name,callee_file,return_type
shortner,views/core.py,get,db/session.py,scoped_session
shortner,views/core.py,add,db/session.py,None
shortner,views/core.py,commit,db/session.py,None
get_chart,views/core.py,current_app,flask/globals.py,Flask
get_df_payload,viz.py,get_query_str,db/models.py,str
```

#### `fixtures/caller_chains.csv`
```csv
target_name,target_file,layer1_caller,layer1_file,layer2_caller,layer2_file
get_df_payload,viz.py,get_viz,views/utils.py,explore_json,views/core.py
validate_sql,utils/sql.py,run_query,api/sql.py,,
```

---

## Checklist Implementation

### Stage Extract (Stage 3)
- [ ] `body_extractor.py` — integrate + handle class methods + edge cases
- [ ] `queries/python/decorators.ql`
- [ ] `queries/python/init_signatures.ql`
- [ ] `queries/python/callee_return_types.ql`
- [ ] `queries/python/caller_chains.ql`
- [ ] `codeql_runner.py` — run queries + decode BQRS + timeout handling
- [ ] `extract_context.py` — unified API
- [ ] `extract_pipeline.py` — orchestrator
- [ ] `stage3_config.yaml`
- [ ] `run_stage3.py` — CLI entry point

### Tests
- [ ] `test_body_extractor.py` — 8 test cases
- [ ] `test_codeql_runner.py` — 5 test cases
- [ ] `test_extract_context.py` — 17 test cases
- [ ] Fixture files (6 files)

### Integration
- [ ] Update `run_test_cases.py` để chạy Stage 3 sau Stage 2
- [ ] Test end-to-end với repo gradio
- [ ] Verify `output/python/gradio/context/` có đủ 4 CSV mới