import re
import logging
from litellm import completion

def call_llm(system_prompt: str, user_prompt: str, model: str,
             temperature: float = 0.2, max_tokens: int = 2048,
             timeout: int = 120) -> str:
    logging.debug("\n========== LLM REQUEST ==========")
    logging.debug(f"[SYSTEM PROMPT]\n{system_prompt}\n")
    logging.debug(f"[USER PROMPT]\n{user_prompt}\n")

    response = completion(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
    )
    
    content = response.choices[0].message.content
    logging.debug(f"========== LLM RESPONSE ==========\n{content}\n==================================")
    return content


def extract_code(raw: str) -> str:
    """Strip markdown fences, return clean Python source."""
    fence = re.search(r"```(?:python)?\s*([\s\S]+?)\s*```", raw)
    if fence:
        return fence.group(1).strip()
    return raw.strip()


def validate_harness(code: str) -> None:
    """Fail fast: syntax check before writing to disk."""
    try:
        compile(code, "<harness>", "exec")
    except SyntaxError as e:
        raise ValueError(f"LLM generated invalid Python:\n{e}\n\n{code}")
