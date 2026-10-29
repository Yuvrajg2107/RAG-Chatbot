# Hosted demo and friend handoff

Verified: 29 October 2026

## Live application

**https://margin-rag.vercel.app**

The frontend and backend are deployed together in the Vercel project **margin-rag**, under the current owner's Hobby team. The backend is **Python 3.12 with FastAPI**, running as a Vercel Function in `iad1`. There is no separate backend hosting account to transfer.

The current deployment generates answers with **Gemini 3.5 Flash-Lite**, using retrieved PDF passages and checked page citations. The latest development evaluation passed 24/24 question checks: 18 supported answers and 6 abstentions.

## Gemini key result

The replacement key passed authentication and generated valid, cited answers. It is configured as a **sensitive, server-side production environment variable** named `GEMINI_API_KEY`. It is not embedded in browser code or included in the source ZIP. The ignored local `.env` was updated too. No billing settings were changed and no credits were purchased.

The completed Gemini fixture run passed 24/24 checks. Public API checks verified a generated capstone-deadline answer with a page-3 citation and refusal to invent a GPU brand. A further 13 browser assertions passed, including the generated-answer label and mobile citation modal. Existing workspace documents were preserved after the credential deployment. Evidence is in `evaluation/gemini-results.json`, `artifacts/gemini-live-checks.json`, and `artifacts/gemini-browser-checks.json`.

One initial supported-question probe failed provider-response handling. A follow-up probe and the full evaluation passed; the initial failure was not diagnosed as a code defect or erased from the record. These are point-in-time development checks, not an availability or general-accuracy guarantee.

The earlier key was valid but returned **HTTP 402 / RESOURCE_EXHAUSTED** because prepaid credits were depleted. It was never deployed and is no longer configured locally. `artifacts/gemini-key-check.json` retains that historical result without any key value.

Public requests now consume the configured key's API quota. Hosting being free does not make Google's API usage free. Set appropriate provider quotas or spending controls before sharing widely. Because the working key was shared in chat, rotate it before the final handoff and replace the production secret with the rotated value. Your friend should ultimately use a key from their own Google project. To keep a local installation in evidence mode, blank `GEMINI_API_KEY` in `.env` before restarting it.

## Where the data lives

Local installations continue using `data/margin.sqlite3`. The Vercel deployment instead saves one private SQLite snapshot per anonymous workspace in **Vercel Blob**. It does not rely on a function's temporary disk for persistence.

- PDF limit: **3 MB per file** on Vercel, below the platform's 4.5 MB request/response ceiling. Local installations retain the 10 MB limit.
- Hosted workspace limit: **32 MB** including PDFs and vectors, with the existing maximum of 20 PDFs.
- The hosted workspace cookie uses HttpOnly and Secure flags with SameSite Strict. Keep using the same hostname and browser profile to retain access.
- Each published snapshot has a new object name. A conditional-create lease serializes writes across function instances. Expired leases can recover after three minutes if a function terminates unexpectedly.
- Immutable object names avoid stale overwritten databases in CDN caches. Old snapshots are removed after a successful write. Cleanup failures are logged and retried on a later mutation.
- Empty document-list requests do not allocate stored workspaces. Blob snapshots are cached only as an optimization, never as the authoritative copy.
- The embedding model is bundled during the build and loaded offline at runtime. The optional `hf-xet` download accelerator is excluded through uv's dependency configuration to keep the Python function within the enforced build-size limit. Downloads use ordinary HTTPS instead.

The app uses anonymous bearer-cookie isolation, not user accounts. It has no account recovery or automatic workspace-retention policy. Avoid confidential documents. After the demonstration, the owner can delete the project and its dedicated Blob store through Vercel; nothing is scheduled to delete itself.

## Free hosting for a few days

The account was checked and is on **Vercel Hobby**. No Pro trial or paid database was enabled. This setup can serve a small, non-commercial submission demo within the shared Hobby allowances.

