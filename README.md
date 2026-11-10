# Shopify Theme Guard

[![Marketplace](https://img.shields.io/badge/Marketplace-Shopify%20Theme%20Guard-ffffff?style=flat&logo=github&logoColor=white&labelColor=000000)](https://github.com/marketplace/actions/shopify-theme-guard)
[![Release](https://img.shields.io/github/v/release/Creative-Source-Graphics-LLC/shopify-theme-guard?style=flat&labelColor=000000&color=ffffff)](https://github.com/Creative-Source-Graphics-LLC/shopify-theme-guard/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-ffffff?style=flat&labelColor=000000)](LICENSE)
![Shopify themes](https://img.shields.io/badge/Shopify-themes-ffffff?style=flat&logo=shopify&logoColor=white&labelColor=000000)
![Language: Liquid](https://img.shields.io/badge/Language-Liquid-ffffff?style=flat&labelColor=000000)
![Checks: security](https://img.shields.io/badge/Checks-security-ffffff?style=flat&labelColor=000000)

A GitHub Action that checks a Shopify theme for three problems that are easy to miss in review and costly in production:

- **Hardcoded secrets**: API tokens, app secrets, private keys and `hmac_sha256` signing keys written straight into Liquid, JSON or JS. Anyone with access to the theme or the repo can read them.
- **Unescaped customer input**: things a visitor controls, like `search.terms`, `comment.author` or `customer.email`, printed without `| escape`. That's how HTML or script gets injected into a page.
- **Unpinned third-party scripts**: libraries loaded from `@latest` or with no version (unpkg, jsDelivr, esm.sh, Babylon.js). A new release, or a hijacked package, can change your storefront without anyone touching the theme.

Findings show up as annotations on the exact lines in pushes and pull requests, plus a summary on the run page.

## What it looks like

```text
ERROR   snippets/subscription-link.liquid:12  Hardcoded secret: 'secret_key' is set to a literal value (a1b2…). Keep keys out of theme code: use a metafield or an app setting, and rotate this one.
WARNING snippets/active-facets.liquid:55  Unescaped customer input: {{ search.terms }} prints text a visitor can control without escaping. Add | escape (or | url_encode inside a URL) so it can't inject HTML or script.
WARNING sections/product-3d.liquid:6  Unpinned third-party script: https://unpkg.com/@google/model-viewer/dist/model-viewer.min.js has no version. Pin an exact version so a new release (or a hijacked package) can't change your storefront without you knowing.
```

Secret values are never printed in full.

## Usage

Add `.github/workflows/theme-guard.yml` to your theme repo:

```yaml
name: Theme Guard

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  guard:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: Creative-Source-Graphics-LLC/shopify-theme-guard@v1
```

It only reads files, so `contents: read` is all it needs.

## Options

| Input | Default | What it does |
|---|---|---|
| `path` | `.` | Folder that holds the theme (the one with `sections/`, `snippets/`, `layout/` ...). |
| `checks` | `secrets,escape,pinning` | Which checks to run. |
| `ignore` | | File patterns to skip, comma or newline separated, for example `assets/vendor-*.js`. |
| `fail-on` | `secrets` | Fail the run on `secrets` only, on `any` finding, or `none` (report only). |

Outputs: `secrets` and `warnings`, the number of findings of each kind.

To accept a single line on purpose, put `theme-guard-ignore` on that line, for example in a Liquid comment.

## What it checks

**Secrets** (errors): Shopify access tokens and app secrets, Stripe live keys, AWS access keys, GitHub and Slack tokens, SendGrid keys, private keys, literal `hmac_sha1` / `hmac_sha256` keys, and variables named like `secret`, `api_key`, `access_token`, `password` or `signing_key` set to a literal value. Google browser keys (`AIza...`) are reported as a warning instead: they're public by design, but should be restricted to your domains in Google Cloud.

**Escaping** (warnings): `{{ ... }}` output that starts with `search.terms`, `predictive_search.terms`, `comment.*`, `form.*` fields, `customer` names and email, `cart.note`, `cart.attributes` or `line_item.properties` and has no escaping filter such as `escape`, `url_encode` or `json`.

**Pinning** (warnings): script and stylesheet URLs on unpkg, jsDelivr (npm and GitHub), esm.sh and the Babylon.js CDN with no version, and any URL using `@latest`.

Files ending in `.min.js` and files over 2 MB are skipped. Python 3 comes with GitHub's Ubuntu, macOS and Windows runners, so there's nothing to install.

## Fixing a hardcoded key

1. Rotate the key with the service that issued it. If it was ever committed, assume it's been seen.
2. Store the new key outside the theme code, for example in a shop metafield, and read it in Liquid with `shop.metafields.namespace.key.value`.
3. Remove the old value from the theme.

## License

MIT, by [Creative Source Graphics, LLC](https://creativesourcegraphics.com).
