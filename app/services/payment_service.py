import secrets


def create_purl(session_id: str, amount_inr: int) -> dict:
    return {"purl": f"https://mock-pay.qcom.local/pay/{secrets.token_urlsafe(12)}",
            "session_id": session_id, "amount_inr": amount_inr, "status": "pending"}


def confirm_payment(payment: dict, confirmation_code: str | None = None) -> dict:
    payment = {**payment, "status": "completed", "confirmation_code": confirmation_code or "MOCK-PAID"}
    return payment

