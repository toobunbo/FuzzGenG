import atheris
import sys
import re
import os

from unittest.mock import patch, MagicMock



with atheris.instrument_imports():

    from testcode.BenchmarkTest00156 import BenchmarkTest00156_post


# === FIXED CONTRACTS (DO NOT MODIFY) ===
_COMPILED_PATTERNS = [

    re.compile("__import__\\s*\\(", re.IGNORECASE),

    re.compile("os\\.system\\s*\\(", re.IGNORECASE),

    re.compile("subprocess", re.IGNORECASE),

    re.compile("open\\s*\\(", re.IGNORECASE),

    re.compile("exec\\s*\\(", re.IGNORECASE),

    re.compile("builtins", re.IGNORECASE),

    re.compile("globals\\s*\\(", re.IGNORECASE),

    re.compile("locals\\s*\\(", re.IGNORECASE),

]
_RAISE_MESSAGE  = "PY/CODE-INJECTION: User-controlled input reached eval() sink — captured={captured} pattern={matched_pattern}"
_TAINTED_PARAMS = [{"name": "BenchmarkTest00156", "index": -1, "type": "str"}]
# ========================================

# === ORACLE CONTEXT ===
# strategy         : patch_call
# patch_target     : testcode.BenchmarkTest00156.eval
# target_arg_index : 0
# target_arg_name  : None
# input_strategy   : flask_view
# signature        : def BenchmarkTest00156_post(self)
# condition        : The string passed to eval() contains user-controlled code injection patterns such as __import__, os.system, exec, or other dangerous builtins, indicating user input reached the eval sink
# capture_what     : The first argument passed to eval() — the expression string being evaluated
# skip_hint        : False
# ========================================


# === SEED CORPUS — bypass-oriented, derived from trigger_patterns ===
_SEED_CORPUS = [
    "__import__('os').system('id')",
    "exec(__import__('os').popen('id').read())",
    "os.system('cat /etc/passwd')",
    "__import__('subprocess').call(['id'])",
    "open('/etc/passwd').read()",
    "globals()['__builtins__'].__import__('os').system('id')",
    "locals()['__builtins__']['exec']('import os; os.system(\"id\")')",
    "builtins.__import__('os').system('whoami')",
    "__import__('builtins').exec('import os')",
    "exec(open('/etc/passwd').read())",
]


def TestOneInput(data):
    fdp = atheris.FuzzedDataProvider(data)

    # 1. INPUT GENERATION
    # Single tainted param of type str — consume all remaining bytes
    tainted_input = fdp.ConsumeUnicodeNoSurrogates(len(data))

    # 2. SKIP CONDITION
    # skip_hint is False — no skip condition needed, proceed with all inputs

    # 3. MOCK SETUP
    mock_return = MagicMock()
    mock_return.__str__ = lambda self: "0"

    with patch("testcode.BenchmarkTest00156.eval", return_value=mock_return) as mock_eval:

        # Build a mock Flask request with the tainted input
        mock_request = MagicMock()
        mock_request.form.get.return_value = tainted_input
        mock_request.args.get.return_value = tainted_input
        mock_request.values.get.return_value = tainted_input
        mock_request.json = {"BenchmarkTest00156": tainted_input}
        mock_request.data = tainted_input.encode("utf-8", errors="replace")
        mock_request.form.__getitem__ = lambda self, key: tainted_input
        mock_request.args.__getitem__ = lambda self, key: tainted_input

        # Build a mock self (Flask view instance)
        mock_self = MagicMock()

        # 4. FUNCTION CALL
        with patch("testcode.BenchmarkTest00156.request", mock_request):
            try:
                BenchmarkTest00156_post(mock_self)
            except RuntimeError:
                raise
            except Exception:
                pass

        # 5. ORACLE CHECK — outside the function call try/except, inside patch context
        for call in mock_eval.call_args_list:
            # Extract the first argument passed to eval()
            captured = None
            if call.args:
                captured = call.args[0]
            elif call.kwargs:
                captured = call.kwargs.get("source", call.kwargs.get("expression", call.kwargs.get("code", None)))

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