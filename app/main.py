import json
import logging
import uuid
from pathlib import Path
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import monobank

log = logging.getLogger("mcp-api.net")

BASE_DIR = Path(__file__).resolve().parent
SUPPORTED_LANGS = ("en", "uk")
DEFAULT_LANG = "uk"

with open(BASE_DIR / "locales" / "strings.json", "r", encoding="utf-8") as f:
    STRINGS = json.load(f)

CONTACTS = {
    "email": "serhii.kirichko@gmail.com",
    "github": "https://github.com/SergeySetti",
    "linkedin": "https://www.linkedin.com/in/serhii-kirichko-agentic-ai-engineer/",
    "website": "https://setti.ai/",
    "phone": "+380997946400",
}

MONOBANK = monobank.load_config()
TEST_AMOUNT_MINOR = 10  # 0.10 USD
TEST_CURRENCY = "USD"

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


@app.get("/agreements", response_class=HTMLResponse)
async def agreements(request: Request):
    return render(request, "agreements.html", "agreements")


@app.get("/agreements/project-sample", response_class=HTMLResponse)
async def agreement_project(request: Request):
    return render(request, "agreement_project.html", "agreements")


@app.get("/agreements/sse-sample", response_class=HTMLResponse)
async def agreement_sse(request: Request):
    return render(request, "agreement_sse.html", "agreements")


@app.get("/agreements/template", response_class=HTMLResponse)
async def agreement_template(request: Request):
    return render(request, "agreement_template.html", "agreements")


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


@app.get("/pay/test", response_class=HTMLResponse)
async def pay_test(request: Request):
    return render(
        request,
        "pay_test.html",
        "pay_test",
        {
            "monobank_missing": not MONOBANK.configured,
            "amount": "0.10",
            "currency": TEST_CURRENCY,
        },
    )


@app.post("/pay/test")
async def pay_test_start(request: Request):
    if not MONOBANK.configured:
        raise HTTPException(status_code=503, detail="Monobank not configured")

    base = str(request.base_url).rstrip("/")
    try:
        invoice = monobank.create_invoice(
            MONOBANK,
            amount_minor=TEST_AMOUNT_MINOR,
            currency=TEST_CURRENCY,
            reference=f"test-{uuid.uuid4().hex[:12]}",
            destination="mcp-api.net test payment",
            redirect_url=MONOBANK.redirect_url or f"{base}/payment/success",
            webhook_url=MONOBANK.webhook_url or f"{base}/webhooks/monobank",
        )
    except Exception as e:
        log.exception("Monobank invoice create failed")
        raise HTTPException(status_code=502, detail=str(e))

    page_url = invoice.get("pageUrl")
    if not page_url:
        raise HTTPException(status_code=502, detail="Monobank response missing pageUrl")
    return RedirectResponse(url=page_url, status_code=303)


@app.get("/payment/success", response_class=HTMLResponse)
async def payment_success(request: Request):
    return render(request, "payment_result.html", "payment", {"success": True})


@app.get("/payment/fail", response_class=HTMLResponse)
async def payment_fail(request: Request):
    return render(request, "payment_result.html", "payment", {"success": False})


@app.post("/webhooks/monobank")
async def monobank_webhook(request: Request):
    """Monobank invoice status webhook. Logs the payload."""
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    # TODO: verify X-Sign (ECDSA over body using /api/merchant/pubkey),
    # persist invoice, mark order paid, send receipt.
    log.info(
        "Monobank webhook: invoiceId=%s status=%s amount=%s ccy=%s",
        payload.get("invoiceId"),
        payload.get("status"),
        payload.get("amount"),
        payload.get("ccy"),
    )
    return JSONResponse({"received": True})


@app.get("/healthz")
async def healthz():
    return {"ok": True}
