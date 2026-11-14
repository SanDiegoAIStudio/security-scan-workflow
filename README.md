# security-scan-workflow

A reusable GitHub Actions workflow that runs four security scans: a dependency audit, CodeQL, a TruffleHog secret scan and a Trivy container scan. Each scan is switched by an input, every job asks for the least permission it needs, and the SARIF reports are kept as downloadable artifacts. It is for anyone who wants one `uses:` line in their own repository instead of wiring four scanners by hand.

## Quick start

Add this job to a workflow in your repository, for example `.github/workflows/ci.yml`. The same job, inside a complete workflow file, is in [`examples/caller.yml`](examples/caller.yml).

```yaml
jobs:
  security:
    permissions:
      actions: read
      contents: read
      security-events: write
    # Replace `v1` with a full commit id for the strictest pin.
    uses: SanDiegoAIStudio/security-scan-workflow/.github/workflows/security-scan.yml@v1
    with:
      working_directory: "."
      run_container_scan: true
```

The caller's `permissions:` block must grant at least what the called jobs declare, so the block above lists the most any job asks for (see [What each job does](#what-each-job-does)). Keep the whole block even when you turn some scans off.

If you would rather not depend on this repository at run time, copy `.github/workflows/security-scan.yml` into your own `.github/workflows/` folder and call it with `uses: ./.github/workflows/security-scan.yml`. A copy keeps its commit-pinned actions, so you still get the pins.

This repository calls its own workflow on [`examples/sample-app`](examples/sample-app) in `.github/workflows/self-test.yml`, on push to `main` and on manual dispatch. A second job there runs the pin check and its tests. That file is a second working example.

## Inputs

All inputs are optional.

| Name | Type | Default | What it does |
| --- | --- | --- | --- |
| `bun_version` | string | `latest` | Bun version that `setup-bun` installs for the dependency audit. |
| `working_directory` | string | `.` | Folder, relative to the repository root, where the dependency audit installs and audits and where the container image is built. CodeQL and the secret scan always cover the whole repository. |
| `run_dependency_audit` | boolean | `true` | Run the dependency audit job. |
| `audit_level` | string | `high` | Lowest severity that `bun audit` reports, passed as `--audit-level`. |
| `audit_soft_fail` | boolean | `false` | Run `bun audit` as advisory: findings print a warning and never fail the job. Useful on first adoption. |
| `run_snyk` | boolean | `false` | Also run Snyk inside the dependency audit job. Needs the `SNYK_TOKEN` secret. The step is set to `continue-on-error`. |
| `run_codeql` | boolean | `true` | Run the CodeQL job. |
| `codeql_languages` | string | `javascript-typescript` | CodeQL languages. Also used in the SARIF category and the artifact name. |
| `codeql_queries` | string | `security-and-quality` | CodeQL query suite. |
| `codeql_upload` | string | `never` | SARIF upload mode for CodeQL. Keep `never` unless the repository has GitHub Advanced Security. |
| `run_secret_scan` | boolean | `true` | Run the TruffleHog job. |
| `run_container_scan` | boolean | `false` | Run the container scan job: build the image, then scan it with Trivy. |
| `container_image_name` | string | `app` | Name given to the image that is built and scanned. The tag is the commit id. |
| `trivy_severity` | string | `CRITICAL,HIGH` | Severities Trivy reports. The workflow turns on the action's `limit-severities-for-sarif`, so the SARIF file holds only these. |

The workflow also accepts one optional secret, `SNYK_TOKEN`.

## What each job does

**Dependency Audit** (`dependency-audit`, 10 minute limit, permission `contents: read`). Checks out the repository, installs Bun, runs `bun install --frozen-lockfile` in `working_directory`, then runs `bun audit` at `audit_level`. With `audit_soft_fail` the audit prints a warning instead of failing. With `run_snyk` it then runs the Snyk Node action, which is called without a folder setting, so `working_directory` does not move it.

**CodeQL SAST** (`codeql`, 15 minute limit, permissions `actions: read`, `contents: read`, `security-events: write`). Initializes CodeQL for `codeql_languages` with `codeql_queries`, runs the autobuild step and the analysis, and writes SARIF to a `codeql-sarif` folder. It then uploads that folder as the artifact `codeql-sarif-<languages>`, kept 14 days, whether or not the analysis step passed. Findings do not fail the job.

