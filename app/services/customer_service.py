from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.customer import Customer


def find_or_validate(db: Session, customer_id: str | None, name: str | None, phone: str | None,
                     email: str | None, existing_pincode: str | None) -> dict:
    customer = db.scalar(select(Customer).where(Customer.customer_id == customer_id)) if customer_id else None
    if customer:
        return {"customer_id": customer.customer_id, "name": customer.name, "phone": customer.phone,
                "email": customer.email, "existing_pincode": customer.existing_pincode}
    if not name or not phone or not email:
        raise ValueError("name, phone, and email are required")
    return {"customer_id": None, "name": name, "phone": phone, "email": email,
            "existing_pincode": existing_pincode}