[Vercel's Blob pricing documentation](https://vercel.com/docs/vercel-blob/usage-and-pricing) includes 1 GB/month of Blob storage on Hobby, with operation and transfer limits. Hobby does not charge for Blob overages: access is blocked when the included limits are exceeded. Those limits are shared with other projects in the account, so this is not an unlimited-capacity or uptime promise. Check the Usage dashboard during the demo.

The app's limits and in-process throttling bound ordinary requests, but there is no distributed abuse-control service. This is a short-lived demonstration, not a production document service. Do not add a billable Gemini key to a public demo without considering provider spending limits and stronger access controls.

A separate Render backend is possible, but unnecessary here. Its [free services sleep after 15 minutes and lose local filesystem changes](https://render.com/docs/free). Current [Hugging Face Spaces documentation](https://huggingface.co/docs/hub/spaces-overview) requires a paid plan to create Docker Spaces even though CPU Basic has no hourly charge. Neither simplifies this handoff compared with the single Vercel project already running.

## Transfer option A: move the existing resources

No ownership transfer has been initiated. Your friend's account/team details are still needed.

1. Confirm that both accounts meet Vercel's [project-transfer permissions and destination requirements](https://vercel.com/docs/projects/transferring-projects). The current docs require ownership of the source team and membership of the destination team, and mention a valid destination payment method. Do not assume every Hobby-to-Hobby transfer is a one-click operation.
2. Transfer the **margin-rag project**, which contains both the frontend and Python backend.
3. Transfer the **margin-rag-workspaces Blob store separately**. Vercel explicitly lists Blob as a resource that does not move automatically with a project. Use Storage → the store → Settings → Transfer Store, subject to the destination's permissions. See [storage transfer documentation](https://vercel.com/docs/storage).
4. Reconnect the store to the destination project and verify `BLOB_STORE_ID` and the provider-managed Blob credentials. Do not send tokens in chat or copy unrelated account credentials.
5. Replace any inherited Google key with your friend's own key. Redeploy and retest document upload and deletion. Check the citations and workspace separation too.
6. Confirm the production alias and any submission links after the transfer.

The backend code needs no separate transfer to another host. Storage and provider credentials are the additional handoff items.

## Transfer option B: deploy a fresh copy under your friend

For a clean, free Hobby setup, your friend can redeploy the source ZIP under their own account instead of negotiating a cross-team transfer. Existing uploaded documents will not migrate, but the fictional sample PDFs are included and can be loaded again.

From a fresh extracted copy, with uv and the Vercel CLI installed:

```powershell
vercel login
vercel project add margin-rag-friend
vercel link --yes --project margin-rag-friend
vercel blob create-store margin-rag-workspaces --access private --yes --environment production --environment preview
vercel env add BLOB_STORE_ID production
vercel env add BLOB_STORE_ID preview
vercel deploy --prod --yes
```

For each `BLOB_STORE_ID` prompt, use the store ID returned by the create-store command. It is an identifier, not the read/write token. The store connection adds the server-side credentials. Use a different project name if that account already has one with the example name.

The ZIP excludes `.env`, `.env.local`, `.vercel/`, user uploads, and model caches. It includes the Vercel configuration and the script that downloads the public embedding model during the cloud build. No GitHub repository or public source repository is required for this CLI deployment.

To enable Gemini later:

```powershell
vercel env add GEMINI_API_KEY production
vercel deploy --prod --yes
```

Enter the key through the CLI prompt rather than putting it in a command, screenshot, or committed file. This is configuration, not a billing setup step. The key's Google project still needs usable quota.

## Hosted verification

- **46 local regression tests passed**, including cloud storage contracts and provider-error handling.
- **20 browser assertions passed against the public URL**, at viewport widths of 1440, 820, and 390 pixels. The run checked actual PDF upload and indexed sample loading. It also verified cited answers and downloads, with document filtering and deletion. Mobile coverage included the source-evidence modal.
- A sample workspace retained **all three document IDs after a new production deployment**, proving that its PDFs did not depend on the old function's memory or disk.
- A separate anonymous session could not list, download, delete, or query selected documents from that workspace. Those four ownership checks passed against the live service.
- A cited capstone-deadline answer still pointed to page 3 after redeployment.
- The final installed dependency audit reported no known vulnerabilities. This is not a production-security certification.
- **Live Gemini generation is enabled.** The replacement key passed the 24-case fixture evaluation and direct checks on the public deployment. Thirteen additional browser assertions verified the generated-answer flow.

The original evidence-mode hosting checks remain in `artifacts/tests.xml`, `artifacts/hosted-browser-checks.json`, `artifacts/hosted-api-checks.json`, and `docs/screenshots/hosted/`. Current generated-answer evidence is in `evaluation/gemini-results.json`, the Gemini reports named above, and `docs/screenshots/gemini/`. No session cookies or API-key values are included.

The Gemini-enabled production deployment completed successfully and was aliased to the live URL. The earlier evidence-mode deployment had a CLI connection reset during finalization; its readiness was independently checked before it was reported as deployed.

## Hosting review scope and limits

OCR delegation was repeated for the hosting changes, with matching rules for the affected source and explicit rules for the tests that OCR excludes by default. The workspace preview listed 29 reviewable files. Of those, 18 new or changed files were examined. Eleven were verified unchanged against the prior build's SHA-256 baseline and skipped for repeat review.

Of the 26 preview exclusions, 12 were reviewed manually: the four Markdown guides, six hosted screenshots, and two test files. Thirteen unchanged assets were compared with the original source ZIP and skipped for repeat review. The changed, generated `uv.lock` was not read line by line. It was installed with `uv sync --frozen` and the resolved packages were audited. Overall hosting scope: **30 reviewed, 24 unchanged/skipped, 1 generated-lockfile line-review skip**. Every previewed path is accounted for, but skipped files are not being called newly reviewed.

Resolved findings and deployment constraints:

| Severity | File/line | Evidence and fix |
| --- | --- | --- |
| High correctness | `app/store.py:33` | Local function disk cannot provide durable hosted SQLite storage. The private snapshot backend now persists data outside the function. Three original document IDs survived an actual redeployment. |
| Medium correctness | `app/rag.py:16`, `app/main.py:138` | The original 10 MB upload setting exceeded Vercel's 4.5 MB payload limit. Hosted limits and browser validation now use 3 MB. An oversized live upload returned 413. |
| Medium correctness | `app/cloud_store.py:124` | The SDK accepts at most 1,000 deletions per call. Cleanup now batches old snapshots. A regression fixture exercises more than 1,000 stale snapshots without turning a committed write into an error. |
| Medium deployment | `pyproject.toml:14` | The first Python bundles exceeded the builder's enforced 225 MB limit. Excluding the optional `hf-xet` dependency allowed a successful optimized build, while retaining ordinary HTTPS downloads and the same tested embeddings. |
| Low error handling | `app/rag.py:221` | The supplied key returned HTTP 402 rather than the previously handled 429 quota response. Both statuses now produce a clear quota/prepaid-credit error. A mocked regression covers 402. |

The hosted checks also rejected cross-origin mutations and returned 404 for five private/config/model URL probes, including `.env` and `.env.local`. No key values were printed or included in the deployment-source manifest. These are scoped checks, not a claim that every possible attack was tested.

Language-server diagnostics were attempted for all affected Python and JavaScript source files. Python's server failed to initialize, and the TypeScript language-server command was unavailable. Those checks remain unavailable, not clean. Docker and remote GitHub CI are still unverified. Ruff, the 46-test suite, real Vercel builds, and the public browser/API checks ran separately.

The rival-model writing check failed with exit 1. Manual editing and the bundled copy linter were used instead. No completed second-model writing pass is claimed for this hosting guide.

### Gemini activation review

The credential update did not change application logic. The only Python edit added two sanitized Gemini evidence filenames to the submission packager. That change was reviewed with OCR delegation rules and the existing packaging regression tests.

The activation preview listed 32 reviewable files and 29 exclusions. Six reviewable files were examined: the packager and five evaluation/evidence outputs. The other 26 matched the saved source hashes and were skipped for repeat review. Four updated guides and three new screenshots received manual review. The other 22 excluded files were unchanged from the prior build and were not re-reviewed. Activation scope: **13 reviewed, 48 unchanged/skipped**, with no new code findings. This is a scoped result, not a fresh full-repository review.

The deployment manifest contained 17 source files and excluded all environment files. The production key was stored as a sensitive secret. The updated source ZIP was checked for environment files and the actual key value. Python language-server diagnostics remained unavailable, so no successful language-server check is claimed.
