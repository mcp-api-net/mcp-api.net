import json
import logging
import uuid
from decimal import Decimal, InvalidOperation
from pathlib import Path
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import fptest, invoices, monobank

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

ROBOTS_TXT = """User-agent: *
Disallow: /test
"""

NOINDEX = {"X-Robots-Tag": "noindex, nofollow, noarchive"}
CREEPJS_DIR = BASE_DIR / "creepjs"


@app.get("/robots.txt", response_class=PlainTextResponse)
async def robots_txt():
    return ROBOTS_TXT


# --- /test: browser-fingerprint test page (vendored CreepJS + collector) -----
# Assets are served from /test/ because creep.js registers itself as a
# service/shared worker via the page-relative path ./creep.js.


@app.get("/test", include_in_schema=False)
async def fp_test_redirect(request: Request):
    query = f"?{request.url.query}" if request.url.query else ""
    return RedirectResponse(url=f"/test/{query}", status_code=308, headers=NOINDEX)


@app.get("/test/", include_in_schema=False)
async def fp_test_page():
    return FileResponse(CREEPJS_DIR / "index.html", media_type="text/html", headers={**NOINDEX, "Cache-Control": "no-store"})


@app.post("/test/collect", include_in_schema=False)
async def fp_test_collect(request: Request):
    if not fptest.configured():
        return JSONResponse({"detail": "storage not configured"}, status_code=503, headers=NOINDEX)
    body = await request.body()
    if len(body) > fptest.MAX_BODY_BYTES:
        return JSONResponse({"detail": "payload too large"}, status_code=413, headers=NOINDEX)
    try:
        payload = json.loads(body)
    except ValueError:
        payload = None
    if not isinstance(payload, dict) or not isinstance(payload.get("fingerprint"), dict):
        return JSONResponse({"detail": "invalid payload"}, status_code=400, headers=NOINDEX)
    headers = [(k.decode("latin-1"), v.decode("latin-1")) for k, v in request.headers.raw]
    try:
        doc_id = fptest.save(payload, ip=request.client.host if request.client else None, headers=headers)
    except Exception:
        log.exception("Failed to store fingerprint")
        return JSONResponse({"detail": "storage error"}, status_code=502, headers=NOINDEX)
    return JSONResponse({"id": doc_id}, headers=NOINDEX)


@app.get("/test/results", include_in_schema=False)
async def fp_test_results(request: Request, token: str | None = None, tag: str | None = None, limit: int = 50):
    if not fptest.token_ok(token) or not fptest.configured():
        raise HTTPException(status_code=404)
    return JSONResponse(fptest.recent(limit=limit, tag=tag), headers=NOINDEX)


@app.get("/test/results/{doc_id}", include_in_schema=False)
async def fp_test_result(doc_id: str, token: str | None = None):
    if not fptest.token_ok(token) or not fptest.configured():
        raise HTTPException(status_code=404)
    doc = fptest.get(doc_id)
    if doc is None:
        raise HTTPException(status_code=404)
    return JSONResponse(doc, headers=NOINDEX)


app.mount("/test", StaticFiles(directory=CREEPJS_DIR), name="creepjs")
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
    response = templates.TemplateResponse(request, template, data)
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


@app.get("/privacy", response_class=HTMLResponse)
async def privacy(request: Request):
    return render(request, "privacy.html", "privacy")


@app.get("/data-deletion", response_class=HTMLResponse)
async def data_deletion(request: Request):
    return render(request, "data_deletion.html", "data_deletion")


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


INVOICE_CURRENCIES = tuple(monobank.CCY)


def _parse_amount_minor(raw: str) -> int | None:
    """Parse an amount string into minor units (kopiykas / cents); None if invalid."""
    try:
        value = Decimal(raw.strip().replace(",", "."))
    except (InvalidOperation, AttributeError):
        return None
    if value <= 0 or value != value.quantize(Decimal("0.01")):
        return None
    return int(value * 100)


@app.get("/pay/invoice", response_class=HTMLResponse)
async def pay_invoice(request: Request):
    return render(
        request,
        "pay_invoice.html",
        "pay_invoice",
        {
            "monobank_missing": not MONOBANK.configured,
            "currencies": INVOICE_CURRENCIES,
            "currency": "UAH",
        },
    )


