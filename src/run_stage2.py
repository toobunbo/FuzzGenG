#!/usr/bin/env python3
import sys
import os
import argparse
from dotenv import load_dotenv

load_dotenv() # Load variables from .env to support Ollama API Base configurations

# Add src to Python Path so that stage2 is recognizable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from stage2.harness_generator import run
import logging

def setup_logging(log_file):
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)  # Root logger captures everything

    # CLI Output: INFO level only
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    logger.addHandler(console_handler)

    # Log File: DEBUG level (full chat)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
        logger.addHandler(file_handler)

    # Silence noisy third-party loggers
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("litellm").setLevel(logging.WARNING)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FuzzGen Stage 2: Harness Generator")
    parser.add_argument("--finding", required=True, help="Path to findings.json")
    parser.add_argument("--spec",    required=True, help="Path to oracle_spec.json")
    parser.add_argument("--config",  default="src/config/stage2_config.yaml")
    parser.add_argument("--log-file", help="Path to log file")
    args = parser.parse_args()

    setup_logging(args.log_file)

    out = run(args.finding, args.spec, args.config)
    logging.info(f"\n[Stage2] harness ready: {out}")
