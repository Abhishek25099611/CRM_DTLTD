"""Pydantic request models."""
from __future__ import annotations

from pydantic import BaseModel, Field


class CustomerIn(BaseModel):
    name: str = Field(min_length=1)
    gstin: str = ""
    address: str = ""
    state: str = ""
    pincode: str = ""
    segment: str = ""


class ContactIn(BaseModel):
    customer_id: int
    name: str = Field(min_length=1)
    phone: str = ""
    email: str = ""
    role: str = ""


class EnquiryIn(BaseModel):
    date: str = ""
    source: str = ""
    customer_id: int
    contact_id: int | None = None
    requirement: str = ""
    system: str = ""
    expected_value: float = 0
    salesperson: str = ""
    priority: str = "Normal"


class ItemIn(BaseModel):
    description: str
    hsn: str = ""
    qty: float = 1
    unit: str = "Nos."
    rate: float = 0
    gst_pct: float = 18


class QuotationIn(BaseModel):
    enquiry_id: int | None = None
    customer_id: int
    contact_id: int | None = None
    date: str = ""
    validity_days: int = 0
    delivery_terms: str = ""
    payment_terms: str = ""
    notes: str = ""
    gst_mode: str = "intra"
    discount_pct: float = 0
    salesperson: str = ""
    items: list[ItemIn] = []


class FollowupIn(BaseModel):
    entity_type: str
    entity_id: int
    due_date: str
    channel: str = "Call"
    note: str = ""


class AssignRkzIn(BaseModel):
    entity_type: str          # enquiry | quotation | order
    ids: list[int]
    rkz: str


class StatusIn(BaseModel):
    status: str
    reason: str = ""
    po_no: str = ""
    po_date: str = ""
    value: float = 0
