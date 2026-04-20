import os

def resolve_import(file_path: str, function_name: str, repo_root: str) -> str:
    """
    Convert file path + function name -> Python import statement.

    Examples:
      "superset/utils/core.py" + "sanitize_svg_content"
      -> "from superset.utils.core import sanitize_svg_content"
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
