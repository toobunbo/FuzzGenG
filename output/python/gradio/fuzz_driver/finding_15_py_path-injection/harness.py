import atheris
import sys
import re
import os

from unittest.mock import patch, MagicMock


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

    re.compile("^/home/[^/]+/\\.", re.IGNORECASE),

    re.compile("/\\.\\./", re.IGNORECASE),

    re.compile("[/\\\\]\\.\\.[/\\\\]", re.IGNORECASE),

]
_RAISE_MESSAGE  = "PATH_INJECTION: Arbitrary file read via unsanitized path — captured={captured} pattern={matched_pattern}"
_TAINTED_PARAMS = [{"name": "value", "index": 1, "type": "str | Path"}]
# ========================================

# === ORACLE CONTEXT ===
# strategy         : patch_call
# patch_target     : builtins.open
# target_arg_index : 0
# target_arg_name  : file
# input_strategy   : direct_params
# signature        : def postprocess_image(format: str, value: np.ndarray | PIL.Image.Image | str | Path | None, cache_dir: str, watermark: WatermarkOptions | None)
# condition        : The path argument to open() contains '../' traversal sequences or is an absolute path pointing outside the cache directory (e.g., /etc/passwd, /etc/shadow, /proc/self/environ)
# capture_what     : The file path argument passed to open() — confirms whether a traversal or absolute path reaches the sink
# skip_hint        : not isinstance(value, (str, bytes)) or len(value) == 0
# ========================================


_SEED_CORPUS = [
    "../../../etc/passwd",
    "../../etc/shadow",
    "/etc/passwd",
    "/proc/self/environ",
    "/root/.bashrc",
    "/home/user/.ssh/id_rsa",
    "images/../../../etc/passwd",
    "cache/../../proc/self/cmdline",
    "..\\..\\etc\\passwd",
    "/etc/hosts",
    "valid_image.png/../../../etc/shadow",
    "subdir/..\\../etc/passwd",
]


def TestOneInput(data):
    fdp = atheris.FuzzedDataProvider(data)

    # INPUT GENERATION
    value = fdp.ConsumeUnicodeNoSurrogates(len(data))

    # SKIP CONDITION
    if not isinstance(value, (str, bytes)) or len(value) == 0:
        return

    # Use a fixed format and cache_dir for simplicity
    fmt = "png"
    cache_dir = "/tmp/gradio_cache"

    # MOCK SETUP
    mock_file = MagicMock()
    mock_file.__enter__ = MagicMock(return_value=mock_file)
    mock_file.__exit__ = MagicMock(return_value=False)
    mock_file.read = MagicMock(return_value=b"")
    mock_file.write = MagicMock(return_value=None)

    with patch("builtins.open", return_value=mock_file) as mock_open:
        try:
            postprocess_image(fmt, value, cache_dir, None)
        except RuntimeError:
            raise
        except Exception:
            pass

        # ORACLE CHECK — outside the function call try/except, inside patch context
        for call in mock_open.call_args_list:
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
                    raise RuntimeError(
                        _RAISE_MESSAGE.format(
                            captured=captured_str,
                            matched_pattern=pattern.pattern
                        )
                    )


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