from __future__ import annotations

import re

from backend.app.api.schemas import TradeFollowupDraftRequest, TradeQuoteDraftRequest


COUNTRY_ALIASES = {
    "united states": "United States",
    "usa": "United States",
    "us": "United States",
    "canada": "Canada",
    "germany": "Germany",
    "france": "France",
    "uk": "United Kingdom",
    "united kingdom": "United Kingdom",
    "australia": "Australia",
    "uae": "United Arab Emirates",
    "dubai": "United Arab Emirates",
    "saudi": "Saudi Arabia",
    "india": "India",
    "singapore": "Singapore",
}

TRADE_TERMS = ["FOB", "CIF", "EXW", "DDP", "DAP", "DDU"]
PAYMENT_TERMS = ["T/T", "LC", "L/C", "PAYPAL", "WESTERN UNION", "ALIBABA TRADE ASSURANCE"]
CERTIFICATIONS = ["CE", "UKCA", "FCC", "ROHS", "REACH", "UL", "ETL", "FDA", "BSCI", "ISO"]


def analyze_trade_inquiry(content: str, source: str = "manual") -> dict:
    text = content.strip()
    lower = text.lower()
    product = _extract_product(text)
    quantity = _extract_quantity(text)
    country = _extract_country(lower)
    trade_term = _pick_upper(text, TRADE_TERMS)
    payment_term = _pick_upper(text, PAYMENT_TERMS)
    certifications = [item for item in CERTIFICATIONS if re.search(rf"\b{re.escape(item)}\b", text, re.I)]
    buyer_type = _buyer_type(lower)
    missing = _missing_fields(product, quantity, country, trade_term, payment_term)
    risks = _risk_points(lower, certifications, trade_term, payment_term)
    score, signals = _intent_score(lower, quantity, country, trade_term, payment_term, certifications)
    stage = "high_intent" if score >= 75 else "qualified" if score >= 55 else "new_inquiry"

    return {
        "source": source.strip() or "manual",
        "language": "en" if re.search(r"[A-Za-z]{8,}", text) else "unknown",
        "summary": text[:260],
        "buyerType": buyer_type,
        "intentScore": score,
        "stage": stage,
        "riskLevel": "high" if len(risks) >= 3 else "medium" if risks else "low",
        "signals": signals,
        "missingFields": missing,
        "riskPoints": risks,
        "extracted": {
            "product": product,
            "quantity": quantity,
            "country": country,
            "tradeTerm": trade_term,
            "paymentTerm": payment_term,
            "certifications": certifications,
            "email": _extract_email(text),
            "whatsapp": _extract_whatsapp(text),
        },
        "nextActions": _next_actions(missing, risks, stage),
        "replyDraft": _reply_draft(product, quantity, country, missing),
    }


def draft_trade_quote(req: TradeQuoteDraftRequest) -> dict:
    product = req.product.strip()
    quantity = req.quantity.strip()
    currency = (req.currency.strip() or "USD").upper()
    trade_term = req.trade_term.strip().upper() or "FOB"
    destination = req.destination.strip()
    payment_terms = req.payment_terms.strip() or "T/T 30% deposit, 70% before shipment"
    lead_time = req.lead_time.strip()
    moq = req.moq.strip()
    unit_price = req.unit_price
    quantity_number = _first_number(quantity)
    total_amount = round(quantity_number * unit_price, 2) if quantity_number and unit_price else None
    risk_points = _quote_risks(trade_term, payment_terms, destination, lead_time, unit_price)
    checklist = _quote_checklist(product, quantity, destination, lead_time, unit_price)

    lines = [
        "Dear Customer,",
        "",
        "Thank you for your inquiry. Please find our quotation draft below:",
        "",
        f"Product: {product}",
        f"Quantity: {quantity or 'To be confirmed'}",
        f"Trade term: {trade_term}",
        f"Destination: {destination or 'To be confirmed'}",
        f"Unit price: {currency} {unit_price:g}" if unit_price else "Unit price: To be confirmed",
    ]
    if total_amount is not None:
        lines.append(f"Total amount: {currency} {total_amount:g}")
    lines.extend([
        f"MOQ: {moq or 'To be confirmed'}",
        f"Lead time: {lead_time or 'To be confirmed'}",
        f"Payment terms: {payment_terms}",
        f"Quotation validity: {max(1, req.validity_days)} days",
    ])
    if req.notes.strip():
        lines.append(f"Remarks: {req.notes.strip()}")
    lines.extend([
        "",
        "The final quotation is subject to confirmed specifications, packaging, destination and shipping cost.",
        "",
        "Best regards,",
    ])

    return {
        "product": product,
        "quantity": quantity,
        "currency": currency,
        "unitPrice": unit_price,
        "totalAmount": total_amount,
        "tradeTerm": trade_term,
        "destination": destination,
        "paymentTerms": payment_terms,
        "leadTime": lead_time,
        "moq": moq,
        "validityDays": max(1, req.validity_days),
        "riskPoints": risk_points,
        "checklist": checklist,
        "emailDraft": "\n".join(lines),
    }


