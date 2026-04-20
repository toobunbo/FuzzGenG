import csv
import logging
import os

logger = logging.getLogger(__name__)


class BodyExtractor:
    def __init__(self, repo_root: str, functions_csv: str):
        self.repo_root = repo_root
        self.functions_csv = functions_csv
        self._rows = None

    def _load_functions_csv(self) -> list[dict]:
        if self._rows is not None:
            return self._rows
        self._rows = []
        with open(self.functions_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                self._rows.append(row)
        return self._rows

    def _read_lines(self, full_path: str, start_line: int, end_line: int) -> str:
        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            selected = lines[start_line - 1 : end_line]
            return "".join(selected)
        except FileNotFoundError:
            logger.warning(f"File not found: {full_path}")
            return f"[File not found: {full_path}]"

    def get_function_body(
        self,
        func_name: str,
        class_name: str | None = None,
    ) -> str:
        rows = self._load_functions_csv()

        for row in rows:
            name = row.get("name", "")
            scope = row.get("scope", "")

            if class_name:
                if name != func_name or scope != class_name:
                    continue
            else:
                if name != func_name:
                    continue

            file_path = row.get("file", "")
            start_line = int(row.get("start_line", 0))
            end_line = int(row.get("end_line", 0))

            if start_line > end_line:
                logger.warning(
                    f"Invalid line range for {func_name}: {start_line}-{end_line}"
                )
                return "[Invalid line range]"

            if start_line > 0 and end_line >= start_line:
                full_path = os.path.join(self.repo_root, file_path)
                code = self._read_lines(full_path, start_line, end_line)
                if code.startswith("[File not found"):
                    return code
                return (
                    f"# Function: {func_name}\n"
                    f"# File: {file_path}:{start_line}-{end_line}\n"
                    f"# Class: {class_name or 'module-level'}\n"
                    f"{code}"
                )

        if class_name:
            return f"[Function not found: {func_name} in class {class_name}]"
        return f"[Function not found: {func_name}]"

    def get_bodies_for_list(
        self,
        targets: list[dict],
    ) -> dict[str, str]:
        results = {}
        for t in targets:
            key = t.get("func", t.get("func_name", t.get("name", "")))
            cls = t.get("class", t.get("class_name"))
            results[key] = self.get_function_body(key, class_name=cls)
        return results
