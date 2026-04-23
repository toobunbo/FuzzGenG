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
    # Check if function has real (non-self/cls) parameters in the signatures CSV
    has_real_params = any(r for r in signatures
                          if r.name == function_name and r.file == file
                          and r.param_name not in ("self", "cls"))
    if has_real_params:
        return "direct_params"

    # No real params → look up the function in functions.csv
    func = next((r for r in functions
                 if r.name == function_name and r.file == file), None)

    # Flask class-based views: scope contains "Class" (e.g. "Class MyView")
    if func and "Class" in func.scope:
        return "flask_view"

    # Fallback heuristic: if the function exists in functions.csv but has no
    # real params (only self), it's almost certainly a Flask MethodView / View
    # method — treat it as flask_view so the LLM uses request.* to get input.
    if func is not None:
        only_self = all(r.param_name in ("self", "cls")
                        for r in signatures
                        if r.name == function_name and r.file == file)
        if only_self:
            return "flask_view"

    return "direct_params"