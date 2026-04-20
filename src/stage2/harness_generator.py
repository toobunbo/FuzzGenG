import json
import yaml
import logging
import os
from pathlib import Path
from .template_builder import build_skeleton
from .llm_client       import call_llm, extract_code, validate_harness


def run(finding_path: str, spec_path: str,
        config_path: str = "config/stage2_config.yaml") -> str:

    config = yaml.safe_load(Path(config_path).read_text())

    # Override model using .env variables if they exist
    llm_provider = os.getenv("LLM_PROVIDER")
    llm_model    = os.getenv("LLM_MODEL")
    if llm_provider and llm_model:
        config["model"] = f"{llm_provider}/{llm_model}"
    elif llm_model:
        config["model"] = llm_model

    finding = json.loads(Path(finding_path).read_text(encoding="utf-8"))
    spec    = json.loads(Path(spec_path).read_text(encoding="utf-8"))

    f        = finding["finding"]
    repo     = f["repo_name"]
    lang     = f["lang"]
    rule_id  = f["rule_id"].replace("/", "_")
    function = f.get("function_name", "unknown")          # ← fix: KeyError → ""unknown""

    repo_root = config.get("repo_root", "").format(repo=repo)

    logging.info(f"[Stage2] function  : {function}")
    logging.info(f"[Stage2] rule_id   : {f['rule_id']}")
    logging.info(f"[Stage2] strategy  : {spec.get('_meta', {}).get('input_strategy')}"
                 f" / {spec.get('monitor', {}).get('strategy')}")

    # 1. Pre-fill skeleton
    skeleton = build_skeleton(finding, spec, repo_root)
    logging.info(f"[Stage2] skeleton built, calling {config['model']} ...")

    # 2. Load prompts
    prompts_dir = config["prompts_dir"]

    strategy = spec.get("monitor", {}).get("strategy", "inspect_return")
    if strategy == "patch_call":
        system_file = "stage2_system_patchcall.txt"
    else:
        system_file = "stage2_system_inspectreturn.txt"

    system_p  = Path(prompts_dir, system_file).read_text(encoding="utf-8")
    user_tmpl = Path(prompts_dir, "stage2_user.txt").read_text(encoding="utf-8")
    user_p    = user_tmpl.format(skeleton=skeleton)

    # 3. Call LLM
    raw  = call_llm(system_p, user_p, config["model"],
                    config["temperature"], config["max_tokens"], config["timeout"])
    code = extract_code(raw)

    # 4. Validate syntax
    validate_harness(code)

    # 5. Write harness output
    out_path = Path(
        config["harness_out"].format(lang=lang, repo=repo, rule_id=rule_id)
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(code, encoding="utf-8")

    # 6. Write seed corpus                                 # ← thêm
    seed_corpus = spec.get("fuzz_guidance", {}).get("seed_corpus", [])
    if seed_corpus:
        corpus_dir = out_path.parent / "corpus" / rule_id
        corpus_dir.mkdir(parents=True, exist_ok=True)
        for i, seed in enumerate(seed_corpus):
            (corpus_dir / f"seed_{i:03d}").write_bytes(
                seed.encode("utf-8", errors="replace")
            )
        logging.info(f"[Stage2] corpus    : {corpus_dir} ({len(seed_corpus)} seeds)")

    logging.info(f"[Stage2] output    : {out_path}")
    logging.info(f"\n[Stage2] Run with:")
    logging.info(f"  python {out_path} -atheris_runs=10000")
    if seed_corpus:
        logging.info(f"  python {out_path} corpus/{rule_id}/")

    return str(out_path)
