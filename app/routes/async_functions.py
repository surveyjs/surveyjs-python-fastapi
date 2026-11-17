"""Async Calculations and Validation: GET /api/customers/exists?email= and GET /api/shipping?postcode=."""

import re

from fastapi import APIRouter

from app.db import Db

router = APIRouter()

# Only a whole German (10115) or UK (SW1A 1AA) postcode gets a price, not anything that starts with a prefix
POSTCODE = re.compile(r"^(\d{5}|[A-Z]{1,2}\d[A-Z\d]?\d[A-Z]{2})$")


# region sjs:async-functions.server
# GET /api/customers/exists?email= — answers emailExists()
@router.get("/api/customers/exists")
def customer_exists(db: Db, email: str = "") -> dict[str, bool]:
    row = db.execute("SELECT 1 FROM customers WHERE email = ?", (email.strip().lower(),)).fetchone()
    return {"exists": row is not None}


# GET /api/shipping?postcode= — answers shippingCost(): the longest matching postcode prefix wins,
# { "price": null } when none matches (the form shows "We don't deliver to this postcode yet")
@router.get("/api/shipping")
def shipping(db: Db, postcode: str = "") -> dict[str, float | None]:
    postcode = postcode.replace(" ", "").upper()
    if not POSTCODE.match(postcode):
        return {"price": None}
    rate = db.execute(
        "SELECT price FROM shipping_rates WHERE substr(?, 1, length(postcode_prefix)) = postcode_prefix"
        " ORDER BY length(postcode_prefix) DESC",
        (postcode,),
    ).fetchone()
    return {"price": rate["price"] if rate else None}
# endregion
