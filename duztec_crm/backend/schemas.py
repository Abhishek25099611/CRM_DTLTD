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
    end_customer: str = ""    # the plant / end user when the customer is a trader or EPC


class ContactIn(BaseModel):
    customer_id: int
    name: str = Field(min_length=1)
    phone: str = ""
    email: str = ""
    role: str = ""            # legacy free-text; superseded by designation/department
    designation: str = ""
    department: str = ""


class EnquiryIn(BaseModel):
    date: str = ""
    source: str = ""
    customer_id: int
    contact_id: int | None = None
    requirement: str = ""
    system: str = ""
    expected_value: float = 0
    salesperson: str = ""
    priority: str = "Normal"   # holds the Enquiry Type (Normal/Tender/Budgetary/Supporting/Repeat Order)


class ItemIn(BaseModel):
    description: str
    hsn: str = ""
    qty: float = 1
    unit: str = "Nos."
    rate: float = 0
    gst_pct: float = 18
    product_id: int | None = None   # chosen from the Products master (pulls its specification onto the print)


class ProductIn(BaseModel):
    code: str = Field(min_length=1)
    name: str = Field(min_length=1)
    hsn: str = ""
    unit: str = "Nos."
    rate: float = 0
    specification: str = ""
    active: int = 1


class TargetIn(BaseModel):
    email: str
    measure: str = "order_value"
    period_type: str = "monthly"
    period_start: str            # YYYY-MM-DD; the end is derived from period_type
    amount: float = 0
    note: str = ""


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
    type: str = ""            # Enquiry Type carried onto the quotation
    introduction: str = ""
    scope: str = ""
    warranty: str = ""
    guarantee: str = ""
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
    so_no: str = ""
    po_date: str = ""
    value: float = 0


class OrderEditIn(BaseModel):
    po_no: str = ""
    so_no: str = ""
    po_date: str = ""
    value: float = 0
    payment_terms: str = ""
    delivery_date: str = ""
