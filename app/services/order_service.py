from uuid import uuid4
from sqlalchemy.orm import Session
from app.models.order import Order


def create_order(db: Session, session_id: str, context: dict) -> dict:
    customer = context.get("customer", {})
    plan = context.get("selected_plan")
    payment = context.get("payment", {})
    address = context.get("service_address") or context.get("qualified_address") or ({"pincode": context.get("pincode")} if context.get("pincode") else {})
    appointment = context.get("appointment")
    if not plan or not address or not appointment or payment.get("status") != "completed":
        raise ValueError("A selected plan, service address, appointment, and completed payment are required")

    order_id = f"QCOM-{uuid4().hex[:10].upper()}"
    order = Order(order_id=order_id, session_id=session_id, customer_id=customer.get("customer_id"),
                  plan_id=plan["plan_id"], service_pincode=address["pincode"],
                  payment_status=payment["status"], amount_inr=plan["price_inr"], details=context)
    db.add(order)
    db.commit()
    return {"order_id": order_id, "status": "confirmed", "amount_inr": plan["price_inr"],
            "plan": plan, "service_address": address, "appointment": appointment}
