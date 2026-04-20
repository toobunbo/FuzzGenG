import atheris
import sys
import re
import os

from unittest.mock import patch, MagicMock



with atheris.instrument_imports():

    from gradio.image_utils import postprocess_image


# === FIXED CONTRACTS (DO NOT MODIFY) ===
_COMPILED_PATTERNS = [

    re.compile("\\.\\./", re.IGNORECASE),

    re.compile("\\.\\.[/\\\\]", re.IGNORECASE),

    re.compile("^/(?!tmp|var/tmp)[a-zA-Z]", re.IGNORECASE),

    re.compile("/etc/", re.IGNORECASE),

    re.compile("/proc/", re.IGNORECASE),

    re.compile("/root/", re.IGNORECASE),

    re.compile("\\.\\.%2[fF]", re.IGNORECASE),

    re.compile("(?:^|/)\\.\\.(?:/|$)", re.IGNORECASE),

]
_RAISE_MESSAGE  = "PATH_INJECTION: Tainted path traversal payload reached open() sink — captured={captured} pattern={matched_pattern}"
_TAINTED_PARAMS = [{"name": "value", "index": 1, "type": "BinaryExpr"}, {"name": "format", "index": 0, "type": "str"}]
# ========================================

# === ORACLE CONTEXT ===
# strategy         : patch_call
# patch_target     : gradio.image_utils.open
# target_arg_index : 0
# target_arg_name  : None
# input_strategy   : direct_params
# signature        : def postprocess_image(format: str, value: BinaryExpr, cache_dir: str, watermark: BinaryExpr)
# condition        : The file path passed to open() contains path traversal sequences (../) or absolute paths that escape the intended cache_dir, confirming path injection exploitation
# capture_what     : The file path argument passed to open() at the sink, constructed from user-provided value/format parameters
# skip_hint        : not isinstance(value, (str, bytes)) or len(value) == 0
# ========================================


# === PATCH_CALL SKELETON ===
# 1. INPUT GENERATION
#    - Generate inputs for tainted params using FuzzedDataProvider.
#    - For a SINGLE str param: consume ALL remaining bytes as one string:
#        text = fdp.ConsumeUnicodeNoSurrogates(len(data))
#    - For MULTIPLE params: split buffer proportionally with ConsumeIntInRange,
#      then consume each part — do NOT use ConsumeIntInRange to pick a seed index.
#    - DO NOT embed a seed list inside TestOneInput or use ConsumeBool() to
#      select from a hardcoded list — this breaks coverage-guided mutation.
#      Seeds are managed externally in _SEED_CORPUS and written to disk at startup.
#
# 2. SKIP CONDITION
#    - Apply skip_hint early, return immediately if not met.
#
# 3. MOCK SETUP
#    - Patch `gradio.image_utils.open` using `with patch(...) as mock_get:`.
#    - Return a realistic MagicMock so the function continues past the patched call.
#
# 4. ORACLE CHECK
#    - After the call, iterate mock_get.call_args_list.
#    - For each call: check call.args[0] first,
#      fall back to call.kwargs.get("None").
#    - Match against every pattern in _COMPILED_PATTERNS.
#    - On match → raise RuntimeError(_RAISE_MESSAGE)
#
# 5. EXCEPTION HANDLING
#    - except RuntimeError: raise   → never swallow oracle signals
#    - except Exception:    return  → only around the target function call
# ==========================================


def TestOneInput(data):
    fdp = atheris.FuzzedDataProvider(data)

    # Split buffer proportionally among tainted params
    total = len(data)
    # Allocate roughly half to format, half to value
    format_len = max(1, total // 3)
    value_len = max(1, total // 3)
    format_str = fdp.ConsumeUnicodeNoSurrogates(format_len)
    value_bytes = fdp.ConsumeBytes(value_len)
    cache_dir = "/tmp/gradio_cache"

    # Apply skip_hint: value must be non-empty bytes or str
    if not isinstance(value_bytes, (str, bytes)) or len(value_bytes) == 0:
        return

    mock_file = MagicMock()
    mock_file.__enter__ = MagicMock(return_value=mock_file)
    mock_file.__exit__ = MagicMock(return_value=False)
    mock_file.read = MagicMock(return_value=b"")

    with patch("gradio.image_utils.open", return_value=mock_file) as mock_open:
        try:
            postprocess_image(format_str, value_bytes, cache_dir, None)
        except RuntimeError:
            raise
        except Exception:
            return

        # Oracle check — outside the try/except above
        for call in mock_open.call_args_list:
            # Check positional arg first, then keyword fallback
            captured = None
            if call.args and len(call.args) > 0:
                captured = call.args[0]
            if captured is None:
                captured = call.kwargs.get(None) or call.kwargs.get("file") or call.kwargs.get("name")

            if captured is None:
                continue

            if not isinstance(captured, str):
                try:
                    captured = str(captured)
                except Exception:
                    continue

            for pattern in _COMPILED_PATTERNS:
                if pattern.search(captured):
                    matched_pattern = pattern.pattern
                    raise RuntimeError(
                        _RAISE_MESSAGE.format(captured=captured, matched_pattern=matched_pattern)
                    )


# === SEED CORPUS — bypass-oriented, derived from trigger_patterns ===
_SEED_CORPUS = [
    # Path traversal with mixed encoding
    "../../etc/passwd\x00.png",
    # Double dot with URL encoding
    "..%2Fetc%2Fpasswd",
    # Absolute path bypass attempt
    "/etc/shadow",
    # Nested traversal
    "foo/../../etc/passwd",
    # Windows-style traversal
    "..\\..\\etc\\passwd",
    # Unicode homoglyph / lookalike for slash
    "..\u2215etc\u2215passwd",
    # Null byte injection with traversal
    "../../../proc/self/environ\x00.jpg",
    # Root path escape
    "/root/.ssh/id_rsa",
    # Mixed case traversal
    "../ETC/passwd",
    # Double encoding
    "..%252Fetc%252Fpasswd",
    # Traversal with format extension
    "../../etc/passwd.png",
    # Traversal via symlink-like path
    "/var/tmp/../../etc/passwd",
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