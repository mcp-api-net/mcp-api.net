"""
Minimal Monobank Acquiring client (no external SDK).

Invoice create:
  POST https://api.monobank.ua/api/merchant/invoice/create
  Header: X-Token: <MONOBANK_API_KEY>
  Body:   { amount, ccy, merchantPaymInfo, redirectUrl, webHookUrl, ... }
  Reply:  { invoiceId, pageUrl }

Docs: https://monobank.ua/api-docs/acquiring/methods/ia/post--api--merchant--invoice--create
"""

from __future__ import annotations

import json as _json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

MONOBANK_API_BASE = "https://api.monobank.ua"
INVOICE_CREATE_PATH = "/api/merchant/invoice/create"

# ISO 4217 numeric currency codes accepted by Monobank acquiring.
CCY = {"UAH": 980, "USD": 840, "EUR": 978}


@dataclass(frozen=True)
class MonobankConfig:
    api_key: str
    webhook_url: str
    redirect_url: str

    @property
    def configured(self) -> bool:
        return bool(self.api_key)


def load_config() -> MonobankConfig:
    return MonobankConfig(
        api_key=os.getenv("MONOBANK_API_KEY", ""),
        webhook_url=os.getenv("MONOBANK_WEBHOOK_URL", ""),
        redirect_url=os.getenv("MONOBANK_REDIRECT_URL", ""),
    )


def create_invoice(
        cfg: MonobankConfig,
        *,
        amount_minor: int,
        currency: str,
        reference: str,
        destination: str,
        redirect_url: str | None = None,
        webhook_url: str | None = None,
) -> dict:
    """Create a Monobank invoice and return the parsed response (`invoiceId`, `pageUrl`)."""
    if not cfg.configured:
        raise RuntimeError("MONOBANK_API_KEY is not set")
    ccy = CCY.get(currency.upper())
    if ccy is None:
        raise ValueError(f"unsupported currency: {currency}")

    payload: dict = {
        "amount": int(amount_minor),
        "ccy": ccy,
        "merchantPaymInfo": {
            "reference": reference,
            "destination": destination,
        },
        "paymentType": "debit",
    }
    redirect = redirect_url or cfg.redirect_url
    if redirect:
        payload["redirectUrl"] = redirect
    webhook = webhook_url or cfg.webhook_url
    if webhook:
        payload["webHookUrl"] = webhook

    req = urllib.request.Request(
        MONOBANK_API_BASE + INVOICE_CREATE_PATH,
        data=_json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Token": cfg.api_key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Monobank invoice create failed ({e.code}): {detail}") from e
    return _json.loads(body)
