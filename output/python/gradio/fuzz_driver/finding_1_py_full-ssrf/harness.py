import atheris
import sys
import re
import os

from unittest.mock import patch, MagicMock



with atheris.instrument_imports():

    from gradio.image_utils import extract_svg_content


# === FIXED CONTRACTS (DO NOT MODIFY) ===
_COMPILED_PATTERNS = [

    re.compile("https?://169\\.254\\.169\\.254", re.IGNORECASE),

    re.compile("https?://127\\.0\\.0\\.1", re.IGNORECASE),

    re.compile("https?://localhost", re.IGNORECASE),

    re.compile("https?://0\\.0\\.0\\.0", re.IGNORECASE),

    re.compile("https?://10\\.\\d+\\.\\d+\\.\\d+", re.IGNORECASE),

    re.compile("https?://192\\.168\\.\\d+\\.\\d+", re.IGNORECASE),

    re.compile("https?://172\\.(1[6-9]|2[0-9]|3[01])\\.\\d+\\.\\d+", re.IGNORECASE),

    re.compile("https?://\\[::1\\]", re.IGNORECASE),

    re.compile("https?://metadata\\.google\\.internal", re.IGNORECASE),

]
_RAISE_MESSAGE  = "PY/FULL-SSRF: httpx.get() called with attacker-controlled internal/metadata URL — captured={captured} pattern={matched_pattern}"
_TAINTED_PARAMS = [{"name": "image_file", "index": 0, "type": "str | Path"}]
# ========================================

# === ORACLE CONTEXT ===
# strategy         : patch_call
# patch_target     : gradio.image_utils.httpx.get
# target_arg_index : 0
# target_arg_name  : None
# input_strategy   : direct_params
# signature        : def extract_svg_content(image_file: str | Path)
# condition        : The URL passed to httpx.get() points to an internal/private IP, localhost, or cloud metadata endpoint, confirming SSRF exploitation with no validation blocking the request
# capture_what     : The URL argument passed to httpx.get() — the full attacker-controlled URL string
# skip_hint        : not (isinstance(image_file, str) and ('http://' in str(image_file) or 'https://' in str(image_file)))
# ========================================


def TestOneInput(data):
    fdp = atheris.FuzzedDataProvider(data)

    # 1. INPUT GENERATION
    # Single str param — consume all bytes
    image_file = fdp.ConsumeUnicodeNoSurrogates(len(data))

    # 2. SKIP CONDITION
    # Must be a string containing http:// or https:// to reach httpx.get()
    if not (isinstance(image_file, str) and ('http://' in image_file or 'https://' in image_file)):
        return

    # 3. MOCK SETUP
    mock_response = MagicMock()
    mock_response.text = "<svg></svg>"
    mock_response.status_code = 200
    mock_response.content = b"<svg></svg>"

    with patch("gradio.image_utils.httpx.get", return_value=mock_response) as mock_get:

        # 4. FUNCTION CALL
        try:
            extract_svg_content(image_file)
        except RuntimeError:
            raise
        except Exception:
            pass

        # 5. ORACLE CHECK — outside the function call try/except, inside patch context
        for call in mock_get.call_args_list:
            # Extract the captured URL argument
            captured = None
            if call.args:
                captured = call.args[0]
            else:
                captured = call.kwargs.get("url")

            if captured is None:
                continue

            captured_str = str(captured)

            for pattern in _COMPILED_PATTERNS:
                match = pattern.search(captured_str)
                if match:
                    matched_pattern = pattern.pattern
                    raise RuntimeError(
                        _RAISE_MESSAGE.format(
                            captured=captured_str,
                            matched_pattern=matched_pattern
                        )
                    )


# === SEED CORPUS — bypass-oriented, derived from trigger_patterns ===
_SEED_CORPUS = [
    "http://169.254.169.254/latest/meta-data/",
    "http://127.0.0.1/etc/passwd",
    "http://localhost/admin",
    "http://0.0.0.0/secret",
    "http://10.0.0.1/internal",
    "http://192.168.1.1/router",
    "http://172.16.0.1/private",
    "http://[::1]/loopback",
    "http://metadata.google.internal/computeMetadata/v1/",
    "HTTP://169.254.169.254/latest/meta-data/",
    "https://127.0.0.1:8080/admin",
    "https://192.168.0.1/config",
    "https://10.10.10.10/secret",
    "https://172.31.255.255/internal",
    "https://metadata.google.internal/",
    "http://169.254.169.254%2flatest%2fmeta-data/",
]


if __name__ == "__main__":
    # Export seed corpus to disk so libFuzzer can mutate raw bytes directly.
    _CORPUS_DIR = os.path.join(os.path.dirname(__file__), "fuzz_corpus")
    os.makedirs(_CORPUS_DIR, exist_ok=True)
    for _i, _seed in enumerate(_SEED_CORPUS):
        _seed_path = os.path.join(_CORPUS_DIR, f"seed_{_i:03d}")
        if not os.path.exists(_seed_path):
            with open(_seed_path, "wb") as _f:
                _f.write(_seed.encode("utf-8"))

    if _CORPUS_DIR not in sys.argv:
        sys.argv.append(_CORPUS_DIR)

    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()