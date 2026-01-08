"""
Users Router - User management
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import Optional, List
import secrets

from app.database import get_db
from app.models import User
from app.schemas import UserCreate, UserUpdate, UserResponse, MessageResponse
from app.services.auth import get_current_user, require_admin

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("", response_model=List[UserResponse])
async def list_users(
    role: Optional[str] = None,
    department: Optional[str] = None,
    active_only: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all users"""
    query = db.query(User)
    
    if role:
        query = query.filter(User.role == role)
    if department:
        query = query.filter(User.department == department)
    if active_only:
        query = query.filter(User.is_active == 1)
    
    return query.order_by(User.name).all()


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    data: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Create a new user (admin only)"""
    # Check for existing email
    existing = db.query(User).filter(User.email == data.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Generate API key
    api_key = f"pk_{secrets.token_urlsafe(32)}"
    
    user = User(
        email=data.email,
        name=data.name,
        department=data.department,
        role=data.role,
        api_key=api_key
    )
    
    db.add(user)
    db.commit()
    db.refresh(user)
    
    return user


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """Get current user information"""
    return current_user


@router.get("/me/api-key")
async def get_my_api_key(
    current_user: User = Depends(get_current_user)
):
    """Get current user's API key"""
    return {"api_key": current_user.api_key}


@router.post("/me/regenerate-api-key")
async def regenerate_api_key(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Generate a new API key for current user"""
    new_key = f"pk_{secrets.token_urlsafe(32)}"
    current_user.api_key = new_key
    db.commit()
    
    return {"api_key": new_key, "message": "API key regenerated. Update your applications."}


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific user"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    data: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Update a user (admin only)"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(user, field, value)
    
    db.commit()
    db.refresh(user)
    
    return user


@router.delete("/{user_id}", response_model=MessageResponse)
async def deactivate_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Deactivate a user (admin only) - soft delete"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate yourself")
    
    user.is_active = 0
    db.commit()
    
    return MessageResponse(message="User deactivated", id=user_id)


@router.get("/approvers/list", response_model=List[UserResponse])
async def list_approvers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all users who can approve requests"""
    return db.query(User).filter(
        User.role.in_(["approver", "admin"]),
        User.is_active == 1
    ).order_by(User.name).all()
