import atheris
import sys
import re

with atheris.instrument_imports():

    from superset.utils.core import sanitize_svg_content


# === FIXED CONTRACTS (DO NOT MODIFY) ===
_COMPILED_PATTERNS = [

    re.compile("<script[\\s>]", re.IGNORECASE),

    re.compile("</script\\s+>", re.IGNORECASE),

    re.compile("<script\\b[^>]*>", re.IGNORECASE),

    re.compile("javascript:", re.IGNORECASE),

]
_RAISE_MESSAGE  = "BAD_TAG_FILTER: Script tag survived SVG sanitization — captured={captured} pattern={matched_pattern}"
_TAINTED_PARAMS = [{"name": "svg_content", "index": 0, "type": "str"}]
# ========================================

def TestOneInput(data):
    fdp = atheris.FuzzedDataProvider(data)
    svg_content = fdp.ConsumeUnicodeNoSurrogates(len(data))
    
    if not svg_content or '<' not in svg_content:
        return

    try:
        result = sanitize_svg_content(svg_content)
    except Exception:
        return

    captured = str(result)
    for pattern in _COMPILED_PATTERNS:
        if pattern.search(captured):
            raise RuntimeError(
                _RAISE_MESSAGE
                .replace("{captured}", captured)
                .replace("{matched_pattern}", pattern.pattern)
            )


if __name__ == "__main__":
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()