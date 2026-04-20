import atheris
import sys
import re
import os

from unittest.mock import patch, MagicMock



with atheris.instrument_imports():

    from gradio.image_utils import extract_svg_content


# === FIXED CONTRACTS (DO NOT MODIFY) ===
_COMPILED_PATTERNS = [

    re.compile("https?://127\\.0\\.0\\.1", re.IGNORECASE),

    re.compile("https?://localhost", re.IGNORECASE),

    re.compile("https?://169\\.254\\.169\\.254", re.IGNORECASE),

    re.compile("https?://192\\.168\\.", re.IGNORECASE),

    re.compile("https?://10\\.", re.IGNORECASE),

    re.compile("https?://172\\.(1[6-9]|2[0-9]|3[01])\\.", re.IGNORECASE),

    re.compile("https?://0\\.0\\.0\\.0", re.IGNORECASE),

    re.compile("https?://\\[::1\\]", re.IGNORECASE),

    re.compile("file://", re.IGNORECASE),

    re.compile("https?://metadata\\.google\\.internal", re.IGNORECASE),

]
_RAISE_MESSAGE  = "PY/FULL-SSRF: Full SSRF confirmed — user-controlled URL reached HTTP request sink without validation — captured={captured} pattern={matched_pattern}"
_TAINTED_PARAMS = [{"name": "image_file", "index": 0, "type": "BinaryExpr"}]
# ========================================

# === ORACLE CONTEXT ===
# strategy         : patch_call
# patch_target     : gradio.image_utils.requests.get
# target_arg_index : 0
# target_arg_name  : url
# input_strategy   : direct_params
# signature        : def extract_svg_content(image_file: BinaryExpr)
# condition        : The URL passed to the HTTP request contains an internal/private IP, localhost, or metadata service address, confirming full SSRF exploitation with no URL validation
# capture_what     : The full URL argument passed to the HTTP request sink, derived from user-controlled image_file parameter
# skip_hint        : not (isinstance(image_file, (str, bytes)) and (b'http' in (image_file if isinstance(image_file, bytes) else image_file.encode()) or b'file' in (image_file if isinstance(image_file, bytes) else image_file.encode())))
# ========================================


def TestOneInput(data):
    fdp = atheris.FuzzedDataProvider(data)

    # 1. INPUT GENERATION — consume all remaining bytes as one string
    image_file = fdp.ConsumeUnicodeNoSurrogates(len(data))

   

    # 3. MOCK SETUP
    mock_response = MagicMock()
    mock_response.text = "<svg></svg>"
    mock_response.content = b"<svg></svg>"
    mock_response.status_code = 200

    captured_url = None
    matched_pattern = None

    with patch("gradio.image_utils.requests.get", return_value=mock_response) as mock_get:
        # 4. FUNCTION CALL — wrapped in try/except
        try:
            extract_svg_content(image_file)
        except RuntimeError:
            raise
        except Exception:
            return

        # 5. ORACLE CHECK — outside the function call try/except, inside the patch context
        for call in mock_get.call_args_list:
            # Check positional args first, then keyword args
            if call.args:
                url_arg = call.args[0]
            else:
                url_arg = call.kwargs.get("url", None)

            if url_arg is None:
                continue

            captured = str(url_arg)

            for pattern in _COMPILED_PATTERNS:
                if pattern.search(captured):
                    matched_pattern = pattern.pattern
                    raise RuntimeError(
                        _RAISE_MESSAGE.format(
                            captured=captured,
                            matched_pattern=matched_pattern
                        )
                    )


# === SEED CORPUS — bypass-oriented, derived from trigger_patterns ===
_SEED_CORPUS = [
    # localhost variants
    "http://localhost/ssrf-test",
    "HTTP://LOCALHOST/admin",
    "http://localhost:8080/internal",
    # 127.0.0.1 variants
    "http://127.0.0.1/secret",
    "http://127.0.0.1:9200/_cat/indices",
    # metadata service
    "http://169.254.169.254/latest/meta-data/",
    "HTTP://169.254.169.254/computeMetadata/v1/",
    # google metadata
    "http://metadata.google.internal/computeMetadata/v1/instance/",
    # private IP ranges
    "http://192.168.1.1/admin",
    "http://10.0.0.1/internal",
    "http://172.16.0.1/private",
    "http://172.31.255.255/secret",
    # 0.0.0.0
    "http://0.0.0.0/bypass",
    # IPv6 loopback
    "http://[::1]/admin",
    # file:// scheme
    "file:///etc/passwd",
    "file:///proc/self/environ",
    # mixed case bypass attempts
    "hTtP://127.0.0.1/bypass",
    "Http://LocalHost/bypass",
    # URL with embedded credentials
    "http://user:pass@127.0.0.1/secret",
    "http://user:pass@localhost/admin",
    # Double encoding / whitespace injection
    "http://127.0.0.1%2F/bypass",
    "http://localhost%09/bypass",
    # SVG with embedded SSRF URL (href/xlink)
    '<svg xmlns="http://www.w3.org/2000/svg"><image href="http://127.0.0.1/ssrf"/></svg>',
    '<svg><use xlink:href="http://localhost/evil"/></svg>',
    # URL with port variations
    "http://127.0.0.1:80/",
    "http://10.0.0.254:443/secret",
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