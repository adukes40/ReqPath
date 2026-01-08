"""
SQLAlchemy ORM models
"""
from sqlalchemy import (
    Column, Integer, String, Text, Numeric, DateTime, 
    ForeignKey, Enum, JSON
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import enum


class UserRole(str, enum.Enum):
    requester = "requester"
    approver = "approver"
    admin = "admin"


class RequestStatus(str, enum.Enum):
    draft = "draft"
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    ordered = "ordered"
    received = "received"
    complete = "complete"
    cancelled = "cancelled"


class DocumentType(str, enum.Enum):
    quote = "quote"
    invoice = "invoice"
    po = "po"
    receipt = "receipt"
    contract = "contract"
    other = "other"


class ApprovalStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


# =============================================================================
# MODELS
# =============================================================================

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=False)
    department = Column(String(100))
    role = Column(String(50), default=UserRole.requester)
    hashed_password = Column(String(255))
    api_key = Column(String(255), unique=True, index=True)
    is_active = Column(Integer, default=1)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    requests = relationship("ProcurementRequest", back_populates="requester")
    approvals = relationship("Approval", back_populates="approver")


class ProcurementRequest(Base):
    __tablename__ = "requests"
    
    id = Column(Integer, primary_key=True, index=True)
    requester_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    department = Column(String(100))
    status = Column(String(50), default=RequestStatus.draft, index=True)
    priority = Column(String(20), default="normal")  # low, normal, high, urgent
    
    # Financial
    total_amount = Column(Numeric(12, 2), default=0)
    budget_code = Column(String(50))
    fiscal_year = Column(String(10))
    
    # Vendor info
    preferred_vendor = Column(String(255))
    
    # Dates
    needed_by = Column(DateTime)
    ordered_at = Column(DateTime)
    received_at = Column(DateTime)
    
    # Tracking
    po_number = Column(String(100))
    notes = Column(Text)
    
    created_at = Column(DateTime, server_default=func.now(), index=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    requester = relationship("User", back_populates="requests")
    line_items = relationship("LineItem", back_populates="request", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="request", cascade="all, delete-orphan")
    approvals = relationship("Approval", back_populates="request", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="request", cascade="all, delete-orphan")


class LineItem(Base):
    __tablename__ = "line_items"
    
    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(Integer, ForeignKey("requests.id", ondelete="CASCADE"), nullable=False)
    
    description = Column(String(500), nullable=False)
    quantity = Column(Integer, default=1)
    unit = Column(String(50))  # each, box, case, etc.
    unit_price = Column(Numeric(10, 2))
    total_price = Column(Numeric(10, 2))
    
    vendor = Column(String(255))
    vendor_sku = Column(String(100))
    category = Column(String(100))
    
    notes = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    
    # Relationships
    request = relationship("ProcurementRequest", back_populates="line_items")


class Document(Base):
    __tablename__ = "documents"
    
    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(Integer, ForeignKey("requests.id", ondelete="CASCADE"), nullable=False)
    
    doc_type = Column(String(50), default=DocumentType.other)
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255))
    file_path = Column(String(500), nullable=False)
    file_size = Column(Integer)
    mime_type = Column(String(100))
    
    description = Column(Text)
    uploaded_by = Column(Integer, ForeignKey("users.id"))
    uploaded_at = Column(DateTime, server_default=func.now())
    
    # Relationships
    request = relationship("ProcurementRequest", back_populates="documents")


class Approval(Base):
    __tablename__ = "approvals"
    
    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(Integer, ForeignKey("requests.id", ondelete="CASCADE"), nullable=False)
    approver_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    status = Column(String(50), default=ApprovalStatus.pending)
    comments = Column(Text)
    
    requested_at = Column(DateTime, server_default=func.now())
    decided_at = Column(DateTime)
    
    # Relationships
    request = relationship("ProcurementRequest", back_populates="approvals")
    approver = relationship("User", back_populates="approvals")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(Integer, ForeignKey("requests.id", ondelete="CASCADE"))
    user_id = Column(Integer, ForeignKey("users.id"))
    
    action = Column(String(100), nullable=False)  # created, updated, submitted, approved, etc.
    details = Column(JSON)  # Store changed fields, old/new values
    ip_address = Column(String(45))
    
    created_at = Column(DateTime, server_default=func.now(), index=True)
    
    # Relationships
    request = relationship("ProcurementRequest", back_populates="audit_logs")


class Vendor(Base):
    """Optional: Track vendors separately for reporting"""
    __tablename__ = "vendors"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, unique=True)
    contact_name = Column(String(255))
    email = Column(String(255))
    phone = Column(String(50))
    address = Column(Text)
    website = Column(String(255))
    notes = Column(Text)
    is_active = Column(Integer, default=1)
    created_at = Column(DateTime, server_default=func.now())