@app.post("/pay/invoice", response_class=HTMLResponse)
async def pay_invoice_create(
    request: Request,
    description: str = Form(...),
    amount: str = Form(...),
    currency: str = Form("UAH"),
):
    currency = currency.strip().upper()
    extra: dict = {
        "monobank_missing": not MONOBANK.configured,
        "description": description,
        "amount": amount,
        "currencies": INVOICE_CURRENCIES,
        "currency": currency if currency in INVOICE_CURRENCIES else "UAH",
    }
    if not MONOBANK.configured:
        return render(request, "pay_invoice.html", "pay_invoice", extra)

    description = description.strip()
    amount_minor = _parse_amount_minor(amount)
    if not description:
        extra["error"] = "desc"
        return render(request, "pay_invoice.html", "pay_invoice", extra)
    if amount_minor is None:
        extra["error"] = "amount"
        return render(request, "pay_invoice.html", "pay_invoice", extra)
    if currency not in INVOICE_CURRENCIES:
        extra["error"] = "currency"
        return render(request, "pay_invoice.html", "pay_invoice", extra)

    number = None
    if invoices.configured():
        try:
            number = invoices.reserve(description=description, amount_minor=amount_minor, currency=currency)
        except Exception:
            log.exception("Failed to persist invoice")
            extra["error"] = "api"
            return render(request, "pay_invoice.html", "pay_invoice", extra)
    else:
        log.warning("MONGODB_URI is not set; invoice will not be persisted")

    base = str(request.base_url).rstrip("/")
    try:
        invoice = monobank.create_invoice(
            MONOBANK,
            amount_minor=amount_minor,
            currency=currency,
            reference=number or f"inv-{uuid.uuid4().hex[:12]}",
            destination=description,
            redirect_url=MONOBANK.redirect_url or f"{base}/payment/success",
            webhook_url=MONOBANK.webhook_url or f"{base}/webhooks/monobank",
        )
    except Exception:
        log.exception("Monobank invoice create failed")
        if number:
            invoices.mark_error(number)
        extra["error"] = "api"
        return render(request, "pay_invoice.html", "pay_invoice", extra)

    page_url = invoice.get("pageUrl")
    if not page_url:
        log.error("Monobank response missing pageUrl: %s", invoice)
        if number:
            invoices.mark_error(number)
        extra["error"] = "api"
        return render(request, "pay_invoice.html", "pay_invoice", extra)

    if number:
        invoices.attach_payment_link(number, invoice_id=invoice.get("invoiceId", ""), page_url=page_url)

    extra.update(
        {
            "invoice_number": number,
            "invoice_url": page_url,
            "invoice_id": invoice.get("invoiceId", ""),
            "invoice_amount": f"{amount_minor / 100:.2f}",
            "invoice_currency": currency,
        }
    )
    return render(request, "pay_invoice.html", "pay_invoice", extra)


@app.get("/payment/success", response_class=HTMLResponse)
async def payment_success(request: Request):
    return render(request, "payment_result.html", "payment", {"success": True})


@app.get("/payment/fail", response_class=HTMLResponse)
async def payment_fail(request: Request):
    return render(request, "payment_result.html", "payment", {"success": False})


@app.post("/webhooks/monobank")
async def monobank_webhook(request: Request):
    """Monobank invoice status webhook: verify X-Sign, record the hit, update the invoice."""
    body = await request.body()
    if MONOBANK.configured:
        if not monobank.verify_webhook(MONOBANK, body, request.headers.get("X-Sign", "")):
            log.warning("Monobank webhook rejected: missing or invalid X-Sign")
            return JSONResponse({"error": "invalid signature"}, status_code=403)
    try:
        payload = json.loads(body)
    except Exception:
        payload = {}
    log.info(
        "Monobank webhook: invoiceId=%s status=%s amount=%s ccy=%s",
        payload.get("invoiceId"),
        payload.get("status"),
        payload.get("amount"),
        payload.get("ccy"),
    )
    if payload and invoices.configured():
        try:
            invoices.handle_webhook(payload)
        except Exception:
            log.exception("Failed to persist Monobank webhook")
    return JSONResponse({"received": True})


@app.get("/healthz")
async def healthz():
    return {"ok": True}
