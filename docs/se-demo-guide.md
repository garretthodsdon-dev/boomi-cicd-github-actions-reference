# SE demo guide: Boomi CI/CD on GitHub Actions

For Solutions Engineers running this as a customer demo. Customers should read the
[README](../README.md); this guide is about preparing and presenting.

**The 30-second pitch:** *"Boomi is where you build and package. GitHub is where you review, approve,
promote and audit. Every release is a pull request, every promotion moves the exact same package with
environment-specific configuration applied automatically, and a failed release rolls itself back — on
GitHub-hosted runners, with no servers to run."*

---

## 1. Prepare the Boomi account (once)

1. **Three environments** with an online runtime attached to each, e.g. `Development` (TEST), `QA`
   (TEST), `Production` (PROD). A local runtime is fine for DEV; it must be running during the demo.
2. **A dedicated folder**, e.g. `Demo/GitHub-CICD`. Keep it small — every deployable component in the
   folder becomes part of the release.
3. **Create the sample components** (connector-free, so they never consume connector licenses):

   ```bash
   pip install -r requirements.txt
   export BOOMI_ACCOUNT_ID=... BOOMI_USERNAME=... BOOMI_API_TOKEN=...
   python -m boomi_release samples --folder-id <folder id> --package 1.0
   ```

   This creates `CICD Demo - Order Acknowledgement` (outputs JSON with `releaseVersion`, `environment`
   and `erpAckEndpoint`), `CICD Demo - Customer Sync`, the automated test
   `CICD Demo - Order Acknowledgement - Test` (returns JUnit XML; throws if `status` ≠ `ACKNOWLEDGED`),
   and its JSON profile — and packages both processes at 1.0. The folder ID is in the folder's URL /
   properties in the Boomi UI.
4. **A Platform API token**, ideally on a dedicated API user.

## 2. Prepare GitHub (once)

1. Create a repository from this template (private is fine for a demo).
2. Add the secrets and variables from the README. `BOOMI_FOLDER` accepts the path with or without the
   account's root folder name.
3. Rename `config/environments/Development.json`, `QA.json`, `Production.json` to your three Boomi
   environment names.
4. Create GitHub environments `dev`, `qa`, `prod`. If your plan supports required reviewers on the repo
   (public repos, or GitHub Enterprise for private), add yourself to `prod`.
5. Enable *Allow GitHub Actions to create and approve pull requests*.
6. **Set the baseline:** run *Boomi Release Request* → merge the PR → let *Boomi Release to DEV* finish →
   *Boomi Promote* → QA → *Boomi Promote* → PROD (any change ticket). Now 1.0 is live everywhere, so the
   live demo is an upgrade.

## 3. Before each demo

- [ ] DEV runtime online.
- [ ] No open release PR (or know which one is open).
- [ ] Tabs: Boomi Build (demo folder), Boomi Deployments, GitHub Actions, GitHub Pull requests, GitHub Releases.
- [ ] Decide which optional beats you'll show (section 5).

## 4. Demo script (~12 minutes)

| # | Show | Say |
|---|---|---|
| 1 | Boomi deploy screen | "Today someone clicks Deploy. Who approved it? Is PROD the same build as QA? Can you prove it to an auditor?" |
| 2 | Edit the Order Acknowledgement Message step (`releaseVersion` 1.0 → 1.1), save, **Create Packaged Component** 1.1 | "In Boomi, packaging is the developer's 'done' — an immutable, versioned artifact. Saving isn't a release." |
| 3 | *Actions → Boomi Release Request → Run* | "The pipeline asks Boomi what's been packaged — nothing exported or rebuilt. In production, Boomi triggers this itself or it runs on a schedule." |
| 4 | The release PR: version table (⬆️ 1.0 → 1.1, ✅ auto-test), *Files changed*, **Boomi lint** check | "This pull request *is* the change request — reviewable, discussable, and checked against our standards on the exact packaged version." |
| 5 | **Merge** → *Boomi Release to DEV*: job graph, Deploy summary (1.1 🚀, Customer Sync ⏸️ already active), configuration table, **Boomi automated tests** check | "Merge is the release approval. Only what changed moves, DEV gets DEV's configuration, and a test harness runs inside Boomi — if it fails, DEV rolls back automatically." |
| 6 | *Boomi Promote → QA*: summary (same package ID as DEV), QA configuration | "Promotion moves the exact artifact that passed DEV. It can't skip a stage. Environment-specific values come from the repo, not from someone editing extensions by hand." |
| 7 | *Boomi Promote → PROD* with a change ticket → **Releases** page | "PROD requires a change ticket, and every promotion is recorded as a release: who, when, which packages, which change." |
| 8 | Boomi Deployments for QA and PROD: version, notes (`promoted from … by … \| CHG…`), package ID | "Same artifact in every environment — and Boomi's own records carry the promotion trail." |
| 9 | *Boomi Rollback → PROD*, reason "demo" → summary (1.1 → 1.0) | "One click restores what ran before, straight from Boomi's deployment history — no rebuild. Then revert the PR so Git matches reality." |
| 10 | Close | The 30-second pitch. |

**Showing environment-specific configuration:** run `CICD Demo - Order Acknowledgement` in each
environment and open the execution's process log — the *Log Acknowledgement* step shows
`"environment":"DEV"` / `"QA"` / `"PROD"` and a different `erpAckEndpoint` from the same package. Or show
each environment's extensions (Process Properties) in Boomi's runtime management screens.

