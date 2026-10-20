# Boomi CI/CD with GitHub Actions

A reference implementation of release management for [Boomi](https://boomi.com) integrations using
GitHub Actions: release requests as pull requests, automated quality checks and tests, promotion from
DEV to QA to PROD with environment-specific configuration, and one-click rollback — all on GitHub-hosted
runners calling the public Boomi Platform API. No Jenkins, no servers.

> **Community reference implementation — not an official Boomi product and not supported by Boomi.**
> Review it, adapt it, and test it in non-production environments before relying on it.

## How it works

Boomi is where integrations are **built and packaged**. GitHub is where releases are **reviewed,
approved, promoted and audited**.

```
Boomi: developer creates a Packaged Component (versioned, immutable)
   │
   ▼
Boomi Release Request ──► pull request "Boomi release" with a table of version changes
                             │  Boomi Validate: lint check on the exact packaged versions
                             ▼
                          merge = release approved
                             │
Boomi Release to DEV:  deploy DEV ─► apply DEV config ─► automated tests ──(fail)──► automatic rollback
                             │
Boomi Promote:         DEV ─► QA ─► PROD   same package IDs · target config applied · change ticket for PROD
Boomi Rollback:        any environment, one click, from Boomi's own deployment history
```

Principles:

- **One artifact, every environment.** Promotion deploys the exact package ID that ran in the previous
  environment. Nothing is rebuilt or re-exported between stages.
- **Git holds the release decision, not a copy of the code.** `release/release.json` pins one Packaged
  Component per Boomi component; every change to it is a reviewed pull request.
- **No skipping stages.** A release can only be promoted from an environment where it is already live.
- **Configuration per environment, not per build.** Values that differ per environment live in
  `config/environments/<environment>.json` and are applied to Boomi environment extensions automatically.
- **A failed release doesn't stay live.** Failed automated tests roll DEV back automatically, and any
  environment can be rolled back in one click.

## Workflows

| Workflow | Trigger | What it does |
|---|---|---|
| **Boomi Release Request** | manual · `repository_dispatch` (`boomi-package-created`) · optional schedule | Finds the newest Packaged Component of each deployable component in a Boomi folder and opens/updates a release pull request |
| **Boomi Validate** | pull request · started by Release Request | Lints the packaged version of every component (rules in [`boomi_release/lint_rules.json`](boomi_release/lint_rules.json)) |
| **Boomi Release to DEV** | merge to `main` that changes `release/release.json` | Lint → deploy DEV → DEV configuration → automated tests → automatic rollback on failure |
| **Boomi Promote** | manual: QA or PROD (change ticket required for PROD) | Promotes what runs in the previous environment, applies target configuration, records a GitHub Release |
| **Boomi Rollback** | manual: environment, optional component, reason | Restores what ran before the current package was introduced |
| **Unit tests** | push / pull request | Tests the tooling itself (no Boomi access needed) |

## Governance and audit trail

| Question | Where the answer lives |
|---|---|
| What changed in this release? | The release pull request (version table) and the `release/release.json` diff |
| Did it meet standards? | **Boomi lint** check on the pull request; lint report on each run |
| Who approved it? | Pull request merge (and, if configured, branch protection reviews) |
| Did it pass tests? | **Boomi automated tests** check (JUnit) on the DEV run |
| Who promoted it to QA / PROD, under which change? | Promote run summary, GitHub Release notes, and the Boomi deployment notes (`promoted from … by … \| CHG…`) |
| What is running in PROD right now? | GitHub Releases (latest `prod-…`), and Boomi deployment history |
| What was rolled back, and why? | Rollback run summary and the Boomi deployment notes (`ROLLBACK a → b by … \| reason`) |

For a second-person approval before QA/PROD, add **required reviewers** to the `qa`/`prod` GitHub
environments (available for private repositories on GitHub Enterprise; on other plans, use branch
protection with required pull request reviews on `main`).

## Prerequisites

- A Boomi account with environments for DEV, QA and PROD, each with an attached, online runtime.
- A Boomi user with Platform API access and a **Platform API token** (created under *Settings*; SSO-only
  users can't call the API with a password, so use a token). A dedicated API user for the pipeline is recommended, so Boomi's own records show
  the pipeline's identity while GitHub records the human who approved.
- A GitHub repository created from this template.

## Setup

1. **Create your repository** from this template (*Use this template*).
2. **Secrets** — *Settings → Secrets and variables → Actions → Secrets*:

   | Secret | Value |
   |---|---|
   | `BOOMI_ACCOUNT_ID` | Your Boomi account ID, e.g. `mycompany-AB12CD` |
   | `BOOMI_USERNAME` | API user name (the `BOOMI_TOKEN.` prefix is added automatically) |
   | `BOOMI_API_TOKEN` | The user's Platform API token |

3. **Variables** — same page, *Variables* tab:

   | Variable | Example | Purpose |
   |---|---|---|
   | `BOOMI_FOLDER` | `Integrations/Orders` | Boomi folder (and subfolders) whose components are released |
   | `BOOMI_ENV_DEV` / `BOOMI_ENV_QA` / `BOOMI_ENV_PROD` | `Development` / `QA` / `Production` | Boomi environment names |
   | `BOOMI_TEST_RUNTIME` | `DEV Runtime 1` | Runtime in the DEV environment that executes test harnesses (unset = no test stage) |
   | `BOOMI_LINT_FAIL_ON` | `MAJOR,MINOR` | Lint priorities that fail the build (unset = report only) |

4. **GitHub environments** — *Settings → Environments*: create `dev`, `qa`, `prod` (add reviewers where
   your plan supports it).
5. **Allow Actions to open pull requests** — *Settings → Actions → General → Workflow permissions →
   Allow GitHub Actions to create and approve pull requests*.
6. **Environment configuration** — rename the files in `config/environments/` to your Boomi environment
   names and set your values (see below).
7. **Run** *Actions → Boomi Release Request* to open your first release pull request.

## Day-to-day flow

1. Build and test in Boomi, then **create a Packaged Component** with a version and notes.
2. *Boomi Release Request* runs (manually, from Boomi via `repository_dispatch`, or on a schedule) and
   opens or updates the **release pull request**.
3. Review the version table and the **Boomi lint** check, then **merge** — the release goes to DEV and
   the automated tests run.
4. *Boomi Promote* → **QA**; after QA sign-off, *Boomi Promote* → **PROD** with a change ticket.
5. If something goes wrong: *Boomi Rollback* for the affected environment, then revert the release pull
   request (or merge a fix) so `main` reflects reality.

## Environment-specific configuration

`config/environments/<Boomi environment name>.json` holds the values that differ per environment. After
every DEV deploy and every promotion they are written to that environment's **Boomi environment
extensions** (a partial update — other extension values are left alone):

```json
{
  "properties": {
    "DPP_ENVIRONMENT_LABEL": "QA",
    "DPP_ERP_ACK_ENDPOINT": "https://erp-qa.example.com/api/order-ack"
  }
}
```

`properties` are Dynamic Process Properties that your processes declare as extensible. Secrets never
belong in Git: use `"$env:NAME"` and map `NAME` from a GitHub (environment) secret in the workflow,
e.g. `ERP_API_KEY: ${{ secrets.ERP_API_KEY }}`. A missing secret fails the run instead of writing an
empty value.

## Automated tests

A process named **`<Process Name> - Test`** in the released folder is the automated test for
`<Process Name>`. It should run the process under test (for example through a Process Call), assert the
result, **return JUnit XML from a Return Documents step**, and **throw an Exception** when an assertion
fails. The pipeline packages the harness at the release's version, deploys it to DEV, executes it, and
publishes the JUnit results as a GitHub check. Harnesses are never promoted beyond DEV.

## Running the tooling locally

```bash
pip install -r requirements.txt
export BOOMI_ACCOUNT_ID=... BOOMI_USERNAME=... BOOMI_API_TOKEN=...

python -m boomi_release discover --folder "Integrations/Orders"
python -m boomi_release lint --fail-on MAJOR
python -m boomi_release deploy  --env Development --dry-run
python -m boomi_release promote --from Development --to QA --label QA --dry-run
python -m boomi_release rollback --env QA --reason "bad release" --dry-run
python -m boomi_release -h
```

## FAQ

**Why not store Boomi XML in Git and build from source?** A Boomi Packaged Component is already an
immutable, versioned artifact managed by the platform. Text-merging component XML (which references
other components by ID) is error-prone; Boomi's own Branch & Merge handles component-aware merges. Git
holds the release decision; exporting XML to Git for review is a possible add-on.

**What about Boomi Branch & Merge?** Development branching happens in Boomi. Releases are taken from
the `main` branch by default (`discover --branch` changes this).

**Can I target a specific runtime?** Boomi deploys to environments; every runtime attached to an
environment receives the deployment. Use separate environments for runtime isolation.

**Which component types are released?** Every deployable type listed in
[`boomi_release/manifest.py`](boomi_release/manifest.py) — processes, API Service components, Flow
Services, process routes, trading partner groups, custom libraries and certificates.

**Jenkins, Azure DevOps, GitLab?** The `boomi_release` CLI is plain Python against the Platform API; the
same commands work from any CI system.

## Limitations

- Lint inspects the top-level packaged component, not every referenced component.
- Environment configuration covers Dynamic Process Properties; connection and other extension types can
  be added in `boomi_release/deploy.py`.
- Test-harness results can take a short time to become retrievable after an execution completes; the test
  stage waits up to three minutes per harness.

## License

[Apache License 2.0](LICENSE).
