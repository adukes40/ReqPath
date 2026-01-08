"""
Approvals Router - Approval workflow management
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_
from typing import Optional, List
from datetime import datetime

from app.database import get_db
from app.models import Approval, ProcurementRequest, User, AuditLog, ApprovalStatus
from app.schemas import ApprovalCreate, ApprovalDecision, ApprovalResponse, MessageResponse
from app.services.auth import get_current_user, require_approver

router = APIRouter(tags=["Approvals"])


# =============================================================================
# REQUEST-SPECIFIC APPROVAL ENDPOINTS
# =============================================================================

@router.get("/requests/{request_id}/approvals", response_model=List[ApprovalResponse])
async def list_request_approvals(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all approvals for a specific request"""
    approvals = db.query(Approval).options(
        joinedload(Approval.approver)
    ).filter(
        Approval.request_id == request_id
    ).order_by(Approval.requested_at.desc()).all()
    
    return approvals


@router.post("/requests/{request_id}/approvals", response_model=ApprovalResponse, status_code=status.HTTP_201_CREATED)
async def request_approval(
    request_id: int,
    data: ApprovalCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Request approval from a specific user"""
    # Verify request exists and is in pending status
    request = db.query(ProcurementRequest).filter(
        ProcurementRequest.id == request_id
    ).first()
    
    if not request:
        raise HTTPException(status_code=404, detail="Request not found")
    
    if request.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot request approval for request in '{request.status}' status"
        )
    
    # Verify approver exists and has approval rights
    approver = db.query(User).filter(User.id == data.approver_id).first()
    if not approver:
        raise HTTPException(status_code=404, detail="Approver not found")
    
    if approver.role not in ["approver", "admin"]:
        raise HTTPException(
            status_code=400,
            detail="Selected user does not have approval rights"
        )
    
    # Check for existing pending approval from this approver
    existing = db.query(Approval).filter(
        Approval.request_id == request_id,
        Approval.approver_id == data.approver_id,
        Approval.status == "pending"
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=400,
            detail="Approval already pending from this user"
        )
    
    # Create approval request
    approval = Approval(
        request_id=request_id,
        approver_id=data.approver_id,
        status="pending"
    )
    db.add(approval)
    
    # Audit log
    audit = AuditLog(
        request_id=request_id,
        user_id=current_user.id,
        action="approval_requested",
        details={"approver_id": data.approver_id, "approver_name": approver.name}
    )
    db.add(audit)
    
    db.commit()
    db.refresh(approval)
    
    return approval


@router.post("/requests/{request_id}/approve", response_model=ApprovalResponse)
async def approve_request(
    request_id: int,
    data: ApprovalDecision,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_approver)
):
    """Approve a procurement request"""
    return await _process_approval(db, request_id, current_user, "approved", data.comments)


@router.post("/requests/{request_id}/reject", response_model=ApprovalResponse)
async def reject_request(
    request_id: int,
    data: ApprovalDecision,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_approver)
):
    """Reject a procurement request"""
    return await _process_approval(db, request_id, current_user, "rejected", data.comments)


async def _process_approval(
    db: Session, 
    request_id: int, 
    user: User, 
    decision: str,
    comments: Optional[str] = None
) -> Approval:
    """Process approval/rejection"""
    # Verify request exists and is pending
    request = db.query(ProcurementRequest).filter(
        ProcurementRequest.id == request_id
    ).first()
    
    if not request:
        raise HTTPException(status_code=404, detail="Request not found")
    
    if request.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot approve/reject request in '{request.status}' status"
        )
    
    # Find or create approval record for this user
    approval = db.query(Approval).filter(
        Approval.request_id == request_id,
        Approval.approver_id == user.id,
        Approval.status == "pending"
    ).first()
    
    if not approval:
        # Create new approval record if user is approver/admin
        approval = Approval(
            request_id=request_id,
            approver_id=user.id,
            status="pending"
        )
        db.add(approval)
        db.flush()
    
    # Update approval
    approval.status = decision
    approval.comments = comments
    approval.decided_at = datetime.utcnow()
    
    # Update request status
    if decision == "approved":
        request.status = "approved"
    else:
        request.status = "rejected"
    
    # Audit log
    audit = AuditLog(
        request_id=request_id,
        user_id=user.id,
        action=f"request_{decision}",
        details={"comments": comments}
    )
    db.add(audit)
    
    db.commit()
    db.refresh(approval)
    
    return approval


# =============================================================================
# APPROVER DASHBOARD ENDPOINTS
# =============================================================================

@router.get("/approvals/pending", response_model=List[ApprovalResponse])
async def get_pending_approvals(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_approver)
):
    """Get all pending approvals for the current user"""
    approvals = db.query(Approval).options(
        joinedload(Approval.request)
    ).filter(
        Approval.approver_id == current_user.id,
        Approval.status == "pending"
    ).order_by(Approval.requested_at.asc()).all()
    
    return approvals


@router.get("/approvals/history", response_model=List[ApprovalResponse])
async def get_approval_history(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_approver)
):
    """Get approval history for the current user"""
    approvals = db.query(Approval).options(
        joinedload(Approval.request)
    ).filter(
        Approval.approver_id == current_user.id,
        Approval.status != "pending"
    ).order_by(Approval.decided_at.desc()).limit(limit).all()
    
    return approvals
