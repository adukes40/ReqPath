"""
Pydantic schemas for request/response validation
"""
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import Optional, List
from datetime import datetime
from decimal import Decimal
from enum import Enum


# =============================================================================
# ENUMS
# =============================================================================

class UserRole(str, Enum):
    requester = "requester"
    approver = "approver"
    admin = "admin"


class RequestStatus(str, Enum):
    draft = "draft"
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    ordered = "ordered"
    received = "received"
    complete = "complete"
    cancelled = "cancelled"


class DocumentType(str, Enum):
    quote = "quote"
    invoice = "invoice"
    po = "po"
    receipt = "receipt"
    contract = "contract"
    other = "other"


class Priority(str, Enum):
    low = "low"
    normal = "normal"
    high = "high"
    urgent = "urgent"


# =============================================================================
# USER SCHEMAS
# =============================================================================

class UserBase(BaseModel):
    email: EmailStr
    name: str
    department: Optional[str] = None
    role: UserRole = UserRole.requester


class UserCreate(UserBase):
    password: Optional[str] = None


class UserUpdate(BaseModel):
    name: Optional[str] = None
    department: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[int] = None


class UserResponse(UserBase):
    id: int
    is_active: int
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# LINE ITEM SCHEMAS
# =============================================================================

class LineItemBase(BaseModel):
    description: str
    quantity: int = 1
    unit: Optional[str] = None
    unit_price: Optional[Decimal] = None
    vendor: Optional[str] = None
    vendor_sku: Optional[str] = None
    category: Optional[str] = None
    notes: Optional[str] = None


class LineItemCreate(LineItemBase):
    pass


class LineItemUpdate(BaseModel):
    description: Optional[str] = None
    quantity: Optional[int] = None
    unit: Optional[str] = None
    unit_price: Optional[Decimal] = None
    vendor: Optional[str] = None
    vendor_sku: Optional[str] = None
    category: Optional[str] = None
    notes: Optional[str] = None


class LineItemResponse(LineItemBase):
    id: int
    request_id: int
    total_price: Optional[Decimal] = None
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# DOCUMENT SCHEMAS
# =============================================================================

class DocumentBase(BaseModel):
    doc_type: DocumentType = DocumentType.other
    description: Optional[str] = None


class DocumentResponse(DocumentBase):
    id: int
    request_id: int
    filename: str
    original_filename: Optional[str] = None
    file_size: Optional[int] = None
    mime_type: Optional[str] = None
    uploaded_by: Optional[int] = None
    uploaded_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# APPROVAL SCHEMAS
# =============================================================================

class ApprovalCreate(BaseModel):
    approver_id: int


class ApprovalDecision(BaseModel):
    status: str = Field(..., pattern="^(approved|rejected)$")
    comments: Optional[str] = None


class ApprovalResponse(BaseModel):
    id: int
    request_id: int
    approver_id: int
    status: str
    comments: Optional[str] = None
    requested_at: datetime
    decided_at: Optional[datetime] = None
    approver: Optional[UserResponse] = None
    
    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# PROCUREMENT REQUEST SCHEMAS
# =============================================================================

class RequestBase(BaseModel):
    title: str
    description: Optional[str] = None
    department: Optional[str] = None
    priority: Priority = Priority.normal
    budget_code: Optional[str] = None
    fiscal_year: Optional[str] = None
    preferred_vendor: Optional[str] = None
    needed_by: Optional[datetime] = None
    notes: Optional[str] = None


class RequestCreate(RequestBase):
    line_items: Optional[List[LineItemCreate]] = None


class RequestUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    department: Optional[str] = None
    priority: Optional[Priority] = None
    budget_code: Optional[str] = None
    fiscal_year: Optional[str] = None
    preferred_vendor: Optional[str] = None
    needed_by: Optional[datetime] = None
    notes: Optional[str] = None
    po_number: Optional[str] = None


class RequestResponse(RequestBase):
    id: int
    requester_id: int
    status: RequestStatus
    total_amount: Optional[Decimal] = None
    po_number: Optional[str] = None
    ordered_at: Optional[datetime] = None
    received_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    
    requester: Optional[UserResponse] = None
    line_items: List[LineItemResponse] = []
    documents: List[DocumentResponse] = []
    approvals: List[ApprovalResponse] = []
    
    model_config = ConfigDict(from_attributes=True)


class RequestListResponse(BaseModel):
    """Lighter response for list views"""
    id: int
    title: str
    department: Optional[str] = None
    status: RequestStatus
    priority: Priority
    total_amount: Optional[Decimal] = None
    requester_id: int
    requester_name: Optional[str] = None
    created_at: datetime
    needed_by: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# STATUS TRANSITION
# =============================================================================

class StatusUpdate(BaseModel):
    status: RequestStatus
    notes: Optional[str] = None


# =============================================================================
# REPORT SCHEMAS
# =============================================================================

class SpendingReport(BaseModel):
    period: str
    department: Optional[str] = None
    total_amount: Decimal
    request_count: int
    avg_amount: Decimal


class VendorReport(BaseModel):
    vendor: str
    total_amount: Decimal
    item_count: int
    request_count: int


class StatusReport(BaseModel):
    status: str
    count: int
    total_amount: Decimal


# =============================================================================
# API RESPONSES
# =============================================================================

class PaginatedResponse(BaseModel):
    items: List
    total: int
    page: int
    page_size: int
    pages: int


class MessageResponse(BaseModel):
    message: str
    id: Optional[int] = None
