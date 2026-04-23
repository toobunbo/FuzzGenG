import atheris
import sys
import re
import os

from unittest.mock import patch, MagicMock


import lxml.etree


with atheris.instrument_imports():

    from testcode.BenchmarkTest00021 import BenchmarkTest00021_post


# === FIXED CONTRACTS (DO NOT MODIFY) ===
_COMPILED_PATTERNS = [

    re.compile("\"[^\"]*\"\\s*=\\s*\"", re.IGNORECASE),

    re.compile("\\[\\s*\\d+\\s*\\]", re.IGNORECASE),

    re.compile("//[a-zA-Z*]", re.IGNORECASE),

    re.compile("\\]\\s*\\|\\s*//", re.IGNORECASE),

    re.compile("or\\s+\"[^\"]*\"\\s*=\\s*\"", re.IGNORECASE),

    re.compile("and\\s+\"[^\"]*\"\\s*=\\s*\"", re.IGNORECASE),

    re.compile("\"\\s*or\\s+", re.IGNORECASE),

    re.compile("\"\\s*and\\s+", re.IGNORECASE),

]
_RAISE_MESSAGE  = "XPATH_INJECTION: XPath expression contains unsanitized user-controlled metacharacters — captured={captured} pattern={matched_pattern}"
_TAINTED_PARAMS = [{"name": "BenchmarkTest00021", "index": -1, "type": "str"}]
# ========================================

# === ORACLE CONTEXT ===
# strategy         : patch_call
# patch_target     : lxml.etree._Element.xpath
# target_arg_index : 0
# target_arg_name  : None
# input_strategy   : flask_view
# signature        : def BenchmarkTest00021_post(self)
# condition        : The XPath expression argument contains XPath metacharacters that were not sanitized (double quotes, square brackets, forward slashes used as injection vectors, or XPath boolean operators) derived from the cookie value
# capture_what     : The XPath expression string argument passed to the xpath() call, containing unsanitized user-controlled input
# skip_hint        : False
# ========================================


# === SEED CORPUS — bypass-oriented, derived from trigger_patterns ===
_SEED_CORPUS = [
    '" or "a"="a',
    '" or "1"="1',
    '"] | //user',
    '//user[1]',
    '" and "a"="a',
    'admin" or "1"="1',
    '"] | //*',
    '//node[1]',
    '" or "x"="x" and "y"="y',
    'test"] | //password',
    '" Or "a"="a',
    '"] | //accounts[1]',
]
# ========================================


def TestOneInput(data):
    fdp = atheris.FuzzedDataProvider(data)

    # 1. INPUT GENERATION
    # Single tainted param (cookie value as str), consume all bytes
    cookie_value = fdp.ConsumeUnicodeNoSurrogates(len(data))

    # 2. SKIP CONDITION
    # skip_hint is False, so no skip condition needed — process all inputs

    # 3. MOCK SETUP
    # We need to simulate a Flask request context with the cookie value
    # The function reads from request.cookies.get("BenchmarkTest00021")
    # We patch lxml.etree._Element.xpath to intercept the XPath call

    mock_element = MagicMock(spec=lxml.etree._Element)
    mock_element.xpath.return_value = []

    # Build a mock Flask request with the cookie
    mock_request = MagicMock()
    mock_request.cookies.get.return_value = cookie_value

    # Create a mock self (the view instance)
    mock_self = MagicMock()

    with patch("lxml.etree._Element.xpath", return_value=[]) as mock_xpath:
        with patch("testcode.BenchmarkTest00021.request", mock_request):
            with patch("lxml.etree.parse") as mock_parse:
                # Make lxml.etree.parse return a mock tree whose getroot() returns
                # something whose xpath method is the patched one
                mock_tree = MagicMock()
                mock_root = MagicMock(spec=lxml.etree._Element)
                mock_root.xpath = mock_xpath
                mock_tree.getroot.return_value = mock_root
                mock_parse.return_value = mock_tree

                # 4. FUNCTION CALL
                try:
                    BenchmarkTest00021_post(mock_self)
                except RuntimeError:
                    raise
                except Exception:
                    pass

        # 5. ORACLE CHECK — outside the function call try/except, inside patch context
        for call in mock_xpath.call_args_list:
            captured = None
            if call.args:
                captured = call.args[0]
            else:
                captured = call.kwargs.get("_path") or call.kwargs.get("path") or call.kwargs.get("xpath")

            if captured is None:
                continue

            captured_str = str(captured)
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