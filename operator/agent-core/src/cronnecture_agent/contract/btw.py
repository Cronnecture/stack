"""Dutch BTW / reverse-charge fields on operator books. Not a VAT identification number."""

from __future__ import annotations

import re
from typing import Any

BTW_KINDS = ("standard", "reduced", "reverse_charge", "exempt", "unknown")

REVERSE_CHARGE = re.compile(
    r"verleggingsregeling|heffing\s*verlegd|btw\s*verlegd|vat\s*verlegd|"
    r"vat\s*reverse[\s-]?charge|reverse[\s-]?charged?|btw\s*shifted|"
    r"intra-?community\s+(?:supply|sale|acquisition)|igic\s*reverse|"
    r"art(?:ikel|\.?)?\s*(?:44|196)\b|directive\s*2006\s*/\s*112",
    re.I,
)

_MONEY = re.compile(r"[$€£]?\s*\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?")
_DUTCH_RATE = re.compile(r"\b(0|9|21)\s*%")


def _round(value: float) -> float:
    return round(float(value) + 0.0, 2)


def _parse_money(raw: str) -> float:
    cleaned = re.sub(r"[^\d,.-]", "", raw or "")
    if not cleaned:
        return 0.0
    last_comma = cleaned.rfind(",")
    last_dot = cleaned.rfind(".")
    if last_comma >= 0 and last_dot >= 0:
        normalized = (
            cleaned.replace(".", "").replace(",", ".") if last_comma > last_dot else cleaned.replace(",", "")
        )
    elif last_comma >= 0:
        fraction = len(cleaned) - last_comma - 1
        normalized = cleaned.replace(",", "") if fraction == 3 else cleaned.replace(",", ".")
    else:
        normalized = cleaned
    try:
        return _round(float(normalized))
    except ValueError:
        return 0.0


def _vat_from_exclusive(net: float, rate: int) -> float:
    if rate <= 0:
        return 0.0
    return _round(net * rate / 100.0)


def infer_btw_kind(row: dict[str, Any]) -> str:
    kind = row.get("btwKind") or row.get("btw_kind")
    currency = str(row.get("currency") or "EUR")
    foreign = currency != "EUR"
    reverse = bool(row.get("reverseCharge") or row.get("reverse_charge"))
    if kind in BTW_KINDS and not (kind == "reverse_charge" and foreign):
        return str(kind)
    if reverse and not foreign:
        return "reverse_charge"
    rate = row.get("vatRate") if row.get("vatRate") is not None else row.get("vat_rate")
    try:
        rate_i = int(rate)
    except (TypeError, ValueError):
        rate_i = None
    if rate_i == 21:
        return "standard"
    if rate_i == 9:
        return "reduced"
    if rate_i == 0 or foreign:
        return "exempt"
    return "unknown"


def extract_btw(text: str, *, currency: str = "EUR", net: float | None = None) -> dict[str, Any]:
    """Read BTW from invoice text. Reverse charge keeps an aangifte liability."""
    hay = text or ""
    reverse = bool(REVERSE_CHARGE.search(hay))
    if reverse:
        rate_hit = _DUTCH_RATE.search(hay)
        nominal = int(rate_hit.group(1)) if rate_hit and rate_hit.group(1) in {"9", "21"} else 21
        printed = None
        for match in re.finditer(
            r"(?:btw\s*verlegd|vat\s*reverse[\s-]?charge)[^\n]{0,40}(" + _MONEY.pattern + ")",
            hay,
            re.I,
        ):
            printed = _parse_money(match.group(1))
            if printed > 0:
                break
        aangifte = printed if printed and printed > 0 else (_vat_from_exclusive(net or 0, nominal) if net else None)
        return {
            "kind": "reverse_charge",
            "vatAmount": 0.0,
            "vatRate": 0,
            "reverseCharge": True,
            "nominalVatRate": nominal,
            "aangifteVatAmount": aangifte,
            "btwStated": printed,
            "foundAmount": bool(aangifte and aangifte > 0),
        }
    if currency != "EUR":
        return {
            "kind": "exempt",
            "vatAmount": 0.0,
            "vatRate": 0,
            "reverseCharge": False,
            "foundAmount": True,
        }
    dutch = _DUTCH_RATE.search(hay)
    amounts: list[float] = []
    for line in hay.splitlines():
        if not re.search(r"\b(btw|vat|omzetbelasting)\b", line, re.I):
            continue
        if re.search(r"excl(?:usief|\.)?\s*(?:btw|vat)|total\s*excluding", line, re.I):
            continue
        stripped = _DUTCH_RATE.sub(" ", line)
        found = [_parse_money(m.group(0)) for m in _MONEY.finditer(stripped)]
        if found:
            amounts.append(found[-1])
    vat_amount = _round(sum(amounts)) if amounts else None
    rate = int(dutch.group(1)) if dutch else None
    if vat_amount is None or rate is None:
        return {
            "kind": "unknown",
            "vatAmount": None,
            "vatRate": None,
            "reverseCharge": False,
            "foundAmount": False,
        }
    kind = "standard" if rate == 21 else "reduced" if rate == 9 else "exempt"
    return {
        "kind": kind,
        "vatAmount": vat_amount,
        "vatRate": rate,
        "reverseCharge": False,
        "foundAmount": True,
    }


def hydrate_row(row: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(row, dict):
        return row
    next_row = dict(row)
    kind = infer_btw_kind(next_row)
    next_row["btwKind"] = kind
    if kind == "reverse_charge":
        next_row["reverseCharge"] = True
        next_row["vatAmount"] = 0
        next_row["vatRate"] = 0
        aangifte = next_row.get("aangifteVatAmount")
        try:
            aangifte_f = float(aangifte) if aangifte not in (None, "") else 0.0
        except (TypeError, ValueError):
            aangifte_f = 0.0
        if aangifte_f <= 0:
            net = next_row.get("amountExcl")
            if net in (None, ""):
                net = next_row.get("amount")
            try:
                net_f = float(net or 0)
            except (TypeError, ValueError):
                net_f = 0.0
            stated = next_row.get("btwStated")
            try:
                stated_f = float(stated) if stated not in (None, "") else 0.0
            except (TypeError, ValueError):
                stated_f = 0.0
            nominal = next_row.get("nominalVatRate") or 21
            try:
                nominal_i = int(nominal)
            except (TypeError, ValueError):
                nominal_i = 21
            if stated_f > 0:
                next_row["aangifteVatAmount"] = _round(stated_f)
            elif net_f > 0:
                next_row["aangifteVatAmount"] = _vat_from_exclusive(net_f, nominal_i)
            if not next_row.get("nominalVatRate"):
                next_row["nominalVatRate"] = nominal_i
    elif str(next_row.get("currency") or "EUR") != "EUR":
        next_row.pop("reverseCharge", None)
        next_row.pop("aangifteVatAmount", None)
        next_row.pop("nominalVatRate", None)
    return next_row


def hydrate_ledger(state: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(state, dict):
        return state
    next_state = dict(state)
    invoices = next_state.get("invoices")
    entries = next_state.get("entries")
    if isinstance(invoices, list):
        next_state["invoices"] = [hydrate_row(item) if isinstance(item, dict) else item for item in invoices]
    if isinstance(entries, list):
        next_state["entries"] = [hydrate_row(item) if isinstance(item, dict) else item for item in entries]
    return next_state