def draft_trade_followup(req: TradeFollowupDraftRequest) -> dict:
    channel = (req.channel.strip() or "email").lower()
    stage = (req.stage.strip() or "first_reply").lower()
    tone = req.tone.strip() or "professional and concise"
    analysis = analyze_trade_inquiry(req.content, "followup")
    extracted = analysis["extracted"]
    product = extracted.get("product") or "your requested product"
    quantity = extracted.get("quantity") or ""
    country = extracted.get("country") or ""
    missing = analysis.get("missingFields") or []

    if stage in {"after_quote", "quoted", "报价后"}:
        subject = f"Follow-up on quotation for {product}"
        opening = "I hope you are doing well. I am following up on the quotation we shared earlier."
        cta = "Could you please let us know your feedback on price, specifications and delivery schedule?"
    elif stage in {"sample", "sample_followup", "样品"}:
        subject = f"Sample confirmation for {product}"
        opening = "Thank you for discussing the sample details with us."
        cta = "Could you please confirm the sample quantity, delivery address and any testing requirements?"
    else:
        subject = f"Re: Inquiry about {product}"
        opening = "Thank you for your inquiry. We are glad to support your project."
        cta = "Could you please confirm the details below so that we can prepare an accurate quotation?"

    detail_lines = [
        f"Product: {product}",
        f"Quantity: {quantity or 'To be confirmed'}",
        f"Destination: {country or 'To be confirmed'}",
    ]
    if missing:
        detail_lines.append("Information needed: " + ", ".join(missing[:5]))

    email_lines = [
        "Dear Customer,",
        "",
        opening,
        "",
        *detail_lines,
        "",
        cta,
        "",
        "Best regards,",
    ]
    whatsapp = (
        f"Hi, thanks for your inquiry about {product}. "
        f"To prepare an accurate quotation, could you confirm {', '.join(missing[:3]) if missing else 'quantity, destination and specifications'}?"
    )
    draft = whatsapp if channel in {"whatsapp", "wa", "im"} else "\n".join(email_lines)
    return {
        "channel": "whatsapp" if channel in {"whatsapp", "wa", "im"} else "email",
        "stage": stage,
        "tone": tone,
        "subject": subject,
        "messageDraft": draft,
        "extracted": extracted,
        "missingFields": missing,
        "riskPoints": analysis.get("riskPoints") or [],
        "nextActions": analysis.get("nextActions") or [],
    }


