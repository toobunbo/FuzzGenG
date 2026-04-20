#!/usr/bin/env python3
import argparse
import logging
import os
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from stage3.extract_pipeline import ExtractPipeline


def setup_logging(log_file):
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(console_handler)

    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(file_handler)

    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("litellm").setLevel(logging.WARNING)


def load_config(config_path: str, repo: str, lang: str) -> dict:
    with open(config_path, "r") as f:
        raw = yaml.safe_load(f)

    return {
        "codeql_path": raw["codeql"]["path"],
        "db_path": raw["codeql"]["db_base"].format(lang=lang, repo=repo),
        "timeout_query": raw["codeql"]["timeout_query"],
        "timeout_decode": raw["codeql"]["timeout_decode"],
        "queries_dir": raw["queries"]["dir"],
        "context_dir": raw["output"]["context_dir"].format(lang=lang, repo=repo),
        "repo_root": raw["repo"]["root"].format(lang=lang, repo=repo),
        "functions_csv": raw["repo"]["functions_csv"].format(lang=lang, repo=repo),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FuzzGen Stage 3: Extract Context")
    parser.add_argument("--repo", required=True, help="Repository name (e.g. gradio)")
    parser.add_argument("--lang", default="python", help="Language (default: python)")
    parser.add_argument("--config", default="src/config/stage3_config.yaml")
    parser.add_argument("--dry-run", action="store_true", help="Print config and exit")
    parser.add_argument("--log-file", help="Path to log file")
    args = parser.parse_args()

    setup_logging(args.log_file)

    config = load_config(args.config, args.repo, args.lang)

    if args.dry_run:
        logging.info("[Stage3] Dry run — config:")
        for k, v in config.items():
            logging.info(f"  {k}: {v}")
        sys.exit(0)

    pipeline = ExtractPipeline(config)
    success = pipeline.run()

    if success:
        logging.info("[Stage3] Done — context enriched successfully")
    else:
        logging.error("[Stage3] Failed — no queries succeeded")
        sys.exit(1)
