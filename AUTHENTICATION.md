# Authentication and credential flow

This document follows the current `main` branch implementation in `app.py`,
`cloud_app.py`, `github_api.py`, and `action_job.py`, plus `SECURITY.md` and
`README_FA.md`.

## Components

1. **Arena website login:** `app.py` implements HTTP Basic authentication for
   the single administrator. `ARENA_USER` and `ARENA_PASSWORD` are read from
   the service environment; they are not stored in the repository or a user
   database. The browser sends an `Authorization: Basic ...` header after the
   server responds with `401` and `WWW-Authenticate`. The comparison uses
   `hmac.compare_digest`. `/healthz` is public; the website and its API require
   authentication. `static/index.html` uses `fetch(..., {credentials:'include'})`
   so the browser includes its HTTP-auth credentials on same-origin requests.

2. **Render-to-GitHub API access:** `cloud_app.py` constructs a `GitHub()`
   client for `GITHUB_REPOSITORY`, authenticated by `GITHUB_TOKEN`. It uses that
   client to inspect Actions runs and dispatch the match workflow. A separate
   `storage_client()` targets `STORAGE_REPOSITORY` with `STORAGE_TOKEN` (or
   falls back to `GITHUB_TOKEN` if no separate token is configured). The app
   calls `require_private()` before using the storage repository; the check
   rejects a repository whose GitHub metadata does not say `private: true`.

3. **GitHub Actions runner-to-private-storage access:** the intended
   `matches.yml` workflow supplies `STORAGE_TOKEN` as a GitHub Actions secret
   and `STORAGE_REPOSITORY` as a repository variable. `action_job.py` uses this
   credential to read the uploaded teams and configuration and write results
   and the final log ZIP. Its storage client also checks that the repository
   is private.

## Request flow

1. The browser opens the Arena site over HTTPS and authenticates with the
   administrator's `ARENA_USER` and `ARENA_PASSWORD`.
2. The browser uploads both team ZIPs and the match configuration to
   `POST /api/tests` on the same origin. Team files are not sent to the public
   GitHub repository.
3. `cloud_app.py` creates a **draft release** in the private storage
   repository, uploads the two ZIPs and `config.json`, then dispatches
   `matches.yml` in the public project with the private release ID as input.
4. The Actions runner reads the draft release assets, runs the match, then
   uploads `results.json` and `logs.zip` back to the same private release.
5. The browser polls the authenticated Arena API. The control plane reads
   status and results from the private release and streams the ZIP download
   without storing it on Render's disk.

## How credentials and tokens are handled

- Keep `ARENA_USER`, `ARENA_PASSWORD`, and `GITHUB_TOKEN` in Render's
  environment/secret settings. The app does not write these values into its
  files. `app.py` suppresses HTTP access logging so request headers, including
  Basic-auth credentials, are not logged by this handler. Use HTTPS; Basic
  authentication is only encoded, not encrypted, by itself.
- Keep `STORAGE_TOKEN` in GitHub Actions Secrets and `STORAGE_REPOSITORY` in
  Actions Variables. Use a fine-grained token limited to the private storage
  repository and only the permissions needed for its release assets. The
  Render PAT and the Actions storage token serve different jobs and should be
  separate credentials.
- `github_api.py` places a token in the GitHub API `Authorization: Bearer ...`
  request header. Its `SafeRedirect` handler removes that header on redirects,
  which matters when GitHub redirects binary-asset downloads to another host.
- `static/index.html` contains no GitHub token and calls only the Arena API.
  Tokens are not returned in API JSON responses.
- Before team launch, `action_job.py` removes `GITHUB_TOKEN`, `STORAGE_TOKEN`,
  `ARENA_PASSWORD`, and `ARENA_USER` from the environment inherited by child
  processes. The GitHub client still needs its token in the Python runner to
  finish publishing results. Environment removal is defense in depth, not a
  security sandbox: this project is for trusted teams only, as `SECURITY.md`
  explains.
- Uploaded binaries, config, results and logs are private-release assets. The
  project source and public Actions logs are public; never put team files or
  tokens in commits or public logs.

## Workflow prerequisites

The public project contains `.github/workflows/matches.yml`, which is the
workflow `cloud_app.py` dispatches. Repository setup still requires the
`STORAGE_TOKEN` Actions secret and `STORAGE_REPOSITORY` Actions variable, and
Actions must be enabled for the repository. Without those settings the
workflow cannot access the private releases even though the Arena website
login succeeds.

## Source references

- [`app.py`](app.py): Basic authentication, same-origin API guard, upload
  validation, local-mode job entry point.
- [`cloud_app.py`](cloud_app.py): authenticated control plane, private release
  creation, workflow dispatch, status polling and archive streaming.
- [`github_api.py`](github_api.py): bearer-token API client, private-repository
  check, redirect credential stripping, storage client selection.
- [`action_job.py`](action_job.py): runner-side private-release access and
  removal of secret environment variables before team processes launch.
- [`runner.py`](runner.py): starts server and team processes.
- [`SECURITY.md`](SECURITY.md) and [`README_FA.md`](README_FA.md): deployment
  and security guidance.
