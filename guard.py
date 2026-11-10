#!/usr/bin/env python3
"""Shopify Theme Guard: checks a theme for hardcoded secrets, unescaped customer input and unpinned third-party scripts."""
import fnmatch
import os
import re
import sys

THEME_DIRS = ("assets", "blocks", "config", "layout", "locales", "sections", "snippets", "templates")
EXTS = (".liquid", ".json", ".js", ".css", ".html")

# --- secrets ---------------------------------------------------------------
TOKENS = [
    (r"shp(at|ca|pa|ss)_[a-fA-F0-9]{32}", "Shopify access token or app secret"),
    (r"(sk|rk)_live_[0-9a-zA-Z]{20,}", "Stripe live secret key"),
    (r"AKIA[0-9A-Z]{16}", "AWS access key"),
    (r"gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,}", "GitHub token"),
    (r"xox[abpr]-[A-Za-z0-9-]{10,}", "Slack token"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "private key"),
    (r"SG\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}", "SendGrid API key"),
]
TOKENS = [(re.compile(p), n) for p, n in TOKENS]
HMAC = re.compile(r"\|\s*hmac_sha(?:1|256)\s*:\s*(['\"])([^'\"]{8,})\1")
NAMED = re.compile(
    r"""(?ix)
    (?:assign\s+|\b)
    ([a-z_]*(?:secret|api_?key|access_?token|private_?key|password|signing_?key|client_?secret)[a-z_]*)
    \s*(?:=|:)\s*(['"])([A-Za-z0-9+/=_\-]{16,})\2""")

# --- unescaped customer input ----------------------------------------------
RISKY = [
    "search.terms", "predictive_search.terms", "comment.author", "comment.email", "form.author", "form.email",
    "form.body", "form.name", "form.first_name", "form.last_name", "customer.first_name", "customer.last_name",
    "customer.name", "customer.email", "cart.note", "cart.attributes", "line_item.properties",
]
SAFE = {"escape", "escape_once", "url_encode", "url_escape", "url_param_escape", "json", "md5", "sha1", "sha256",
        "hmac_sha1", "hmac_sha256", "handle", "handleize", "strip_html", "size", "base64_encode", "money",
        "date", "times", "plus", "minus", "divided_by", "modulo", "round", "ceil", "floor", "abs"}
OUTPUT = re.compile(r"\{\{-?\s*(.*?)\s*-?\}\}", re.S)

# --- unpinned third-party scripts --------------------------------------------
URL = re.compile(r"""(?:https?:)?//[^\s'"()<>]+""")


def unpinned(url):
    u = re.sub(r"^(https?:)?//", "", url).split("?")[0].split("#")[0]
    host, _, path = u.partition("/")
    if "@latest" in u:
        return "loads @latest"
    if host == "unpkg.com" or (host == "cdn.jsdelivr.net" and path.startswith("npm/")):
        pkg = path[4:] if path.startswith("npm/") else path
        parts = pkg.split("/")
        name = "/".join(parts[:2]) if pkg.startswith("@") else parts[0]
        if "@" not in name.lstrip("@"):
            return "has no version"
    if host == "cdn.jsdelivr.net" and path.startswith("gh/"):
        repo = "/".join(path.split("/")[1:3])
        if "@" not in repo:
            return "has no version"
    if host == "cdn.babylonjs.com" and not re.match(r"v\d", path) and path.endswith(".js"):
        return "has no version"
    if host == "esm.sh" and "@" not in path.split("/")[0].lstrip("@"):
        return "has no version"
    return None


def mask(s):
    return s[:4] + "…" if len(s) > 8 else "…"


def line_of(text, pos):
    return text.count("\n", 0, pos) + 1


