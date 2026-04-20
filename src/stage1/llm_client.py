import json, re
import logging
from litellm import completion

def call_llm(system_prompt: str, user_prompt: str, model: str,
             temperature: float = 0.2, max_tokens: int = 1024, timeout: int = 60) -> str:
    logging.debug("\n========== LLM REQUEST ==========")
    logging.debug(f"[SYSTEM PROMPT]\n{system_prompt}\n")
    logging.debug(f"[USER PROMPT]\n{user_prompt}\n")

    response = completion(
        model=model,
        messages=[{"role": "system", "content": system_prompt},
                  {"role": "user",   "content": user_prompt}],
        temperature=temperature, max_tokens=max_tokens, timeout=timeout,
    )

    content = response.choices[0].message.content
    logging.debug(f"========== LLM RESPONSE ==========\n{content}\n==================================")
    return content

def parse_oracle_spec(raw_text: str) -> dict:
    text = raw_text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if fence:
        text = fence.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM output not valid JSON:\n{raw_text}\n\nError: {e}")

def validate_oracle_spec(spec: dict) -> None:
    # Top-level blocks
    for block in ["monitor", "oracle_check", "_meta"]:
        if block not in spec:
            raise ValueError(f"oracle_spec missing block: '{block}'")

    # monitor fields
    monitor = spec["monitor"]
    for field in ["strategy", "patch_target", "capture_what", "additional_imports"]:
        if field not in monitor:
            raise ValueError(f"monitor missing field: '{field}'")

    valid_strategies = {"inspect_return", "patch_call", "catch_exception"}
    if monitor["strategy"] not in valid_strategies:
        raise ValueError(f"monitor.strategy invalid: '{monitor['strategy']}'. Must be one of {valid_strategies}")

    if monitor["strategy"] == "patch_call" and not monitor["patch_target"]:
        raise ValueError("monitor.patch_target must be set when strategy is 'patch_call'")

    # if monitor["strategy"] != "inspect_return" and spec["oracle_check"].get("trigger_patterns"):
    #     raise ValueError("oracle_check.trigger_patterns must be [] when strategy is not 'inspect_return'")

    # oracle_check fields
    oracle_check = spec["oracle_check"]
    for field in ["condition_description", "trigger_patterns", "raise_type", "raise_message_template"]:
        if field not in oracle_check:
            raise ValueError(f"oracle_check missing field: '{field}'")

    # _meta fields
    meta = spec["_meta"]
    for field in ["function", "file", "input_strategy", "function_signature", "tainted_params"]:
        if field not in meta:
            raise ValueError(f"_meta missing field: '{field}'")

    valid_input_strategies = {"direct_params", "flask_view"}
    if meta["input_strategy"] not in valid_input_strategies:
        raise ValueError(f"_meta.input_strategy invalid: '{meta['input_strategy']}'")

    for i, param in enumerate(meta["tainted_params"]):
        for field in ["name", "index", "type"]:
            if field not in param:
                raise ValueError(f"tainted_params[{i}] missing field: '{field}'")
        if meta["input_strategy"] == "direct_params" and param["index"] < 0:
            raise ValueError(f"tainted_params[{i}].index must be >= 0 for direct_params strategy")