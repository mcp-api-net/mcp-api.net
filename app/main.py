import json
import logging
import uuid
from pathlib import Path
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import liqpay

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

LIQPAY = liqpay.load_config()

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


@app.get("/pay/test", response_class=HTMLResponse)
async def pay_test(request: Request):
    if not LIQPAY.configured:
        return render(
            request,
            "pay_test.html",
            "pay_test",
            {"liqpay_missing": True, "amount": "0.10", "currency": "USD"},
        )

    data, signature = liqpay.build_checkout(
        LIQPAY,
        amount=0.10,
        currency="USD",
        description="mcp-api.net test payment",
        order_id=f"test-{uuid.uuid4().hex[:12]}",
        language=ctx(request, "pay_test")["lang"],
    )
    return render(
        request,
        "pay_test.html",
        "pay_test",
        {
            "liqpay_missing": False,
            "amount": "0.10",
            "currency": "USD",
            "checkout_url": liqpay.LIQPAY_CHECKOUT_URL,
            "data": data,
            "signature": signature,
            "sandbox": LIQPAY.is_sandbox,
        },
    )


@app.get("/payment/success", response_class=HTMLResponse)
async def payment_success(request: Request):
    return render(request, "payment_result.html", "payment", {"success": True})


@app.get("/payment/fail", response_class=HTMLResponse)
async def payment_fail(request: Request):
    return render(request, "payment_result.html", "payment", {"success": False})


@app.post("/webhooks/liqpay")
async def liqpay_callback(
    data: str = Form(...),
    signature: str = Form(...),
):
    """LiqPay server callback. Verifies signature and logs the payload."""
    if not LIQPAY.configured:
        raise HTTPException(status_code=503, detail="LiqPay not configured")

    if not liqpay.verify(data, signature, LIQPAY.private_key):
        log.warning("LiqPay callback signature mismatch")
        raise HTTPException(status_code=400, detail="invalid signature")

    payload = liqpay.decode_callback(data)
    log.info(
        "LiqPay callback: order_id=%s status=%s amount=%s %s",
        payload.get("order_id"),
        payload.get("status"),
        payload.get("amount"),
        payload.get("currency"),
    )
    # TODO: persist payment, mark invoice paid, send receipt, etc.
    return JSONResponse({"received": True})


@app.get("/healthz")
async def healthz():
    return {"ok": True}