def check(path, text, enabled):
    found = []  # (level, line, title, message)
    lines = text.split("\n")

    def ignored(n):
        return "theme-guard-ignore" in lines[n - 1]

    if "secrets" in enabled:
        for rx, name in TOKENS:
            for m in rx.finditer(text):
                n = line_of(text, m.start())
                if not ignored(n):
                    found.append(("error", n, "Hardcoded secret", f"Looks like a {name} ({mask(m.group(0))}). Theme files can be read by anyone with theme or repo access: move it out of the theme and rotate it."))
        for m in HMAC.finditer(text):
            n = line_of(text, m.start())
            if not ignored(n):
                found.append(("error", n, "Hardcoded signing key", f"hmac signing key written in the code ({mask(m.group(2))}). Read it from a shop metafield instead, and rotate it, since anyone with theme or repo access can see it."))
        for m in NAMED.finditer(text):
            n = line_of(text, m.start())
            val = m.group(3)
            if ignored(n) or re.fullmatch(r"(x+|0+|your[_-].*|test.*|example.*)", val, re.I):
                continue
            if val.startswith("AIza"):  # Google browser keys are public by design; they just need restricting
                found.append(("warning", n, "Google API key in theme", f"'{m.group(1)}' ({mask(val)}) is visible to every visitor. That's normal for Maps keys, but make sure it's restricted to your store's domains and only the APIs it needs in Google Cloud, or anyone can run up your bill."))
                continue
            found.append(("error", n, "Hardcoded secret", f"'{m.group(1)}' is set to a literal value ({mask(val)}). Keep keys out of theme code: use a metafield or an app setting, and rotate this one."))

    if "escape" in enabled and path.endswith((".liquid", ".html")):
        for m in OUTPUT.finditer(text):
            expr = m.group(1)
            parts = [p.strip() for p in re.split(r"\|(?![^'\"]*['\"][^'\"]*$)", expr)]
            head = parts[0]
            var = next((r for r in RISKY if head == r or head.startswith(r + ".") or head.startswith(r + "[")), None)
            if not var:
                continue
            filters = {p.split(":")[0].strip() for p in parts[1:]}
            if filters & SAFE:
                continue
            n = line_of(text, m.start())
            if not ignored(n):
                found.append(("warning", n, "Unescaped customer input", f"{{{{ {head} }}}} prints text a visitor can control without escaping. Add | escape (or | url_encode inside a URL) so it can't inject HTML or script."))

    if "pinning" in enabled and path.endswith((".liquid", ".html", ".js")):
        for m in URL.finditer(text):
            why = unpinned(m.group(0))
            if not why:
                continue
            n = line_of(text, m.start())
            if not ignored(n):
                found.append(("warning", n, "Unpinned third-party script", f"{m.group(0)} {why}. Pin an exact version so a new release (or a hijacked package) can't change your storefront without you knowing."))
    return found


def main():
    root = os.environ.get("TG_PATH") or "."
    enabled = {c.strip() for c in (os.environ.get("TG_CHECKS") or "secrets,escape,pinning").split(",") if c.strip()}
    ignore = [g.strip() for g in (os.environ.get("TG_IGNORE") or "").replace("\n", ",").split(",") if g.strip()]
    fail_on = (os.environ.get("TG_FAIL_ON") or "secrets").strip()
    results = []
    for d in THEME_DIRS:
        base = os.path.join(root, d)
        for dirpath, _, files in os.walk(base):
            for fn in sorted(files):
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, root).replace(os.sep, "/")
                if not fn.endswith(EXTS) or any(fnmatch.fnmatch(rel, g) for g in ignore):
                    continue
                if fn.endswith(".min.js") or os.path.getsize(full) > 2_000_000:
                    continue
                try:
                    text = open(full, encoding="utf-8", errors="replace").read()
                except OSError:
                    continue
                for level, n, title, msg in check(rel, text, enabled):
                    results.append((rel, level, n, title, msg))

    gh = os.environ.get("GITHUB_ACTIONS") == "true"
    for rel, level, n, title, msg in results:
        if gh:
            print(f"::{level} file={rel},line={n},title={title}::{msg}")
        else:
            print(f"{level.upper():7} {rel}:{n}  {title}: {msg}")

    errors = sum(1 for r in results if r[1] == "error")
    warnings = len(results) - errors
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as s:
            s.write(f"## Shopify Theme Guard\n\n{errors} secret finding(s), {warnings} warning(s).\n\n")
            if results:
                s.write("| File | Line | Finding |\n|---|---|---|\n")
                for rel, level, n, title, msg in results[:200]:
                    s.write(f"| `{rel}` | {n} | {title} |\n")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as o:
            o.write(f"secrets={errors}\nwarnings={warnings}\n")
    print(f"\n{errors} secret finding(s), {warnings} warning(s).")
    if fail_on == "any" and results or fail_on == "secrets" and errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
