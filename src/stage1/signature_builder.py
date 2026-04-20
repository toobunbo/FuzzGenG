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