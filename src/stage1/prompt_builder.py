import json
from pathlib import Path

def load_system_prompt(prompts_dir: str) -> str:
    return Path(prompts_dir, "stage1_system.txt").read_text(encoding="utf-8")

def build_user_prompt(finding: dict, function_signature: str,
                       input_strategy: str, prompts_dir: str) -> str:
    template = Path(prompts_dir, "stage1_user.txt").read_text(encoding="utf-8")
    return template.format(
        finding_json       = json.dumps(finding, indent=2, ensure_ascii=False),
        function_signature = function_signature,
        input_strategy     = input_strategy,
    )