## 5. Optional beats

- **Quality gate fails:** clear the description of a process in the folder, package it, run the Release
  Request → the **Boomi lint** check fails (`PROCESS_DESCRIPTION_MISSING`, with `BOOMI_LINT_FAIL_ON`
  including `MINOR`). Restore the description, repackage, re-run → green.
- **Failed release rolls itself back:** set the Message step's `"status"` to `"PENDING"`, package,
  release, merge → the harness throws, the JUnit check shows the failure, and *Roll back DEV after failed
  tests* restores the previous version. Then show *Boomi Promote → QA* is **blocked** ("DEV runs X,
  release is Y"). Clean up: revert the PR and restore `ACKNOWLEDGED`.
- **Webhook from Boomi:** call `POST https://api.github.com/repos/<owner>/<repo>/dispatches` with
  `{"event_type":"boomi-package-created"}` (e.g. from a Boomi process) to show the request opening by itself.

## 6. Questions you'll get

- **"Why not keep Boomi XML in Git?"** The package is the artifact, owned and versioned by the platform;
  Git holds the release decision. Merging component XML as text is unsafe — Boomi Branch & Merge does
  component-aware merges. Exporting XML for code review is a possible add-on.
- **"Branching?"** Two kinds: development branching happens in Boomi (Branch & Merge); release branching
  is the release PR. Releases come from Boomi `main` by default. No per-environment Git branches — one
  artifact is promoted.
- **"Approvals / separation of duties?"** Merge approves the release; PROD needs a change ticket; GitHub
  environment required reviewers add a second person before QA/PROD jobs start (Enterprise for private
  repos; otherwise branch protection + required PR reviews).
- **"Jenkins / Azure DevOps?"** The CLI is plain Python against the Platform API — same commands in any CI.
- **"Per-runtime deployment?"** Boomi deploys to environments; runtime isolation = environment boundary.
- **"Is this a product feature?"** No — a reference implementation on the public Platform API, built on
  Boomi's native packaging, deployment, environments and extensions. Say so plainly.

## 7. Gotchas (learned the hard way)

- **The DEV runtime must be online**, or deploys and tests fail.
- **Test results may take a moment.** In our testing, a harness's Return Documents output sometimes wasn't
  retrievable until a minute or two after the execution completed; the test stage waits up to three minutes.
- **Bot-opened PRs:** pull requests opened by `GITHUB_TOKEN` don't run `pull_request` workflows normally;
  the Release Request starts validation itself and deletes the parked runs.
- **GitHub plan limits:** required reviewers and branch protection aren't available on free private
  repos — narrate the gate or use a public/Enterprise repo.
- **Configure extensions after the first deployment.** Extension values are tied to properties that a
  deployed process declares — deploy the release once before checking values in the Boomi UI.
- **Use a dedicated API user** — otherwise every Boomi record shows your own name.
- **Connector licenses:** deploying processes with connectors to several environments consumes licenses;
  the samples are connector-free for this reason.

## 8. Live coaching prompt (Claude in Chrome)

Paste into Claude in Chrome to be walked through the demo beat by beat. Replace the placeholders.

```text
You are my live demo coach for a Boomi CI/CD demo on GitHub Actions. Walk me through ONE beat at a
time; after each, wait for me to type "next". For each beat give CLICK (where), SHOW (what to point at)
and SAY (2–3 spoken sentences). Look at the page first and confirm I'm in the right place.
Never merge, approve, run workflows or change settings yourself unless I say "go". Never read out
secret values. If the screen doesn't match the script, stop and help me troubleshoot — don't invent facts.

Setup facts:
- GitHub repo: <REPO URL>. Workflows: Boomi Release Request, Boomi Validate (check "Boomi lint"),
  Boomi Release to DEV, Boomi Promote (QA or PROD; PROD needs a change ticket), Boomi Rollback.
- Boomi: <BOOMI ACCOUNT>, folder <FOLDER>. Processes: "CICD Demo - Order Acknowledgement" (output shows
  releaseVersion, environment, erpAckEndpoint), "CICD Demo - Customer Sync", test harness
  "CICD Demo - Order Acknowledgement - Test".
- Environments: DEV = <DEV ENV> (runtime <DEV RUNTIME>, must be online), QA = <QA ENV>, PROD = <PROD ENV>.

Pre-flight: DEV runtime online; latest "Boomi Release to DEV" run green; no stale release PR; note
whether the GitHub "prod" environment has required reviewers (if not, narrate the approval gate).

Beats: (1) the problem — manual deploys, no audit; (2) package a new version in Boomi; (3) run Boomi
Release Request; (4) review the release PR: version table, Files changed, Boomi lint check; (5) merge →
Boomi Release to DEV: deploy summary, configuration table, Boomi automated tests check; (6) Promote → QA:
same package ID, QA configuration; (7) Promote → PROD with a change ticket, then the Releases page;
(8) Boomi Deployments: notes and package IDs match; (9) Boomi Rollback → PROD, then revert the PR;
(10) close: "Boomi builds and packages; GitHub reviews, approves, promotes and audits."

If I type "qa", ask me three likely customer questions and critique my answers.
Start by greeting me and running the pre-flight.
```
