import json
from pathlib import Path
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent
SUPPORTED_LANGS = ("en", "uk")
DEFAULT_LANG = "en"

with open(BASE_DIR / "locales" / "strings.json", "r", encoding="utf-8") as f:
    STRINGS = json.load(f)

CONTACTS = {
    "email": "serhii.kirichko@gmail.com",
    "github": "https://github.com/SergeySetti",
    "linkedin": "https://www.linkedin.com/in/serhii-kirichko-agentic-ai-engineer/",
    "website": "https://setti.ai/",
}

app = FastAPI(title="mcp-api.net")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def pick_lang(request: Request) -> str:
    lang = request.query_params.get("lang") or request.cookies.get("lang")
    if lang in SUPPORTED_LANGS:
        return lang
    accept = request.headers.get("accept-language", "")
    if accept.lower().startswith("uk"):
        return "uk"
    return DEFAULT_LANG


def ctx(request: Request, page: str) -> dict:
    lang = pick_lang(request)
    t = STRINGS[lang]
    other = "uk" if lang == "en" else "en"
    return {
        "request": request,
        "t": t,
        "lang": lang,
        "other_lang": other,
        "page": page,
        "contacts": CONTACTS,
        "supported_langs": SUPPORTED_LANGS,
    }


def render(request: Request, template: str, page: str, extra: dict | None = None) -> HTMLResponse:
    data = ctx(request, page)
    if extra:
        data.update(extra)
    response = templates.TemplateResponse(template, data)
    response.set_cookie("lang", data["lang"], max_age=60 * 60 * 24 * 365, samesite="lax")
    return response


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return render(request, "home.html", "home")


@app.get("/services", response_class=HTMLResponse)
async def services(request: Request):
    return render(request, "services.html", "services")


@app.get("/pricing", response_class=HTMLResponse)
async def pricing(request: Request):
    return render(request, "pricing.html", "pricing")


@app.get("/warranty", response_class=HTMLResponse)
async def warranty(request: Request):
    return render(request, "warranty.html", "warranty")


@app.get("/terms", response_class=HTMLResponse)
async def terms(request: Request):
    return render(request, "terms.html", "terms")


@app.get("/contacts", response_class=HTMLResponse)
async def contacts(request: Request):
    return render(request, "contacts.html", "contacts")


@app.post("/contacts", response_class=HTMLResponse)
async def contacts_submit(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    message: str = Form(...),
):
    # Boilerplate: in production, store / forward this message.
    return render(request, "contacts.html", "contacts", {"sent": True})


@app.get("/set-lang/{lang}")
async def set_lang(lang: str, request: Request):
    if lang not in SUPPORTED_LANGS:
        raise HTTPException(status_code=404)
    target = request.headers.get("referer", "/")
    response = RedirectResponse(url=target, status_code=303)
    response.set_cookie("lang", lang, max_age=60 * 60 * 24 * 365, samesite="lax")
    return response


@app.post("/webhooks/bank/payment-approved")
async def bank_payment_webhook(request: Request):
    """
    Boilerplate webhook for bank payment-approval callbacks.

    Real integration TODO:
      - Verify the bank's signature header (HMAC / RSA).
      - Idempotency: dedupe by payment_id.
      - Match invoice_id to an internal order/subscription.
      - Mark order as paid; activate subscription; send receipt email.
    """
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    invoice_id = payload.get("invoice_id")
    amount = payload.get("amount")
    currency = payload.get("currency")
    payment_id = payload.get("payment_id")
    status = payload.get("status", "approved")

    # TODO: signature verification, persistence, side effects.
    return JSONResponse(
        {
            "received": True,
            "invoice_id": invoice_id,
            "amount": amount,
            "currency": currency,
            "payment_id": payment_id,
            "status": status,
        }
    )


@app.get("/healthz")
async def healthz():
    return {"ok": True}
