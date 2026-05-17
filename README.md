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

## i18n

Edit `app/locales/strings.json`. Each top-level key is a language code; add a new language by adding a new key and listing it in `SUPPORTED_LANGS` in `app/main.py`.
