"""
Procurement Requests Router - CRUD operations
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, or_
from typing import Optional, List
from datetime import datetime
from decimal import Decimal

from app.database import get_db
from app.models import ProcurementRequest, LineItem, User, AuditLog, RequestStatus
from app.schemas import (
    RequestCreate, RequestUpdate, RequestResponse, RequestListResponse,
    LineItemCreate, LineItemUpdate, LineItemResponse,
    StatusUpdate, MessageResponse
)
from app.services.auth import get_current_user

router = APIRouter(prefix="/requests", tags=["Procurement Requests"])


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def calculate_total(db: Session, request_id: int) -> Decimal:
    """Recalculate request total from line items"""
    result = db.query(func.sum(LineItem.total_price)).filter(
        LineItem.request_id == request_id
    ).scalar()
    return result or Decimal("0")


def log_action(
    db: Session, 
    request_id: int, 
    user_id: int, 
    action: str, 
    details: dict = None
):
    """Create audit log entry"""
    log = AuditLog(
        request_id=request_id,
        user_id=user_id,
        action=action,
        details=details
    )
    db.add(log)


# Valid status transitions
VALID_TRANSITIONS = {
    "draft": ["pending", "cancelled"],
    "pending": ["approved", "rejected", "draft"],
    "approved": ["ordered", "cancelled"],
    "rejected": ["draft"],
    "ordered": ["received", "cancelled"],
    "received": ["complete"],
    "complete": [],
    "cancelled": ["draft"]
}


# =============================================================================
# REQUEST ENDPOINTS
# =============================================================================

@router.get("", response_model=List[RequestListResponse])
async def list_requests(
    status: Optional[str] = Query(None, description="Filter by status"),
    department: Optional[str] = Query(None, description="Filter by department"),
    requester_id: Optional[int] = Query(None, description="Filter by requester"),
    priority: Optional[str] = Query(None, description="Filter by priority"),
    search: Optional[str] = Query(None, description="Search title/description"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all procurement requests with optional filters"""
    query = db.query(ProcurementRequest).options(
        joinedload(ProcurementRequest.requester)
    )
    
    # Apply filters
    if status:
        query = query.filter(ProcurementRequest.status == status)
    if department:
        query = query.filter(ProcurementRequest.department == department)
    if requester_id:
        query = query.filter(ProcurementRequest.requester_id == requester_id)
    if priority:
        query = query.filter(ProcurementRequest.priority == priority)
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                ProcurementRequest.title.ilike(search_term),
                ProcurementRequest.description.ilike(search_term)
            )
        )
    
    # Order and paginate
    query = query.order_by(ProcurementRequest.created_at.desc())
    offset = (page - 1) * page_size
    requests = query.offset(offset).limit(page_size).all()
    
    # Build response with requester name
    result = []
    for req in requests:
        item = RequestListResponse(
            id=req.id,
            title=req.title,
            department=req.department,
            status=req.status,
            priority=req.priority,
            total_amount=req.total_amount,
            requester_id=req.requester_id,
            requester_name=req.requester.name if req.requester else None,
            created_at=req.created_at,
            needed_by=req.needed_by
        )
        result.append(item)
    
    return result


