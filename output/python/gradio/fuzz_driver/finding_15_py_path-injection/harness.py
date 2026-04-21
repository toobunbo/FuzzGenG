import atheris
import sys
import re
import os

from unittest.mock import patch, MagicMock
from pathlib import Path


with atheris.instrument_imports():

    from gradio.image_utils import postprocess_image


# === FIXED CONTRACTS (DO NOT MODIFY) ===
_COMPILED_PATTERNS = [

    re.compile("\\.\\./", re.IGNORECASE),

    re.compile("\\.\\.[/\\\\]", re.IGNORECASE),

    re.compile("^/etc/", re.IGNORECASE),

    re.compile("^/proc/", re.IGNORECASE),

    re.compile("^/root/", re.IGNORECASE),

    re.compile("^/home/", re.IGNORECASE),

    re.compile("^/var/", re.IGNORECASE),

    re.compile("^/usr/", re.IGNORECASE),

    re.compile("^/tmp/[^/]+\\.(conf|key|pem|env|cfg|ini|json|py|sh|txt)$", re.IGNORECASE),

    re.compile("(?:^|/)\\.\\.(?:/|$)", re.IGNORECASE),

]
_RAISE_MESSAGE  = "PATH_INJECTION: Arbitrary file read via unsanitized path in postprocess_image — captured={captured} pattern={matched_pattern}"
_TAINTED_PARAMS = [{"name": "value", "index": 1, "type": "str | Path"}]
# ========================================

# === ORACLE CONTEXT ===
# strategy         : patch_call
# patch_target     : gradio.image_utils.open
# target_arg_index : 0
# target_arg_name  : None
# input_strategy   : direct_params
# signature        : def postprocess_image(format: str, value: np.ndarray | PIL.Image.Image | str | Path | None, cache_dir: str, watermark: WatermarkOptions | None)
# condition        : The path argument to open() contains path traversal sequences ('../') or is an absolute path pointing outside the cache directory, indicating arbitrary file read exploitation
# capture_what     : The file path argument passed to open() at the sink in postprocess_image
# skip_hint        : not isinstance(value, (str, Path)) or (isinstance(value, str) and not value)
# ========================================


_SEED_CORPUS = [
    "../../../etc/passwd",
    "../../secret.conf",
    "/etc/shadow",
    "/home/user/.ssh/id_rsa",
    "/var/log/syslog",
    "/tmp/config.env",
    "/proc/self/environ",
    "/root/.bashrc",
    "images/../../../etc/hosts",
    "uploads/../../usr/bin/python",
    "/tmp/secret.key",
    "foo/bar/../../../../../../etc/passwd",
    "..\\..\\windows\\system32\\config",
    "/usr/local/etc/config.ini",
    "/tmp/app.json",
    "valid_image.png/../../../etc/passwd",
]


def TestOneInput(data):
    fdp = atheris.FuzzedDataProvider(data)

    # Split buffer: reserve some bytes for format and cache_dir, rest for value
    format_str_len = min(fdp.ConsumeIntInRange(1, 10), len(data) // 4 + 1)
    format_str = fdp.ConsumeString(format_str_len)

    cache_dir_len = min(fdp.ConsumeIntInRange(1, 20), len(data) // 4 + 1)
    cache_dir = fdp.ConsumeString(cache_dir_len)

    # Use seed corpus or fuzz-generated value
    if fdp.ConsumeBool() and _SEED_CORPUS:
        seed_idx = fdp.ConsumeIntInRange(0, len(_SEED_CORPUS) - 1)
        value = _SEED_CORPUS[seed_idx]
    else:
        value = fdp.ConsumeString(len(data))

    # SKIP CONDITION: value must be a non-empty string or Path
    if not isinstance(value, (str, Path)) or (isinstance(value, str) and not value):
        return

    # Normalize format string to something reasonable
    if not format_str or not format_str.isalpha():
        format_str = "png"

    # Normalize cache_dir
    if not cache_dir:
        cache_dir = "/tmp/gradio_cache"

    # Set up a realistic mock for open()
    mock_file = MagicMock()
    mock_file.__enter__ = MagicMock(return_value=mock_file)
    mock_file.__exit__ = MagicMock(return_value=False)
    mock_file.read = MagicMock(return_value=b"")

    with patch("gradio.image_utils.open", return_value=mock_file) as mock_open:
        try:
            postprocess_image(format_str, value, cache_dir, None)
        except RuntimeError:
            raise
        except Exception:
            pass

        # ORACLE CHECK — outside the function call try/except, inside patch context
        for call in mock_open.call_args_list:
            # Check positional args first
            captured = None
            if call.args:
                captured = call.args[0]
            elif call.kwargs:
                captured = call.kwargs.get("file") or call.kwargs.get("name") or call.kwargs.get("path")

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