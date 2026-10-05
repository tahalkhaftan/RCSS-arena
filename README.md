# RCSS Arena

A mobile-friendly RoboCup Soccer Simulation 2D test portal. The web control plane runs on **Render Free**, while **GitHub Actions** runs RCSSServer 19.0.0 and the teams. The browser is not the match worker: closing it after submission does not stop the job.

[راهنمای فارسی و نصب](README_FA.md) · [Security model](SECURITY.md) · [Third-party licenses](THIRD_PARTY.md)

## Features

- Left/right ZIP uploads, relative working directory and start command per team.
- Test rounds and matches per round; ordinary or synchronous server mode.
- Match progress, score summary, possession estimates and downloadable JSON.
- Downloadable ZIP with `.rcg`, `.rcl`, server and team output logs.
- Graceful cancellation and recovery of the most recent test.
- One self-contained HTML/CSS/JavaScript interface; Python standard-library backend.

## Public project, private team files

This repository and its Actions logs are public. **Its source code cannot be hidden.**
Uploaded teams, configuration, results and logs are stored in a **separate private repository**. The application refuses public storage repositories. Do not commit team binaries, team source or credentials to this project. Public Actions must never print their contents.

Each user forks this project and deploys their **own password-protected instance** with their own private storage repository. This is not an anonymous multi-tenant execution service. Only run trusted teams; player processes do not have a dedicated security sandbox.

## Deploy

1. Put all project files, including `.github/`, at the root of `tahalkhaftan/RCSS-arena`, on `main`.
2. Create `tahalkhaftan/RCSS-arena-data` as **private**, initialized with a README on its default branch.
3. Create a fine-grained storage PAT for the private repository only: Contents read/write. In the public repository, set Actions **secret** `STORAGE_TOKEN` to this PAT and Actions **variable** `STORAGE_REPOSITORY` to `tahalkhaftan/RCSS-arena-data`.
4. Create a separate Render PAT restricted to both repositories: Contents read/write and Actions read/write. Save it only in Render's secret environment, never in a committed file.
5. Connect Render to the public repository. Create a Docker Web Service, select **Free**, and use `render.yaml` as a reference. Set `ARENA_USER`, `ARENA_PASSWORD`, `GITHUB_REPOSITORY=tahalkhaftan/RCSS-arena`, `STORAGE_REPOSITORY=tahalkhaftan/RCSS-arena-data`, `GITHUB_TOKEN=<Render PAT>`, `GITHUB_REF=main`.
6. Open the HTTPS website, sign in, upload two Linux x86_64 team binaries and start **one ordinary match** first. The site creates the private release ID and dispatches Actions; manually entering a made-up release ID will fail.

No paid service or disk is declared. Free tiers still have limits and can change. Standard public Actions runners are free under GitHub's usage rules; larger runners are paid. Render Free can sleep, restart and exhaust its bandwidth/build allowance. Private data is not persisted on Render's filesystem. Do not add a payment method if you require quota exhaustion to stop consumption instead of purchasing overage. This app does not control account billing settings.

## Commands

ZIP directory: `AITech-2D/bin/`  
Start command: `./start.sh -h {host} -p {port}` or `./localStartAll`

Commands must start all 11 players. Supported placeholders: `{host}`, `{port}`, `{coach_port}`, `{olcoach_port}`. Include required libraries as ordinary files; ZIP symlinks are rejected. This version accepts prepared binaries; building uploaded team source is not implemented.

## Limits and validation

Combined team uploads: 32 MiB. Up to 50 matches per request, sequential execution. Workflow timeout: 150 minutes; per-match timeout: 30 minutes. A request may exceed the workflow time budget, so begin with small batches. Each instance has one administrator login and one active workflow at a time.

Possession is a kickable-distance estimate during `play_on`, with free/shared categories; it is not an official server statistic or last-touch measure. The definition is included in JSON. Incomplete games are excluded from completed-game aggregate statistics.

Run checks: `python3 -m unittest discover -s tests -v`.

Local checks use synthetic logs, a fake UDP server and a mocked GitHub API. A real GitHub/Render deployment, RCSS build there and a full game using your team binaries still require verification. No team binaries are bundled.

## Sources

- https://docs.github.com/en/actions/reference/runners/github-hosted-runners
- https://docs.github.com/en/billing/concepts/product-billing/github-actions
- https://render.com/docs/free
- https://github.com/rcsoccersim/rcssserver