**Secret Detection** (`secret-scan`, 5 minute limit, permission `contents: read`). Checks out the full history (`fetch-depth: 0`) and runs TruffleHog with `--only-verified`.

**Container Security Scan** (`container-scan`, 15 minute limit, permissions `contents: read`, `security-events: write`). Builds the image with `docker build` from `working_directory`, scans it with Trivy at `trivy_severity` and writes `trivy-results.sarif`. It then tries to upload the SARIF to the code scanning tab (the step is set to `continue-on-error`, so it does not fail the job where code scanning is unavailable) and always uploads the file as the artifact `trivy-sarif`, kept 14 days. The workflow does not set Trivy's `exit-code` input, so findings are reported and never fail the job.

## Needs

- A repository on GitHub with Actions turned on.
- A Bun lockfile (`bun.lock`) in `working_directory` for the dependency audit. `bun audit` needs a lockfile, and Bun 1.3.5 writes none for a project with no dependencies, so a project with no dependencies has nothing to audit here. The sample app has one small dependency for that reason.
- A `Dockerfile` in `working_directory` for the container scan.
- GitHub Advanced Security, only if you want SARIF in the code scanning tab. Without it the reports are still available as artifacts.
- A `SNYK_TOKEN` secret, only if `run_snyk` is on.

## Limits

- Each scanner finds only what it knows. A clean run is not a statement that the code is safe.
- TruffleHog runs with `--only-verified`, so a secret that TruffleHog cannot confirm is live does not appear in the results.
- CodeQL on a private repository needs GitHub Advanced Security. On a public repository, or on code under an open source licence, it is available without it.
- The dependency audit is Bun's: it reports what `bun audit` reports for the lockfile, and it covers only the lockfile in `working_directory`.
- The Snyk step is advisory (`continue-on-error`) and runs from the repository checkout, not from `working_directory`. A missing `SNYK_TOKEN`, or a project Snyk cannot read, shows only in that step's log.
- The artifact names are fixed, so calling this workflow twice in one workflow run makes the second upload of the same name fail.
- On pull requests from forks and from Dependabot, GitHub gives the run a read-only token, so jobs that ask for `security-events: write` may be refused before they start. For those repositories, run the security job on push.
- The sample app's Dockerfile is built and scanned only on GitHub, by the self test. The machine this was written on had no Docker.

## Checking the pins

Every third-party action in the workflow is pinned to a full commit id with its release tag in a trailing comment. To check that nothing was left on a movable tag or branch:

```sh
python3 tests/check_pins.py .github/workflows examples/caller.yml
python3 -m unittest discover -s tests -q
actionlint .github/workflows/security-scan.yml .github/workflows/self-test.yml examples/caller.yml
```

`check_pins.py` prints `path:line: not pinned: <value>` for each `uses:` that names another repository without a 40-character commit id and a `# vX.Y.Z` comment, and for each `docker://` image not pinned by its sha256 digest. Local refs that start with `./` are allowed, and a line marked `# pin-exempt: example` is skipped; the example caller uses that mark because it shows `@v1` on purpose, and a test checks that no file in `.github/workflows` carries it. It exits 0 when everything is pinned, 1 when something is not and 2 on bad usage: no path, a path that does not exist, or no `.yml` or `.yaml` file found. It uses only the Python standard library. [actionlint](https://github.com/rhysd/actionlint) is a separate tool you install yourself.

## Credits

- CodeQL, by GitHub: [github/codeql-action](https://github.com/github/codeql-action)
- TruffleHog, by Truffle Security: [trufflesecurity/trufflehog](https://github.com/trufflesecurity/trufflehog)
- Trivy, by Aqua Security: [aquasecurity/trivy-action](https://github.com/aquasecurity/trivy-action) and [aquasecurity/trivy](https://github.com/aquasecurity/trivy)
- Snyk: [snyk/actions](https://github.com/snyk/actions)
- `bun audit`, from [Bun](https://bun.sh), with [oven-sh/setup-bun](https://github.com/oven-sh/setup-bun) to install it
- [actions/checkout](https://github.com/actions/checkout) and [actions/upload-artifact](https://github.com/actions/upload-artifact), by GitHub

## License

MIT. See [LICENSE](LICENSE).

## Built at San Diego AI Studio

This workflow comes out of San Diego AI Studio, the builders' community in San Diego. More of what its members build is at [sandiegoaistudio.com/projects](https://sandiegoaistudio.com/projects).
