import json, yaml, os
import logging
from pathlib import Path
from .csv_loader        import load_signatures, load_functions
from .signature_builder import build_signature, get_input_strategy
from .prompt_builder    import load_system_prompt, build_user_prompt
from .llm_client        import call_llm, parse_oracle_spec, validate_oracle_spec

def run(finding_path: str, config_path: str = "src/config/stage1_config.yaml") -> dict:
    config       = yaml.safe_load(Path(config_path).read_text())
    
    # Override model using .env variables if they exist
    llm_provider = os.getenv("LLM_PROVIDER")
    llm_model    = os.getenv("LLM_MODEL")
    if llm_provider and llm_model:
        config["model"] = f"{llm_provider}/{llm_model}"
    elif llm_model:
        config["model"] = llm_model

    finding_full = json.loads(Path(finding_path).read_text(encoding="utf-8"))
    f     = finding_full["finding"]
    repo  = f["repo_name"]
    lang  = f["lang"]
    func  = f.get("function_name", "unknown")
    file_ = f["file"]
    finding_id = f.get("id", "0")
    rule_id = f.get("rule_id", "unknown").replace("/", "_")

    sigs  = load_signatures(config["signatures_csv"].format(lang=lang, repo=repo))
    funcs = load_functions(config["functions_csv"].format(lang=lang, repo=repo))

    sig      = build_signature(func, file_, sigs)
    strategy = get_input_strategy(func, file_, sigs, funcs)
    logging.info(f"[Stage1] function  : {func}")
    logging.info(f"[Stage1] signature : {sig}")
    logging.info(f"[Stage1] strategy  : {strategy}")

    answers = finding_full.get("answers")

    sys_p  = load_system_prompt(config["prompts_dir"])
    user_p = build_user_prompt(finding_full, sig, strategy, config["prompts_dir"], answers)

    logging.info(f"[Stage1] calling   : {config['model']} ...")
    raw  = call_llm(sys_p, user_p, config["model"],
                    config["temperature"], config["max_tokens"], config["timeout"])
    spec = parse_oracle_spec(raw)
    validate_oracle_spec(spec)

    if "_meta" not in spec:
        spec["_meta"] = {}
    
    spec["_meta"].update({
        "function": func, 
        "file": file_,
        "input_strategy": strategy, 
        "function_signature": sig,
        "model": config["model"],
    })
    out = Path(config["oracle_spec_out"].format(lang=lang, repo=repo, id=finding_id, rule_id=rule_id))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(spec, indent=2, ensure_ascii=False), encoding="utf-8")
    logging.info(f"[Stage1] output    : {out}")
    return spec
