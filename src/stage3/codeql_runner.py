import glob
import logging
import os
import subprocess

logger = logging.getLogger(__name__)


class CodeQLRunner:
    def __init__(self, codeql_path: str, db_path: str, output_dir: str):
        self.codeql_path = codeql_path
        self.db_path = db_path
        self.output_dir = output_dir

    def run_query(self, query_path: str, output_csv: str, timeout_query: int = 120, timeout_decode: int = 60) -> bool:
        if not os.path.exists(self.db_path):
            logger.warning(f"CodeQL database not found: {self.db_path} — skipping query")
            return False

        os.makedirs(os.path.dirname(output_csv), exist_ok=True)
        bqrs_path = output_csv.replace(".csv", ".bqrs")

        # Step 1: Run query
        run_cmd = [
            self.codeql_path, "query", "run",
            "--database", self.db_path,
            "--output", bqrs_path,
            query_path,
        ]
        try:
            result = subprocess.run(run_cmd, capture_output=True, timeout=timeout_query)
            if result.returncode != 0:
                stderr = result.stderr.decode(errors="replace")
                logger.error(f"Query failed ({query_path}): {stderr}")
                return False
        except subprocess.TimeoutExpired:
            logger.error(f"Query timed out after {timeout_query}s: {query_path}")
            return False

        # Step 2: Decode BQRS -> CSV
        decode_cmd = [
            self.codeql_path, "bqrs", "decode",
            "--format", "csv",
            "--output", output_csv,
            bqrs_path,
        ]
        try:
            result = subprocess.run(decode_cmd, capture_output=True, timeout=timeout_decode)
            if result.returncode != 0:
                stderr = result.stderr.decode(errors="replace")
                logger.error(f"Decode failed ({query_path}): {stderr}")
                return False
        except subprocess.TimeoutExpired:
            logger.error(f"Decode timed out after {timeout_decode}s: {output_csv}")
            return False

        logger.info(f"Query OK -> {output_csv}")
        return True

    def run_all(self, queries_dir: str) -> dict[str, bool]:
        results = {}
        for ql_file in sorted(glob.glob(os.path.join(queries_dir, "*.ql"))):
            name = os.path.splitext(os.path.basename(ql_file))[0]
            output_csv = os.path.join(self.output_dir, f"{name}.csv")
            results[name] = self.run_query(ql_file, output_csv)
        return results
