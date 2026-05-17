# mcp-api.net

FastAPI marketing site for an MCP consulting / integration / managed-service business.

## Stack
- FastAPI + Jinja2 templates
- Bootstrap 5 (CDN) for CSS/JS
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

## Bank payment webhook (boilerplate)

`POST /webhooks/bank/payment-approved`

Expects JSON `{ invoice_id, amount, currency, payment_id, status }`.
TODOs marked in `app/main.py`: signature verification, idempotency, invoice matching, side effects.

## Docker

```powershell
docker build -t mcp-api-net .
docker run --rm -p 8000:8000 mcp-api-net
```

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

To allow the workflow to set visibility automatically going forward, in the org settings enable: **Settings → Actions → General → Workflow permissions → Read and write permissions** (also tick *Allow GitHub Actions to create and approve pull requests* if you use them).

To pull and run anywhere:

```bash
docker run --rm -p 8000:8000 ghcr.io/mcp-api-net/mcp-api.net:latest
```

## i18n

Edit `app/locales/strings.json`. Each top-level key is a language code; add a new language by adding a new key and listing it in `SUPPORTED_LANGS` in `app/main.py`.
