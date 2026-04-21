import atheris
import sys
import re
import os

from unittest.mock import patch, MagicMock


import requests


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

    re.compile("https?://[^/]*@", re.IGNORECASE),

    re.compile("https?://\\[::1\\]", re.IGNORECASE),

]
_RAISE_MESSAGE  = "PY/FULL-SSRF: Full SSRF detected in extract_svg_content — requests.get received attacker-controlled URL — captured={captured} pattern={matched_pattern}"
_TAINTED_PARAMS = [{"name": "image_file", "index": 0, "type": "str | Path"}]
# ========================================

# === ORACLE CONTEXT ===
# strategy         : patch_call
# patch_target     : gradio.image_utils.requests.get
# target_arg_index : 0
# target_arg_name  : url
# input_strategy   : direct_params
# signature        : def extract_svg_content(image_file: str | Path)
# condition        : The URL passed to requests.get contains an attacker-controlled scheme and host, specifically targeting internal/private IP addresses or localhost, confirming full SSRF with no URL validation
# capture_what     : The full URL argument passed to requests.get, which is derived from the user-supplied image_file parameter
# skip_hint        : not (isinstance(image_file, str) and image_file.startswith(('http://', 'https://')))
# ========================================


def TestOneInput(data):
    fdp = atheris.FuzzedDataProvider(data)

    # 1. INPUT GENERATION — consume all remaining bytes as one string
    image_file = fdp.ConsumeUnicodeNoSurrogates(len(data))

    # 2. SKIP CONDITION — only proceed if input looks like an HTTP(S) URL
    if not (isinstance(image_file, str) and image_file.startswith(('http://', 'https://'))):
        return

    # 3. MOCK SETUP
    mock_response = MagicMock()
    mock_response.text = "<svg></svg>"
    mock_response.content = b"<svg></svg>"
    mock_response.status_code = 200
    mock_response.headers = {"Content-Type": "image/svg+xml"}

    with patch("gradio.image_utils.requests.get", return_value=mock_response) as mock_get:

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
                if pattern.search(captured_str):
                    matched_pattern = pattern.pattern
                    raise RuntimeError(
                        _RAISE_MESSAGE.format(
                            captured=captured_str,
                            matched_pattern=matched_pattern
                        )
                    )


# === SEED CORPUS — bypass-oriented, derived from trigger_patterns ===
_SEED_CORPUS = [
    # Direct SSRF targets — metadata endpoint
    "http://169.254.169.254/latest/meta-data/",
    "https://169.254.169.254/latest/meta-data/iam/security-credentials/",
    # Localhost variants
    "http://localhost/admin",
    "http://127.0.0.1/etc/passwd",
    "https://127.0.0.1:8080/internal",
    # IPv6 loopback
    "http://[::1]/secret",
    # Private IP ranges
    "http://10.0.0.1/internal",
    "http://192.168.1.1/router",
    "http://172.16.0.1/private",
    "http://172.31.255.255/admin",
    # Zero address
    "http://0.0.0.0/",
    # Credentials in URL (auth bypass attempt)
    "http://attacker@169.254.169.254/",
    "https://user:pass@127.0.0.1/secret",
    # Mixed case bypass attempts
    "HTTP://LOCALHOST/admin",
    "Http://LocalHost/secret",
    "hTTp://127.0.0.1/",
    # URL with path traversal after SSRF target
    "http://169.254.169.254/../../../etc/passwd",
    # Encoded variants
    "http://127.0.0.1%2F/secret",
    # SVG-like URL to trigger SVG fetch path
    "http://127.0.0.1/image.svg",
    "http://192.168.0.1/logo.svg",
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