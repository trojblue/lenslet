# Dependency security review — 2026-10-26

Scope: Lenslet's frontend lockfile, Python runtime/development dependencies,
optional extras, build tooling, and default outbound TLS clients. This is a
dated advisory review, not a guarantee against unknown vulnerabilities or an
audit of other applications on the host.

## Findings and changes

| Finding | Resolution |
| --- | --- |
| Vitest 4.1.11 pulled vulnerable `@vitest/mocker` | Pin Vitest 4.1.12 and refresh its transitive packages. [Injection advisory](https://github.com/advisories/GHSA-qxg6-89mg-rqv8), [Windows traversal advisory](https://github.com/advisories/GHSA-xp26-3454-mjgp). |
| Pillow constraints pinned 12.1.1; the active environment had 12.3.0 | Require Pillow 13 and pin 13.0.0. Recent fixes include [image-decoder memory corruption](https://github.com/python-pillow/Pillow/security/advisories/GHSA-v9pv-5gc8-w2m6) and [TIFF heap disclosure](https://github.com/python-pillow/Pillow/security/advisories/GHSA-c6hw-5grf-ff96). This raises Lenslet's Python minimum to 3.11. |
| No minimum certifi version; pip 26.2 still bundled an affected CA | Require certifi >=2026.10.19; pin 2026.10.23. Bootstrap pip 26.2.2 from the [Python team's hash-verified wheel](https://discuss.python.org/t/information-for-python-users-regarding-emudhra-emsign-ca-certificate-security-incident/109576). Setup rejects older pip before installing. |
| urllib downloads inherited the stale Conda trust store | Default HTTP/HTTPS opens now share a verified certifi SSL context, including HTTP-to-HTTPS redirects. Custom contexts remain explicit caller responsibility. A regression check verifies hostname checking, required certificate validation, context reuse, and absence of the compromised G3 root. |
| Optional dependencies included filelock 3.29.1 and setuptools 81.0.0 | Set security floors of 4.2.1 and 84.1.0 respectively; constrain validated versions to 4.2.4 and 84.2.1. |
| Frontend manifests allowed unreviewed direct-version drift and old Node versions | Pin direct versions; retain the integrity-bearing lockfile; require patched Node 22.23.4/24.22.1/26.12.1 release lines; disable dependency lifecycle scripts by default. [Node security release](https://nodejs.org/en/blog/vulnerability/october-2026-security-releases). |
| Python constraints used unsupported extras syntax | Change `uvicorn[standard]==...` to `uvicorn==...`; the package requirement still requests standard extras. |
| Build backend was unpinned | Pin Hatchling 1.32.4 in build requirements and dev extras; build with the audited environment using `--no-isolation`. |
| Base Python 3.13.13 lacked the latest interpreter fixes | Build private CPython 3.13.18 from the [official source release](https://www.python.org/downloads/release/python-31318/), verify its published SHA-256, and rebase `.venv` onto it. Update Ubuntu ca-certificates to 20260816ubuntu0.24.04.1. |

## Incident applicability

- **eMudhra:** relevant to outbound HTTPS and package installers, even though
  Lenslet serves HTTP locally by default. The application and installer fixes
  above address their default trust stores. See [Mozilla's incident notice](https://blog.mozilla.org/security/2026/10/20/protecting-firefox-users-following-the-compromise-of-emudhra-intermediate-certificates/).
- **PHP2Shell:** no PHP application, runtime dependency, or PHP executable was
  found in this workspace environment. The [PHP advisory](https://www.php.net/archive/2026.php)
  concerns PHP web runtimes, not FastAPI or browser-side React. Separate reverse
  proxies or unrelated hosted PHP applications were not inspected.
- **React2Shell:** the lockfile has React 18 and no `react-server-dom-*` or
  Next.js packages. Lenslet serves a static Vite client; the affected
  [React Server Components surface](https://react.dev/blog/2025/12/03/critical-security-vulnerability-in-react-server-components)
  is absent.
- **TanStack supply-chain compromise:** this lockfile uses Query and Virtual,
  which the [maintainer's postmortem](https://tanstack.com/blog/npm-supply-chain-compromise-postmortem)
  identifies as unaffected. Router/Start affected packages are absent.
- **LiteLLM October compromise:** `litellm` is absent from the inspected
  installed and freshly resolved Lenslet dependency trees. The compromised
  release was [1.107.0](https://docs.litellm.ai/blog/security-incident-oct-21-2026-attack-chain).

## Audit evidence and limits

- `npm audit`: zero known vulnerabilities after the update, including dev dependencies.
- `npm audit signatures`: 180 installed packages had verified registry signatures;
  54 had verified attestations. Signatures do not prove a maintainer's release is benign.
- `pip-audit`: zero known vulnerabilities in the 76 installed packages in the
  project virtual environment, including pip and build tooling.
- Live TLS verification: both the patched interpreter's default SSL context and
  Lenslet's certifi context rejected the researcher's four published G3B test
  endpoints (direct/cross-signed, logged/unlogged). Both accepted the PyPI
  positive control. All failures were certificate-verification errors, not
  timeouts. [Test endpoint documentation](https://emudhra.we-have-a-problem.com/).
- Separate resolution and audit of all extras, including GPU embedding packages:
  97 packages, zero known vulnerabilities. GPU packages were resolved/audited,
  not installed or exercised on hardware in the clean environment.
- The original environment contained local CUDA PyTorch/TorchVision versions and
  a development Unibox build that PyPI auditing could not identify. Fresh public
  versions were audited instead; no claim is made about those local builds.
- The original shared Gradio/PyTorch constraints conflict with patched
  Pillow/setuptools. Their original versions were restored; use `.venv` for
  Lenslet. The shared Conda environment is **not** cleared by this review.
- Version pins are not a complete Python lockfile. Optional dependencies and
  platform-specific distributions must be re-resolved and audited when changed.
  OS libraries, custom CA bundles, browsers, external services, and historical
  credential compromise require separate review.

## Validation

Frontend build and packaged asset mirror, wheel and sdist build, 719 frontend
tests, TypeScript, repository lint, dependency consistency, TLS regression checks,
and browser acceptance passed. Browser acceptance reported its existing nonfatal
folder re-entry anchor warning.

The final Python suite on Python 3.13.18 reported 868 passing, one expected failure, and
three failures. All three reproduced with the previous shared dependencies:
two existing frontend import-contract violations in RankingApp, and the corrupt
image export test expecting 422 where preindexing removes the image and returns
404. These unrelated failures were not rewritten to make the audit green.

## Using the patched workspace

Run `source .venv/bin/activate` before launching, testing, or building Lenslet.
This environment uses the private interpreter at
`/fsx/yada/.local/share/lenslet/python-3.13.18`; it does not replace Conda's Python.
Its installed dependency graph passes `pip check`. Do not use the shared
Conda `lenslet` command as a substitute for this environment.

Build outputs are `dist/lenslet-0.4-py3-none-any.whl` and
`dist/lenslet-0.4.tar.gz`. The wheel contains the regenerated frontend.
