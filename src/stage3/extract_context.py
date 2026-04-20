import csv
import logging
import os
import re

from .body_extractor import BodyExtractor

logger = logging.getLogger(__name__)

# Route decorator patterns for Flask/FastAPI detection
_ROUTE_PATTERNS = [
    re.compile(r"@(?:app|blueprint)\.route\("),
    re.compile(r"@(?:router|api_router)\.(?:get|post|put|delete|patch)\("),
    re.compile(r"@expose\("),
]


class ExtractContext:
    def __init__(
        self,
        repo_name: str,
        lang: str,
        context_dir: str,
        repo_root: str,
    ):
        self.repo_name = repo_name
        self.lang = lang
        self.context_dir = context_dir
        self.repo_root = repo_root
        self.body_extractor = BodyExtractor(
            repo_root=repo_root,
            functions_csv=os.path.join(context_dir, "functions.csv"),
        )
        self._cache: dict[str, list[dict]] = {}

    def _load_csv(self, filename: str) -> list[dict]:
        if filename in self._cache:
            return self._cache[filename]
        filepath = os.path.join(self.context_dir, filename)
        rows = []
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
        self._cache[filename] = rows
        return rows

    # === Body extraction ===

    def get_function_body(self, func_name: str, class_name: str | None = None) -> str:
        return self.body_extractor.get_function_body(func_name, class_name=class_name)

    def get_bodies_for_list(self, targets: list[dict]) -> dict[str, str]:
        return self.body_extractor.get_bodies_for_list(targets)

    # === Decorator info ===

    def get_decorators(self, func_name: str) -> list[dict]:
        rows = self._load_csv("decorators.csv")
        result = []
        for row in rows:
            if row.get("function_name") == func_name:
                dec_str = row.get("decorator_name", "")
                name = self._parse_decorator_name(dec_str)
                args = self._parse_decorator_args(dec_str)
                result.append({"name": name, "args": args, "raw": dec_str})
        return result

    @staticmethod
    def _parse_decorator_name(dec_str: str) -> str:
        match = re.match(r"([a-zA-Z_]\w*)", dec_str.strip())
        return match.group(1) if match else dec_str.strip()

    @staticmethod
    def _parse_decorator_args(dec_str: str) -> list[str]:
        match = re.search(r"\((.+)\)", dec_str)
        if not match:
            return []
        return [a.strip().strip("\"'") for a in match.group(1).split(",")]

    def is_route_handler(self, func_name: str) -> bool:
        decorators = self.get_decorators(func_name)
        for d in decorators:
            for pat in _ROUTE_PATTERNS:
                if pat.match("@" + d["name"] + "(") or pat.search(d["raw"]):
                    return True
        return False

    def get_route_info(self, func_name: str) -> dict | None:
        decorators = self.get_decorators(func_name)
        for d in decorators:
            raw = d["raw"]
            # Try to extract path
            path_match = re.search(r'["\'](/[^"\']+)["\']', raw)
            if path_match:
                path = path_match.group(1)
            else:
                continue

            # Detect methods
            methods_match = re.search(r'methods\s*=\s*\[(.*?)\]', raw)
            methods = (
                [m.strip().strip("\"'") for m in methods_match.group(1).split(",")]
                if methods_match
                else ["GET"]
            )

            # Detect framework
            framework = "flask"
            if "router" in d["name"] or "api_router" in raw:
                framework = "fastapi"

            return {"path": path, "methods": methods, "framework": framework}
        return None

    # === Class init info ===

    def get_init_params(self, class_name: str) -> list[dict]:
        rows = self._load_csv("init_signatures.csv")
        params = []
        for row in rows:
            if row.get("class_name") == class_name:
                params.append({
                    "name": row.get("param_name", ""),
                    "index": int(row.get("param_index", 0)),
                    "type": row.get("param_type", ""),
                    "default": row.get("default_value", "") or None,
                })
        return params

    def needs_instantiation(self, class_name: str) -> bool:
        params = self.get_init_params(class_name)
        return any(p["default"] is None for p in params)

    # === Callee info ===

    def get_callee_return_types(self, func_name: str) -> list[dict]:
        rows = self._load_csv("callee_return_types.csv")
        result = []
        for row in rows:
            if row.get("caller_name") == func_name:
                result.append({
                    "callee": row.get("callee_name", ""),
                    "callee_file": row.get("callee_file", ""),
                    "return_type": row.get("return_type", ""),
                })
        return result

    def has_db_dependency(self, func_name: str) -> bool:
        callees = self.get_callee_return_types(func_name)
        for c in callees:
            callee_lower = c["callee"].lower()
            file_lower = c["callee_file"].lower()
            if ("session" in callee_lower or "cursor" in callee_lower or
                    "execute" in callee_lower or "db/" in file_lower or
                    "db\\" in file_lower or "database" in file_lower):
                return True
        return False

    def has_framework_dependency(self, func_name: str) -> bool:
        callees = self.get_callee_return_types(func_name)
        for c in callees:
            callee_lower = c["callee"].lower()
            if callee_lower in ("current_app", "g", "flask.g", "request"):
                return True
        return False

    # === Caller chain ===

    def get_caller_chain(self, func_name: str) -> list[dict]:
        rows = self._load_csv("caller_chains.csv")
        chain = []
        for row in rows:
            if row.get("target_name") == func_name:
                chain.append({
                    "name": row.get("layer1_caller", ""),
                    "file": row.get("layer1_file", ""),
                    "depth": 1,
                })
                if row.get("layer2_caller"):
                    chain.append({
                        "name": row.get("layer2_caller", ""),
                        "file": row.get("layer2_file", ""),
                        "depth": 2,
                    })
        return chain

    def get_chain_depth(self, func_name: str) -> int:
        chain = self.get_caller_chain(func_name)
        if not chain:
            return 0
        return max(c["depth"] for c in chain)

    # === Gap classification ===

    def classify_gap(self, func_name: str, class_name: str | None, error_type: str) -> str:
        # GAP_1: class method access issue
        if class_name and "ImportError" in error_type:
            return "GAP_1_CLASS_METHOD"

        # GAP_2: framework context issue
        if "Working outside of application context" in error_type or \
           "application context" in error_type.lower():
            if self.is_route_handler(func_name):
                return "GAP_2_FRAMEWORK"

        # GAP_3: precondition / null dependency
        if "NoneType" in error_type or "AttributeError" in error_type:
            if self.has_db_dependency(func_name):
                return "GAP_3_PRECONDITION"

        # GAP_4: missing import / module
        if "ModuleNotFoundError" in error_type or "ImportError" in error_type:
            return "GAP_4_MISSING_IMPORT"

        # GAP_5: type mismatch (fallback)
        if "TypeError" in error_type:
            return "GAP_5_TYPE_MISMATCH"

        # Default
        return "GAP_5_TYPE_MISMATCH"
