# Verification record

Date: 29 October 2026  
Environment: Windows, Python 3.12.13, Node.js 24.19.0  
Applications: `http://127.0.0.1:8000` and https://margin-rag.vercel.app  
Scope: local build and short-lived hosted demo. Hosting-specific evidence is in `docs/DEPLOYMENT.md`.

## Checks completed

| Check | Observed result | Evidence |
| --- | --- | --- |
| Unit/API regressions | 46 passed | `artifacts/tests.xml`, `tests/test_app.py` |
| Python lint | `uv run ruff check .` passed | Local command output |
| Python formatting | `uv run ruff format --check .` passed | Local command output |
| JavaScript syntax | `node --check static/app.js` passed | Local command output |
| Real embedding model | BGE-small produced normalized 384-dimensional vectors | Live indexing and corpus evaluation |
| Supported retrieval | Correct file and page retrieved for 18 of 18 supported questions | `evaluation/results.json` |
| Live Gemini evaluation | 24/24 development checks passed: 18 supported answers and 6 abstentions | `evaluation/gemini-results.json` |
| Gemini browser flow | 13 assertions passed on the public deployment | `artifacts/gemini-browser-checks.json` |
| Unsupported retrieval | No passages for 5 of 6 unknown questions | `evaluation/results.json` |
| Browser interactions | 20 original local assertions and 20 hosted assertions passed | `artifacts/browser-checks.json`, `artifacts/hosted-browser-checks.json` |
| Dependency audit | Final audit reported no known vulnerabilities in the installed environment | `artifacts/dependency-audit.json` |
| Sample PDFs | All nine pages rendered and checked for overflow and extraction regressions | `artifacts/sample-pdf-contact-sheet.png` |
| PowerShell syntax | Start script parsed without errors | PowerShell parser output |

The corpus evaluation is a development fixture, not a held-out benchmark. It does not establish general answer accuracy. The unsupported GPU-brand question retrieved a related GPU policy, which is not evidence of the brand.

The initial 31-test baseline emitted an upstream Starlette deprecation warning. The current 46-test run passed without that warning after the Blob SDK brought in a compatible `httpx2` dependency.

## Browser coverage

Headless Chromium exercised the application at 1440×960, 820×1100, and 390×844. Checks included a valid PDF upload, sample loading with duplicate detection, question submission, source-page inspection, PDF download, single-document filtering, invalid-file feedback, and document deletion. Dialog dismissal was checked too. The mobile run also checked the source-evidence modal and the library menu's keyboard/inert state.

The runs found no horizontal page overflow. Screenshots were read after capture. Text contrast was increased during review, keyboard upload access was added, and the hidden mobile library was removed from focus navigation. A tablet line-break issue was corrected so suggestion text does not join words.

This was not a complete WCAG audit. No screen-reader session or axe audit ran. Reduced motion was enabled during the repeatable browser checks.

The temporary browser script is at `C:/Users/rajve/AppData/Local/Temp/margin-browser.cjs` on the build machine. Its recorded output and screenshots are included in the project. For a portable manual repeat, follow the demo sequence in `docs/SUBMISSION.md` at the viewport sizes above.

## OCR delegation review

The review used `ocr delegate preview --format json` and matching rules from `ocr delegate rule --format json`. Pi inspected the new source against the empty repository baseline, then repeated the review after fixes. No OCR-managed model endpoint or separate review provider was used.

Initial local-build scope accounting: **22 preview-listed files reviewed, none skipped within that list**. OCR excluded another **18 files** by extension, binary type, or default path rules. Of those, **17 received manual source, rendered-output, or test-evidence review**. The generated `uv.lock` was not read line by line, so it is the **one explicitly skipped manual file**. Its installation was verified with `uv sync --frozen`, and the resolved environment was dependency-audited. Initial build total: **39 files reviewed, 1 skipped for line-by-line review**. The later Vercel changes have a separate scoped review record in `docs/DEPLOYMENT.md`.

The preview-listed review covered the application, frontend assets, evaluation code and results, packaging/startup code, CI/container configuration, and recorded test evidence. The manually added scope covered `.env.example`, the three Markdown guides, all six screenshots, the PDF contact sheet, three sample PDFs, `start.cmd`, `static/favicon.svg`, and `tests/test_app.py`.

### Findings resolved

| Severity | Location | Evidence and resolution |
| --- | --- | --- |
| Low (dependency hygiene) | `pyproject.toml:8`, resolved Pillow dependency | The first audit reported Pillow 11.3.0 advisories. Application exploitability was not established. FastEmbed was updated to 0.9.1 and Pillow to 13.0.0 in the lockfile. The repeated audit reported no known vulnerabilities. |
| Medium | `static/app.js`, `setSidebarOpen` | A translated-offscreen mobile library remained keyboard-focusable. The closed library now uses `inert`, with resize and Escape handling. Browser checks cover that state. |
| Low | `app/main.py:109`, `Question.valid_ids` | UUID validation accepted uppercase IDs but ownership checks compared unnormalized strings. IDs are now canonicalized before lookup. A regression test submits an uppercase owned ID. |
| Low | `app/rag.py:179`, generated-response parsing | A non-object JSON response was not rejected at the parsing boundary. It now produces an explicit invalid-provider-response error. A mocked-provider regression covers it. |
| Low | `app/rag.py:194`, quote validation | Case-folded comparison could accept a changed-case quote as an exact excerpt. Quote checks now preserve case and normalize whitespace only. A negative test covers changed-case text. |
| Low | `static/index.html`, suggestion cards | Hiding line breaks on tablet could join adjacent words. Spaces before the breaks now preserve word boundaries. |

There are no unresolved blocking findings within the reviewed local-demo scope. This is not a claim of production security or complete review of excluded/generated files.

## Checks not completed

- **General Gemini accuracy/availability:** a replacement key now works, and the 24-case development evaluation plus public API/browser checks passed. This does not establish general accuracy or an availability guarantee. One initial small probe failed provider-response handling before the later successful checks. The earlier key's HTTP 402 result is retained as historical evidence.
- **Docker build/run:** Docker CLI is installed, but the Docker Desktop engine was not running. The daemon connection failed. The image recipe was inspected but not built or exercised.
- **Remote CI:** the workflow exists, but no GitHub repository has been published and no remote checks ran.
- **Language servers:** diagnostics were attempted for JavaScript and the changed Python files. The TypeScript language-server command was missing, and `pylsp` closed before initialization. These checks are unavailable, not clean. Ruff and the test suite ran separately from JavaScript syntax checks.
- **Production service:** not built. A short-lived public demo is now running on Vercel and has been checked in the browser. Anonymous workspace cookies and in-process limits are still not sufficient controls for a production multi-user service.

## Re-run locally

```powershell
uv sync --frozen
uv run ruff check .
uv run ruff format --check .
uv run pytest -q --junitxml=artifacts/tests.xml
node --check static/app.js
uv run python -m scripts.evaluate
uv run pip-audit --progress-spinner off --format json --output artifacts/dependency-audit.json
```

Use `--gemini` only when you intend to send the fictional corpus passages to Google and consume API quota. Review the individual answers, especially refusals and claims with multiple possible source pages.
