# Accounts, subscriptions and authentication

The web UI is public and `/login` offers Google login plus a separate owner
login. The Google password is never collected by Arena. Existing HTTP Basic
owner credentials continue to work for administration and the personal worker.

## Deployment

Set these server environment variables (never commit their values):

- `ARENA_USER`: owner email/username; `ARENA_PASSWORD`: a separate strong site
  password. They allow owner login at `/login` with unlimited access and no
  subscription purchase.
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`: Google OAuth web application
  credentials. Register the exact callback
  `https://YOUR-SITE/auth/google/callback` with Google.
- `ARENA_PUBLIC_URL`: the exact HTTPS origin of this deployment. Local OAuth
  development may use HTTP on localhost. This setting also enables Secure
  session cookies on production HTTPS.
- Optional `ARENA_OWNER_GOOGLE_SUB`: immutable Google `sub` of the owner.
  Alternatively, `ARENA_OWNER_EMAIL` may name a verified Gmail address.
  When `sub` is configured it takes precedence. Any other Google account is
  an ordinary user and cannot grant itself owner access.
- `ARENA_ACCOUNTS_STORE=github`: use the existing private `STORAGE_REPOSITORY`
  and `STORAGE_TOKEN` (or `GITHUB_TOKEN`) for durable account snapshots. The
  Render blueprint sets this mode; existing deployments must add the variable
  in their environment settings. No paid Render disk is required.
- For local deployments, `ARENA_ACCOUNTS_STORE=sqlite` (default) uses
  `ARENA_ACCOUNT_DB`, defaulting to `DATA_DIR/accounts.sqlite3`. Keep this file
  on persistent storage. An ephemeral SQLite file alone is unsuitable for
  paid subscriptions or durable guest quotas.
- `ARENA_TRUST_PROXY=1` may be enabled only when a trusted reverse proxy
  overwrites `X-Forwarded-For`. The default uses the direct peer address.
  Guest quota buckets are shared by guests behind the same address; their
  identities, jobs and files remain separate. Google accounts have their own
  quotas. Clearing cookies does not reset the address bucket.

The GitHub mode is for **one web instance**. It restores a private draft release
named `arena-account-store-v1` before serving account data. Every mutation
uploads a new SQLite snapshot before acknowledging it; the two newest copies
are retained. A failed upload keeps the previous snapshot and fails the local
transaction. Storage failures must be fixed rather than switching to a fresh
database, which would lose subscriptions and job ownership. Treat the account
store as private personal data; do not publish or manually delete it. For
multiple web instances, replace this adapter with a transactional shared DB.
Do not point the web service and personal worker at the same local account DB.

Google OAuth uses a short-lived, one-use, session-bound state and PKCE. The
backend exchanges the authorization code directly with Google's HTTPS token
endpoint and reads verified account details from Google's HTTPS UserInfo
endpoint. Identity is keyed by `sub`, never by a browser-supplied email. Session
tokens are opaque and only their SHA-256 hashes are stored. Cookies are
HttpOnly, SameSite=Lax and Secure on the configured HTTPS origin. Owner login
has a server-side attempt limit. Account-changing POSTs require a same-origin
Origin header. Secrets stay on the server.

## Plans and payment

All prices are **tomans**, and each approved purchase lasts one calendar month
from activation. Renewing the same plan extends it by another month. A different
plan cannot be approved while the existing plan is active; no silent downgrade
or conversion of purchased days occurs.

| Plan | Original price | Current price | Requests | Games per request | Files |
| --- | --- | --- | --- | --- | --- |
| Free / guest | 0 | 0 | 5 total | At most 5 games **in total** | RCG, RCL, JSON |
| Plus | 50,000 | 30,000 | Unlimited during the month | 100 | RCG, RCL, JSON |
| Pro | 70,000 | 50,000 | Unlimited during the month | Existing technical cap of 500 | All exports |
| Owner | — | Free | Unlimited | Existing technical cap of 500 | All exports |

Google login preserves the consumed guest allowance. Free submissions reserve
quota atomically; submissions rejected before dispatch release that reservation.
Accepted jobs (including later failed/cancelled matches) consume their allowance.
A request split over multiple rounds still counts every game.

Payments are manual card transfers to **6219861351359095**. The site displays
the recipient card; it does not initiate a transfer or claim to verify a bank
transaction. A signed-in user submits the transfer reference and chosen plan.
The price is taken from server configuration, not the browser. The owner sees
pending requests in the account panel and must reconcile the reference and
amount with an actual bank receipt before approving. Only owner approval
activates the subscription. Duplicate references and repeated approvals are
rejected. Rejection does not activate a plan. No bank API or payment gateway
is configured by this change.

## Files and ownership

Each new test and cloud source build is bound to its creator. Lists, status,
live feeds, replays, downloads and cancellation are protected by that binding.
Existing jobs without account metadata remain owner-only. Source-build reuse
also checks the creator. The shared native desktop and personal Ubuntu worker
are owner-only because they were designed as single-user tools.

The complete `match.rcg` is always generated and retained. Optional
`player_rcg={enabled:true,left:[1,2],right:[3]}` writes separate ULG5 files under
`player-rcg/` for the selected uniforms. Each keeps the ball, game metadata and
that player's server-recorded track. These are filtered server recordings,
**not player-local first-person sensor logs**. The original full RCG remains
unchanged. Both teams have uniforms 1 through 11.

Free and Plus cannot request offline/CSV/debug exports. Their archives contain
only RCG, RCL and JSON (including gzip-compressed JSON). Downloads are filtered
again using current entitlement, so expired Pro users cannot retrieve other
file types from an older full archive. Results JSON still excludes player
position telemetry; replay data is separate.

## Existing private runner architecture

`cloud_app.py` uploads teams/config into draft releases in a private storage
repository and dispatches `matches.yml`. The runner publishes results/replays
and archives there. The website streams downloads through authenticated API
routes and never exposes GitHub tokens. The storage client rejects public
repositories and strips Authorization on asset redirects. Existing Actions
secrets and variables remain required; see `SECURITY.md` for the trusted-team
execution model. This change does not publish a site or configure OAuth/bank
accounts automatically.

Google flow reference: https://developers.google.com/identity/protocols/oauth2/web-server