@router.post("", response_model=RequestResponse, status_code=status.HTTP_201_CREATED)
async def create_request(
    data: RequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new procurement request"""
    # Create request
    request = ProcurementRequest(
        requester_id=current_user.id,
        title=data.title,
        description=data.description,
        department=data.department or current_user.department,
        priority=data.priority,
        budget_code=data.budget_code,
        fiscal_year=data.fiscal_year,
        preferred_vendor=data.preferred_vendor,
        needed_by=data.needed_by,
        notes=data.notes,
        status="draft"
    )
    db.add(request)
    db.flush()  # Get the ID
    
    # Add line items if provided
    if data.line_items:
        for item_data in data.line_items:
            item = LineItem(
                request_id=request.id,
                description=item_data.description,
                quantity=item_data.quantity,
                unit=item_data.unit,
                unit_price=item_data.unit_price,
                total_price=(item_data.unit_price or 0) * item_data.quantity,
                vendor=item_data.vendor,
                vendor_sku=item_data.vendor_sku,
                category=item_data.category,
                notes=item_data.notes
            )
            db.add(item)
        
        db.flush()
        request.total_amount = calculate_total(db, request.id)
    
    # Audit log
    log_action(db, request.id, current_user.id, "created", {"title": data.title})
    
    db.commit()
    db.refresh(request)
    
    return request


@router.get("/{request_id}", response_model=RequestResponse)
async def get_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a single procurement request with all details"""
    request = db.query(ProcurementRequest).options(
        joinedload(ProcurementRequest.requester),
        joinedload(ProcurementRequest.line_items),
        joinedload(ProcurementRequest.documents),
        joinedload(ProcurementRequest.approvals).joinedload("approver")
    ).filter(ProcurementRequest.id == request_id).first()
    
    if not request:
        raise HTTPException(status_code=404, detail="Request not found")
    
    return request


@router.patch("/{request_id}", response_model=RequestResponse)
async def update_request(
    request_id: int,
    data: RequestUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a procurement request (only allowed in draft status)"""
    request = db.query(ProcurementRequest).filter(
        ProcurementRequest.id == request_id
    ).first()
    
    if not request:
        raise HTTPException(status_code=404, detail="Request not found")
    
    # Only allow edits in draft or rejected status
    if request.status not in ["draft", "rejected"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot edit request in '{request.status}' status"
        )
    
    # Track changes for audit
    changes = {}
    update_data = data.model_dump(exclude_unset=True)
    
    for field, value in update_data.items():
        old_value = getattr(request, field)
        if old_value != value:
            changes[field] = {"old": str(old_value), "new": str(value)}
            setattr(request, field, value)
    
    if changes:
        log_action(db, request_id, current_user.id, "updated", changes)
    
    db.commit()
    db.refresh(request)
    
    return request


@router.delete("/{request_id}", response_model=MessageResponse)
async def delete_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a procurement request (only allowed in draft status)"""
    request = db.query(ProcurementRequest).filter(
        ProcurementRequest.id == request_id
    ).first()
    
    if not request:
        raise HTTPException(status_code=404, detail="Request not found")
    
    if request.status != "draft":
        raise HTTPException(
            status_code=400,
            detail="Can only delete requests in draft status"
        )
    
    db.delete(request)
    db.commit()
    
    return MessageResponse(message="Request deleted", id=request_id)


# =============================================================================
# STATUS TRANSITIONS
# =============================================================================

@router.post("/{request_id}/submit", response_model=RequestResponse)
async def submit_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Submit a draft request for approval"""
    request = db.query(ProcurementRequest).filter(
        ProcurementRequest.id == request_id
    ).first()
    
    if not request:
        raise HTTPException(status_code=404, detail="Request not found")
    
    if request.status != "draft":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot submit request in '{request.status}' status"
        )
    
    # Validate request has line items
    if not request.line_items:
        raise HTTPException(
            status_code=400,
            detail="Cannot submit request without line items"
        )
    
    request.status = "pending"
    log_action(db, request_id, current_user.id, "submitted")
    
    db.commit()
    db.refresh(request)
    
    return request


@router.post("/{request_id}/status", response_model=RequestResponse)
async def update_status(
    request_id: int,
    data: StatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update request status (for admins and workflow)"""
    request = db.query(ProcurementRequest).filter(
        ProcurementRequest.id == request_id
    ).first()
    
    if not request:
        raise HTTPException(status_code=404, detail="Request not found")
    
    # Validate transition
    new_status = data.status.value
    current_status = request.status
    
    if new_status not in VALID_TRANSITIONS.get(current_status, []):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot transition from '{current_status}' to '{new_status}'"
        )
    
    # Update status and related timestamps
    request.status = new_status
    
    if new_status == "ordered":
        request.ordered_at = datetime.utcnow()
    elif new_status == "received":
        request.received_at = datetime.utcnow()
    
    log_action(
        db, request_id, current_user.id, 
        f"status_changed_{new_status}",
        {"from": current_status, "to": new_status, "notes": data.notes}
    )
    
    db.commit()
    db.refresh(request)
    
    return request


# =============================================================================
# LINE ITEMS
# =============================================================================

@router.get("/{request_id}/items", response_model=List[LineItemResponse])
async def list_line_items(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all line items for a request"""
    items = db.query(LineItem).filter(LineItem.request_id == request_id).all()
    return items


@router.post("/{request_id}/items", response_model=LineItemResponse, status_code=status.HTTP_201_CREATED)
async def add_line_item(
    request_id: int,
    data: LineItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Add a line item to a request"""
    request = db.query(ProcurementRequest).filter(
        ProcurementRequest.id == request_id
    ).first()
    
    if not request:
        raise HTTPException(status_code=404, detail="Request not found")
    
    if request.status not in ["draft", "rejected"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot add items to request in '{request.status}' status"
        )
    
    # Create line item
    total = (data.unit_price or 0) * data.quantity
    item = LineItem(
        request_id=request_id,
        description=data.description,
        quantity=data.quantity,
        unit=data.unit,
        unit_price=data.unit_price,
        total_price=total,
        vendor=data.vendor,
        vendor_sku=data.vendor_sku,
        category=data.category,
        notes=data.notes
    )
    db.add(item)
    
    # Update request total
    db.flush()
    request.total_amount = calculate_total(db, request_id)
    
    log_action(db, request_id, current_user.id, "item_added", {"description": data.description})
    
    db.commit()
    db.refresh(item)
    
    return item


@router.patch("/{request_id}/items/{item_id}", response_model=LineItemResponse)
async def update_line_item(
    request_id: int,
    item_id: int,
    data: LineItemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a line item"""
    item = db.query(LineItem).filter(
        LineItem.id == item_id,
        LineItem.request_id == request_id
    ).first()
    
    if not item:
        raise HTTPException(status_code=404, detail="Line item not found")
    
    request = db.query(ProcurementRequest).filter(
        ProcurementRequest.id == request_id
    ).first()
    
    if request.status not in ["draft", "rejected"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot edit items on request in '{request.status}' status"
        )
    
    # Update fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(item, field, value)
    
    # Recalculate totals
    item.total_price = (item.unit_price or 0) * item.quantity
    db.flush()
    request.total_amount = calculate_total(db, request_id)
    
    db.commit()
    db.refresh(item)
    
    return item


@router.delete("/{request_id}/items/{item_id}", response_model=MessageResponse)
async def delete_line_item(
    request_id: int,
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a line item"""
    item = db.query(LineItem).filter(
        LineItem.id == item_id,
        LineItem.request_id == request_id
    ).first()
    
    if not item:
        raise HTTPException(status_code=404, detail="Line item not found")
    
    request = db.query(ProcurementRequest).filter(
        ProcurementRequest.id == request_id
    ).first()
    
    if request.status not in ["draft", "rejected"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete items from request in '{request.status}' status"
        )
    
    db.delete(item)
    db.flush()
    
    # Update request total
    request.total_amount = calculate_total(db, request_id)
    
    log_action(db, request_id, current_user.id, "item_deleted", {"item_id": item_id})
    
    db.commit()
    
    return MessageResponse(message="Line item deleted", id=item_id)
