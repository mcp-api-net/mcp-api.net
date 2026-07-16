# mcp-api.net

FastAPI marketing site for an MCP consulting / integration / managed-service business.

## Stack
- FastAPI + Jinja2 templates
- Bootstrap 5 (CDN) for CSS/JS
- MongoDB (pymongo) for invoice storage — shared `onlik` cluster
- All UI strings in a single JSON file: `app/locales/strings.json`
- Languages: English (`en`) and Ukrainian (`uk`)

## Run

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
uvicorn app.main:app --reload
```

Or with `uv`:

```powershell
uv sync
uv run uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000

## Pages
- `/` — Home
- `/services`
- `/pricing` — per-project and monthly MCP-SSE plans
- `/warranty` — money-back policy
- `/contacts`
- Language switch: `/set-lang/en` or `/set-lang/uk`

## Monobank Acquiring

Pay button uses Monobank's [invoice/create](https://monobank.ua/api-docs/acquiring/methods/ia/post--api--merchant--invoice--create) API.

- Set `MONOBANK_API_KEY` (X-Token from the acquiring terminal).
- `GET /pay/test` renders the test-payment page; `POST /pay/test` creates an invoice and 303-redirects to Monobank's `pageUrl`. Test payments are not persisted.
- `POST /webhooks/monobank` receives invoice status callbacks: verifies `X-Sign`
  (ECDSA over the raw body, merchant pubkey from `/api/merchant/pubkey`, cached
  and re-fetched once on mismatch; invalid → 403), records every verified hit in
  `onlik.webhook_hits` (including invoices issued on other sites under the same
  merchant), and updates the matching invoice in `onlik.invoices` — repeated /
  out-of-order webhooks are ignored via `modifiedDate`. When `MONOBANK_API_KEY`
  is unset (local dev), signature checks are skipped.

### Invoice creation (`/pay/invoice`)

Internal tool for billing clients: open `/pay/invoice`, enter a service
description, an amount and a currency (UAH, USD or EUR), and the server
creates a Monobank invoice and shows the resulting payment link (`pageUrl`)
and the invoice number. Copy the link and send it to the client — they pay
online on Monobank's hosted page, and the settlement status arrives on
`POST /webhooks/monobank` like any other invoice.

- Each invoice gets a random (non-sortable) public number in the format
  `INV-{digit}{3 chars}`, e.g. `INV-5FZW`. The alphabet (`12456789DFGJLNQRSUVWZ`)
  excludes Latin letters with identical-looking Cyrillic counterparts and the
  digits 0/3 (lookalikes of О/З). Uniqueness is enforced by a unique Mongo
  index with retry on collision.
- Invoices are persisted in MongoDB (`MONGODB_URI`, database `onlik`,
  collection `invoices`); the number is sent to Monobank as
  `merchantPaymInfo.reference`, and the webhook drives the status:
  `pending → created → processing/success/failure/expired/reversed`
  (`error` if invoice creation failed). If `MONGODB_URI` is unset, links are
  still created with a random `inv-<uuid>` reference, just not persisted.
- The page is intentionally **not linked** from anywhere on the site — reach
  it by URL only.
- There is also **no authentication** on it: anyone who knows the URL can
  create (unpaid) invoices against the terminal. Add auth before sharing the
  URL beyond yourself.
- Amounts accept up to 2 decimal places (kopiykas / cents); the description
  becomes the invoice's `destination` shown to the payer.
- Non-UAH invoices (USD/EUR) are created only if multicurrency is enabled on
  the Monobank acquiring terminal — otherwise `invoice/create` returns an
  error, which the page surfaces as an alert.

## Docker

```powershell
docker build -t mcp-api-net .
docker run --rm -p 8000:8000 mcp-api-net
```

## Deployment

Runs standalone on `85.62.195.176` (SSH alias `recall-server`), fronted by a
shared Caddy reverse proxy that also serves other projects on that box
(e.g. `recall.select`). `docker-compose.yml` runs the published GHCR image on
the external `caddy_net` network; `deploy/caddy/mcp-api.net.caddy` is the site
block this repo owns, which the shared proxy mounts and imports — routing
config lives here, not in the central proxy repo.

Deploy with:

```powershell
./deploy/deploy.sh
```

Works from a dev machine (pushes, then runs the deploy over SSH) or directly
on the server (deploys in place). The server-side `.env` (`MONOBANK_API_KEY`,
`MONOBANK_REDIRECT_URL`, `MONOBANK_WEBHOOK_URL`, `MONGODB_URI`) is not
committed — see `.env.example`.

## Publishing to GHCR

On every push to `main` (and on tags `v*.*.*`), [.github/workflows/publish.yml](.github/workflows/publish.yml) builds a multi-tag Docker image and pushes it to:

```
ghcr.io/mcp-api-net/mcp-api.net:latest
ghcr.io/mcp-api-net/mcp-api.net:sha-<commit>
ghcr.io/mcp-api-net/mcp-api.net:<semver>   # on v*.*.* tags
```

Setup (one-time):

```powershell
git init -b main
git remote add origin https://github.com/mcp-api-net/mcp-api.net.git
git add .
git commit -m "Initial commit"
git push -u origin main
```

The workflow uses the built-in `GITHUB_TOKEN` — no extra secrets needed. The image is published as **public**.

If the automatic visibility step fails (most often on the very first publish), set it once by hand:

1. Open https://github.com/orgs/mcp-api-net/packages
2. Click the `mcp-api.net` package → **Package settings**
3. Under **Danger Zone** → **Change visibility** → choose **Public**

To pull and run anywhere:

```bash
docker run --rm -p 8000:8000 ghcr.io/mcp-api-net/mcp-api.net:latest
```

## i18n

Edit `app/locales/strings.json`. Each top-level key is a language code; add a new language by adding a new key and listing it in `SUPPORTED_LANGS` in `app/main.py`.
