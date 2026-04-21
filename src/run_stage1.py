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
    import tempfile
    import traceback
    
    parser = argparse.ArgumentParser(description="FuzzGen Stage 1: Oracle Reasoner")
    parser.add_argument("--finding", required=True, help="Path to single finding JSON or summary JSON")
    parser.add_argument("--config",  default="src/config/stage1_config.yaml")
    parser.add_argument("--log-file", help="Path to log file")
    parser.add_argument("--verdict", choices=["TP", "NMD", "FP", "all"], default="all",
                        help="Filter findings by verdict: TP (True Positive), NMD (Needs More Data), FP (False Positive) or all")
    args = parser.parse_args()
    
    setup_logging(args.log_file)
    
    data = json.loads(open(args.finding, encoding="utf-8").read())
    
    if "verdicts" in data:
        verdicts = data.get("verdicts", [])
        logging.info(f"Batch mode: Loaded {len(verdicts)} findings from summary.")
        processed = 0
        success = 0
        for idx, item in enumerate(verdicts):
            if not isinstance(item, dict) or "finding" not in item: continue
            
            v = item.get("verdict", "")
            if v == "Error": continue
            
            v_map = {"True Positive": "TP", "Needs More Data": "NMD", "False Positive": "FP"}
            if args.verdict != "all":
                if v_map.get(v, v) != args.verdict:
                    continue
            
            f = item["finding"]
            f["id"] = str(idx)
            
            logging.info(f"\n{'='*50}\nProcessing Finding {idx}: {f.get('rule_id')} (Verdict: {v})\n{'='*50}")
            tmp = tempfile.mktemp(suffix=".json")
            with open(tmp, "w", encoding="utf-8") as tf:
                payload = {"finding": f}
                if "answers" in item:
                    payload["answers"] = item["answers"]
                if "reasoning" in item:
                    payload["reasoning"] = item["reasoning"]
                json.dump(payload, tf, ensure_ascii=False)
                
            try:
                run(tmp, args.config)
                success += 1
            except Exception as e:
                logging.error(f"Failed to process finding {idx}: {e}")
                logging.debug(traceback.format_exc())
            finally:
                import os
                if os.path.exists(tmp): os.remove(tmp)
            processed += 1
        logging.info(f"Batch processing completed! Processed: {processed}, Successful: {success}")
    else:
        # Single mode
        spec = run(args.finding, args.config)
        logging.info("\n[Stage1] oracle_spec:")
        logging.info("\n" + json.dumps(spec, indent=2, ensure_ascii=False))
