"""
Authentication service - API key and future JWT support
"""
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader, APIKeyQuery
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.models import User
from app.config import get_settings

settings = get_settings()

# API Key can be passed in header or query param
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
api_key_query = APIKeyQuery(name="api_key", auto_error=False)


async def get_api_key(
    header_key: Optional[str] = Security(api_key_header),
    query_key: Optional[str] = Security(api_key_query),
) -> str:
    """Extract API key from header or query parameter"""
    api_key = header_key or query_key
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required. Pass via X-API-Key header or api_key query param"
        )
    return api_key


async def get_current_user(
    api_key: str = Depends(get_api_key),
    db: Session = Depends(get_db)
) -> User:
    """
    Validate API key and return associated user
    """
    # Check static API keys first (for system/admin access)
    static_keys = settings.api_keys.split(",") if settings.api_keys else []
    if api_key in static_keys:
        # Return a system user for static keys
        system_user = db.query(User).filter(User.email == "system@local").first()
        if not system_user:
            # Create system user if doesn't exist
            system_user = User(
                email="system@local",
                name="System",
                role="admin"
            )
            db.add(system_user)
            db.commit()
            db.refresh(system_user)
        return system_user
    
    # Check user API keys
    user = db.query(User).filter(
        User.api_key == api_key,
        User.is_active == 1
    ).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )
    
    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """Ensure user is active"""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled"
        )
    return current_user


def require_role(*roles: str):
    """Dependency factory for role-based access control"""
    async def role_checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required role: {', '.join(roles)}"
            )
        return user
    return role_checker


# Convenience dependencies
require_admin = require_role("admin")
require_approver = require_role("admin", "approver")