def _extract_product(text: str) -> str:
    patterns = [
        r"(?:interested in|looking for|need|want|quote for|quotation for)\s+([^.\n,;]{3,80})",
        r"(?:product|item|model)\s*[:：]\s*([^.\n,;]{3,80})",
        r"\b\d{1,7}\s*(?:pcs|pieces|sets|units|cartons|containers|ctns)\s+([^.\n,;]{3,80}?)(?:\s+to\s+|\s+for\s+|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return match.group(1).strip(" .,:;")
    return ""


def _extract_quantity(text: str) -> str:
    match = re.search(r"\b(\d{1,7})\s*(pcs|pieces|sets|units|cartons|containers|ctns)\b", text, re.I)
    return f"{match.group(1)} {match.group(2)}" if match else ""


def _extract_country(lower: str) -> str:
    for key, country in COUNTRY_ALIASES.items():
        if re.search(rf"\b{re.escape(key)}\b", lower):
            return country
    return ""


def _pick_upper(text: str, candidates: list[str]) -> str:
    for item in candidates:
        if re.search(rf"\b{re.escape(item)}\b", text, re.I):
            return item
    return ""


def _buyer_type(lower: str) -> str:
    if any(word in lower for word in ["distributor", "wholesale", "reseller", "dealer"]):
        return "channel_buyer"
    if any(word in lower for word in ["contractor", "project", "hotel", "apartment", "builder"]):
        return "project_buyer"
    if any(word in lower for word in ["factory", "manufacturer", "oem", "odm"]):
        return "oem_buyer"
    return "unknown_buyer"


def _missing_fields(product: str, quantity: str, country: str, trade_term: str, payment_term: str) -> list[str]:
    missing = []
    if not product:
        missing.append("product/model")
    if not quantity:
        missing.append("quantity")
    if not country:
        missing.append("destination country/port")
    if not trade_term:
        missing.append("trade term")
    if not payment_term:
        missing.append("payment term")
    return missing


def _risk_points(lower: str, certifications: list[str], trade_term: str, payment_term: str) -> list[str]:
    risks = []
    if "ddp" in trade_term.lower():
        risks.append("DDP 涉及目的国税费、清关和责任边界，报价前需人工确认")
    if any(word in lower for word in ["urgent", "asap", "very fast"]):
        risks.append("客户要求紧急交付，需确认真实交期后再承诺")
    if any(word in lower for word in ["lowest price", "best price", "target price"]):
        risks.append("客户强价格导向，报价时需保护底价和阶梯价格")
    if not certifications and any(word in lower for word in ["europe", "usa", "uk", "amazon"]):
        risks.append("目标市场可能需要认证/标签要求，需补充合规确认")
    if "l/c" in payment_term.lower() or payment_term == "LC":
        risks.append("L/C 条款需单证人员复核")
    return risks


def _intent_score(lower: str, quantity: str, country: str, trade_term: str, payment_term: str, certifications: list[str]) -> tuple[int, list[str]]:
    score = 25
    signals = []
    if quantity:
        score += 18
        signals.append(f"明确数量：{quantity}")
    if country:
        score += 12
        signals.append(f"明确市场：{country}")
    if trade_term:
        score += 10
        signals.append(f"出现贸易条款：{trade_term}")
    if payment_term:
        score += 8
        signals.append(f"出现付款方式：{payment_term}")
    if certifications:
        score += 8
        signals.append("提到认证：" + ", ".join(certifications[:4]))
    if any(word in lower for word in ["quotation", "quote", "price", "pi", "proforma invoice"]):
        score += 12
        signals.append("明确索要报价/PI")
    if any(word in lower for word in ["sample", "catalog", "datasheet"]):
        score += 6
        signals.append("索要样品或资料")
    if any(word in lower for word in ["just check", "only compare", "for reference"]):
        score -= 12
        signals.append("存在比价/参考倾向")
    return max(0, min(100, score)), signals or ["询盘信息较少，需先补齐关键字段"]


def _next_actions(missing: list[str], risks: list[str], stage: str) -> list[str]:
    actions = []
    if missing:
        actions.append("先追问缺失字段：" + ", ".join(missing[:5]))
    if risks:
        actions.append("涉及风险项，报价/承诺前请人工确认")
    if stage == "high_intent":
        actions.append("24小时内给出报价草稿，并同步样品/MOQ/交期")
    else:
        actions.append("先发送产品目录、案例和关键问题清单")
    return actions


def _reply_draft(product: str, quantity: str, country: str, missing: list[str]) -> str:
    ask = ", ".join(missing[:4])
    base = "Dear Customer,\n\nThank you for your inquiry."
    if product:
        base += f" We have noted your interest in {product}."
    if quantity:
        base += f" Quantity: {quantity}."
    if country:
        base += f" Destination market: {country}."
    if ask:
        base += f"\n\nTo prepare an accurate quotation, could you please confirm: {ask}?"
    base += "\n\nBest regards,"
    return base


def _extract_email(text: str) -> str:
    match = re.search(r"[\w.\-+]+@[\w.\-]+\.[A-Za-z]{2,}", text)
    return match.group(0) if match else ""


def _extract_whatsapp(text: str) -> str:
    match = re.search(r"(?:whatsapp|wa)[:：\s+]*(\+?\d[\d\s\-]{6,20})", text, re.I)
    return match.group(1).strip() if match else ""


def _first_number(value: str) -> float | None:
    match = re.search(r"\d+(?:\.\d+)?", value or "")
    return float(match.group(0)) if match else None


def _quote_risks(trade_term: str, payment_terms: str, destination: str, lead_time: str, unit_price: float | None) -> list[str]:
    risks = []
    if not unit_price:
        risks.append("缺少单价，不能作为正式报价发送")
    if trade_term == "DDP":
        risks.append("DDP 涉及目的国税费、清关和责任边界，必须人工复核")
    if "L/C" in payment_terms.upper() or payment_terms.upper() == "LC":
        risks.append("L/C 付款条款需单证人员复核")
    if not destination:
        risks.append("缺少目的国/目的港，运费和合规要求无法确认")
    if not lead_time:
        risks.append("缺少交期，不能承诺发货时间")
    return risks


def _quote_checklist(product: str, quantity: str, destination: str, lead_time: str, unit_price: float | None) -> list[str]:
    checks = []
    if product:
        checks.append("已填写产品/型号")
    if quantity:
        checks.append("已填写数量")
    if unit_price:
        checks.append("已填写单价")
    if destination:
        checks.append("已填写目的地")
    if lead_time:
        checks.append("已填写交期")
    required = {"已填写产品/型号", "已填写数量", "已填写单价", "已填写目的地", "已填写交期"}
    missing_count = len(required - set(checks))
    if missing_count:
        checks.append(f"仍有 {missing_count} 个关键报价字段待确认")
    return checks
