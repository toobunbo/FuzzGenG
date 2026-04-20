import logging

from .codeql_runner import CodeQLRunner

logger = logging.getLogger(__name__)


class ExtractPipeline:
    def __init__(self, config: dict):
        self.config = config
        self.codeql_runner = CodeQLRunner(
            codeql_path=config["codeql_path"],
            db_path=config["db_path"],
            output_dir=config["context_dir"],
        )

    def run(self) -> bool:
        queries_dir = self.config["queries_dir"]
        logger.info(f"[Stage3] Running queries from {queries_dir}")
        logger.info(f"[Stage3] Database: {self.config['db_path']}")
        logger.info(f"[Stage3] Output dir: {self.config['context_dir']}")

        results = self.codeql_runner.run_all(queries_dir)

        success_count = sum(results.values())
        total = len(results)
        logger.info(f"[Stage3] {success_count}/{total} queries succeeded")

        for name, ok in results.items():
            status = "OK" if ok else "FAILED"
            logger.info(f"[Stage3]   {name}: {status}")

        return success_count > 0
