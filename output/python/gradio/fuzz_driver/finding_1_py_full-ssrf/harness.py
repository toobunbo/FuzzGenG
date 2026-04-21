import atheris
import sys
import re
import os

from unittest.mock import patch, MagicMock


import httpx


with atheris.instrument_imports():

    from gradio.image_utils import extract_svg_content


# === FIXED CONTRACTS (DO NOT MODIFY) ===
_COMPILED_PATTERNS = [

    re.compile("https?://169\\.254\\.169\\.254", re.IGNORECASE),

    re.compile("https?://127\\.0\\.0\\.1", re.IGNORECASE),

    re.compile("https?://localhost[:/]", re.IGNORECASE),

    re.compile("https?://0\\.0\\.0\\.0", re.IGNORECASE),

    re.compile("https?://10\\.\\d+\\.\\d+\\.\\d+", re.IGNORECASE),

    re.compile("https?://192\\.168\\.\\d+\\.\\d+", re.IGNORECASE),

    re.compile("https?://172\\.(1[6-9]|2[0-9]|3[01])\\.\\d+\\.\\d+", re.IGNORECASE),

    re.compile("https?://\\[::1\\]", re.IGNORECASE),

    re.compile("https?://metadata\\.google\\.internal", re.IGNORECASE),

    re.compile("file://", re.IGNORECASE),

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
# condition        : The URL passed to httpx.get() points to an internal/private network address or cloud metadata endpoint, confirming SSRF exploitation with no allowlist or IP restriction in place
# capture_what     : The first positional argument to httpx.get() — the full URL string constructed from user-controlled image_file
# skip_hint        : not (image_file.startswith('http://') or image_file.startswith('https://') or image_file.startswith('file://'))
# ========================================


_SEED_CORPUS = [
    "http://169.254.169.254/latest/meta-data/",
    "http://127.0.0.1/etc/passwd",
    "http://localhost:8080/admin",
    "http://0.0.0.0/secret",
    "http://10.0.0.1/internal",
    "http://192.168.1.1/router",
    "http://172.16.0.1/private",
    "http://[::1]/loopback",
    "http://metadata.google.internal/computeMetadata/v1/",
    "file:///etc/passwd",
    "HTTP://169.254.169.254/latest/meta-data/",
    "HTTPS://127.0.0.1/secret",
    "http://169.254.169.254%2Flatest%2Fmeta-data%2F",
    "https://192.168.0.1/admin",
    "https://172.31.255.255/internal",
    "file:///proc/self/environ",
]


def TestOneInput(data):
    fdp = atheris.FuzzedDataProvider(data)

    # 1. INPUT GENERATION
    if fdp.ConsumeBool():
        # Use a seed corpus entry
        seed_index = fdp.ConsumeIntInRange(0, len(_SEED_CORPUS) - 1)
        image_file = _SEED_CORPUS[seed_index]
        # Optionally append fuzz-generated suffix
        if fdp.ConsumeBool():
            suffix = fdp.ConsumeString(min(len(data), 32))
            image_file = image_file + suffix
    else:
        image_file = fdp.ConsumeString(len(data))

    # 2. SKIP CONDITION
    if not (image_file.startswith('http://') or image_file.startswith('https://') or image_file.startswith('file://')):
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

        # 5. ORACLE CHECK — OUTSIDE the function call try/except, INSIDE the patch context
        for call in mock_get.call_args_list:
            # Check positional args first
            captured = None
            if call.args:
                captured = call.args[0]
            elif call.kwargs.get("url") is not None:
                captured = call.kwargs.get("url")
            else:
                # Try generic fallback
                captured = call.kwargs.get("None")

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


if __name__ == "__main__":
    # Export seed corpus to disk so libFuzzer can mutate raw bytes directly.
    # This preserves coverage-guided mutation — fuzzer mutates content, not index.
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