# AUTO-GENERATED ATHERIS HARNESS
# rule_id  : py/path-injection
# function : postprocess_image
# file     : gradio/image_utils.py
# ================================================================
import atheris
import sys
import re
import os

from unittest.mock import patch, MagicMock, mock_open


import builtins


with atheris.instrument_imports():

    from gradio.image_utils import postprocess_image


# === FIXED CONTRACTS (DO NOT MODIFY) ===
_COMPILED_PATTERNS = [

    re.compile("\\.\\./", re.IGNORECASE),

    re.compile("\\.\\.[/\\\\]", re.IGNORECASE),

    re.compile("^/etc/", re.IGNORECASE),

    re.compile("^/proc/", re.IGNORECASE),

    re.compile("^/root/", re.IGNORECASE),

    re.compile("/\\.\\./", re.IGNORECASE),

    re.compile("\\.\\.\\\\", re.IGNORECASE),

]
_RAISE_MESSAGE  = "PATH_INJECTION: unsanitized path traversal reached file sink — captured={captured} pattern={matched_pattern}"
_TAINTED_PARAMS = [{"name": "value", "index": 1, "type": "str | Path"}, {"name": "cache_dir", "index": 2, "type": "str"}]
# ========================================

# === ORACLE CONTEXT ===
# strategy         : patch_call
# patch_target     : builtins.open
# target_arg_index : 0
# target_arg_name  : file
# input_strategy   : direct_params
# signature        : def postprocess_image(format: str, value: np.ndarray | PIL.Image.Image | str | Path | None, cache_dir: str, watermark: WatermarkOptions | None)
# condition        : The path passed to open() contains path traversal sequences (../) or absolute paths pointing outside the cache directory, confirming unsanitized user input reaches the file sink
# capture_what     : the file path argument passed to open(), revealing path traversal
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
#    - Patch `builtins.open` using `with patch(...) as mock_get:`.
#    - Return a realistic MagicMock so the function continues past the patched call.
#
# 4. ORACLE CHECK
#    - After the call, iterate mock_get.call_args_list.
#    - For each call: check call.args[0] first,
#      fall back to call.kwargs.get("file").
#    - Match against every pattern in _COMPILED_PATTERNS.
#    - On match → raise RuntimeError(_RAISE_MESSAGE)
#
# 5. EXCEPTION HANDLING
#    - except RuntimeError: raise   → never swallow oracle signals
#    - except Exception:    return  → only around the target function call
# ==========================================


def TestOneInput(data):
    fdp = atheris.FuzzedDataProvider(data)

    if len(data) < 4:
        return

    # Split buffer: ~60% for value, ~40% for cache_dir
    total = len(data)
    value_len = max(1, int(total * 0.6))
    cache_len = max(1, total - value_len)

    value = fdp.ConsumeUnicodeNoSurrogates(value_len)
    cache_dir = fdp.ConsumeUnicodeNoSurrogates(cache_len)

    # skip_hint: not isinstance(value, (str, bytes)) or len(value) == 0
    if not isinstance(value, (str, bytes)) or len(value) == 0:
        return

    # Build a realistic mock for open() that returns a file-like object
    mock_file = MagicMock()
    mock_file.__enter__ = MagicMock(return_value=mock_file)
    mock_file.__exit__ = MagicMock(return_value=False)
    mock_file.read = MagicMock(return_value=b"")
    mock_file.write = MagicMock(return_value=0)

    with patch("builtins.open", return_value=mock_file) as mock_open_obj:
        try:
            postprocess_image("png", value, cache_dir, None)
        except RuntimeError:
            raise
        except Exception:
            pass

        # Oracle check — OUTSIDE the function call try/except, INSIDE patch context
        for call in mock_open_obj.call_args_list:
            # Extract the file path argument
            captured = None
            if call.args:
                captured = call.args[0]
            if captured is None:
                captured = call.kwargs.get("file")
            if captured is None:
                continue

            captured_str = str(captured)

            for pattern in _COMPILED_PATTERNS:
                if pattern.search(captured_str):
                    matched_pattern = pattern.pattern
                    raise RuntimeError(
                        _RAISE_MESSAGE.format(
                            captured=captured_str,
                            matched_pattern=matched_pattern,
                        )
                    )


# === SEED CORPUS — bypass-oriented, derived from trigger_patterns ===
_SEED_CORPUS = [
    # Path traversal sequences in value
    "../../../etc/passwd",
    "..%2F..%2F..%2Fetc%2Fshadow",
    "/etc/passwd",
    "/proc/self/environ",
    "/root/.ssh/id_rsa",
    "images/../../etc/hosts",
    "..\\..\\windows\\system32\\config",
    "valid_image/../../../etc/crontab",
    "%2e%2e%2f%2e%2e%2fetc%2fpasswd",
    "images%2F..%2F..%2Fetc%2Fpasswd",
    "/proc/1/cmdline",
    "cache/../../../root/.bashrc",
]


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