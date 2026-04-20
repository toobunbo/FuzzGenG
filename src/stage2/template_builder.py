import json
import os
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from .import_resolver import resolve_import

# "os" added — template __main__ block requires it for corpus export
TEMPLATE_BUILTINS = {"re", "sys", "atheris", "os"}


def build_skeleton(finding: dict, spec: dict, repo_root: str) -> str:
    f      = finding["finding"]
    meta    = spec.get("_meta", {})
    monitor = spec.get("monitor", {})
    oracle  = spec.get("oracle_check", {})
    fuzz    = spec.get("fuzz_guidance", {})

    rule_id          = f.get("rule_id", "Unknown")
    function_name    = meta.get("function", "")
    file_path        = meta.get("file", "")
    input_strategy   = meta.get("input_strategy", "direct_params")
    monitor_strategy = monitor.get("strategy", "inspect_return")

    # Resolve import
    raw_import   = resolve_import(file_path, function_name, repo_root)
    import_stmts = raw_import if isinstance(raw_import, list) else [raw_import]

    # Extra imports — skip builtins and unittest.mock (template handles it)
    extra_imports = []
    for m in monitor.get("additional_imports", []):
        if m.strip() not in TEMPLATE_BUILTINS:
            extra_imports.append(f"import {m}")

    # Normalize trigger_patterns
    trigger_patterns = oracle.get("trigger_patterns", [])
    if isinstance(trigger_patterns, str):
        trigger_patterns = json.loads(trigger_patterns)

    # Normalize tainted_params
    tainted_params = meta.get("tainted_params", [])
    if isinstance(tainted_params, str):
        tainted_params = json.loads(tainted_params)

    # Build function_signature — fallback if spec omits it
    function_signature = meta.get("function_signature") or (
        "def {}({})".format(
            function_name,
            ", ".join(p["name"] for p in tainted_params) if tainted_params else "...",
        )
    )

    # capture_what — lives in oracle semantically; monitor is a fallback
    capture_what = oracle.get("capture_what") or monitor.get("capture_what", "")

    # Render
    templates_dir = Path(__file__).parent / "templates"
    env = Environment(loader=FileSystemLoader(str(templates_dir)))
    env.filters["tojson"] = lambda v: json.dumps(v, ensure_ascii=False)
    template = env.get_template("base_harness.j2")

    return template.render(
        rule_id            = rule_id,
        function_name      = function_name,
        file_path          = file_path,
        extra_imports      = extra_imports,
        import_stmts       = import_stmts,
        input_strategy     = input_strategy,
        monitor_strategy   = monitor_strategy,
        patch_target       = monitor.get("patch_target"),
        target_arg_index   = monitor.get("target_arg_index"),
        target_arg_name    = monitor.get("target_arg_name"),
        capture_what       = capture_what,
        condition_desc     = oracle.get("condition_description", ""),
        tainted_params     = tainted_params,
        trigger_patterns   = trigger_patterns,
        raise_message      = oracle.get("raise_message_template", ""),
        function_signature = function_signature,
        skip_condition     = fuzz.get("skip_condition", "False"),
    )