#!/usr/bin/env python3
import argparse, json
import logging
from dotenv import load_dotenv
load_dotenv()

from stage1.oracle_reasoner import run

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
    parser = argparse.ArgumentParser(description="FuzzGen Stage 1: Oracle Reasoner")
    parser.add_argument("--finding", required=True)
    parser.add_argument("--config",  default="src/config/stage1_config.yaml")
    parser.add_argument("--log-file", help="Path to log file")
    args = parser.parse_args()
    
    setup_logging(args.log_file)
    
    spec = run(args.finding, args.config)
    logging.info("\n[Stage1] oracle_spec:")
    logging.info("\n" + json.dumps(spec, indent=2, ensure_ascii=False))
