"""
Documents Router - File upload and management
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import Optional, List
from pathlib import Path

from app.database import get_db
from app.models import Document, ProcurementRequest, User, AuditLog
from app.schemas import DocumentResponse, DocumentType, MessageResponse
from app.services.auth import get_current_user
from app.services.storage import storage

router = APIRouter(prefix="/requests/{request_id}/documents", tags=["Documents"])


@router.get("", response_model=List[DocumentResponse])
async def list_documents(
    request_id: int,
    doc_type: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all documents for a request"""
    query = db.query(Document).filter(Document.request_id == request_id)
    
    if doc_type:
        query = query.filter(Document.doc_type == doc_type)
    
    return query.order_by(Document.uploaded_at.desc()).all()


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    request_id: int,
    file: UploadFile = File(...),
    doc_type: str = Form(default="other"),
    description: Optional[str] = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Upload a document (quote, invoice, PO, etc.)"""
    # Verify request exists
    request = db.query(ProcurementRequest).filter(
        ProcurementRequest.id == request_id
    ).first()
    
    if not request:
        raise HTTPException(status_code=404, detail="Request not found")
    
    # Validate doc_type
    valid_types = [t.value for t in DocumentType]
    if doc_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid document type. Valid types: {', '.join(valid_types)}"
        )
    
    # Save file
    try:
        file_info = await storage.save_file(file, request_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")
    
    # Create database record
    document = Document(
        request_id=request_id,
        doc_type=doc_type,
        filename=file_info["filename"],
        original_filename=file_info["original_filename"],
        file_path=file_info["file_path"],
        file_size=file_info["file_size"],
        mime_type=file_info["mime_type"],
        description=description,
        uploaded_by=current_user.id
    )
    db.add(document)
    
    # Audit log
    audit = AuditLog(
        request_id=request_id,
        user_id=current_user.id,
        action="document_uploaded",
        details={
            "filename": file_info["original_filename"],
            "doc_type": doc_type,
            "size": file_info["file_size"]
        }
    )
    db.add(audit)
    
    db.commit()
    db.refresh(document)
    
    return document


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    request_id: int,
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get document metadata"""
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.request_id == request_id
    ).first()
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return document


@router.delete("/{document_id}", response_model=MessageResponse)
async def delete_document(
    request_id: int,
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a document"""
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.request_id == request_id
    ).first()
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Check request status - more restrictive for certain statuses
    request = db.query(ProcurementRequest).filter(
        ProcurementRequest.id == request_id
    ).first()
    
    if request.status in ["complete"]:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete documents from completed requests"
        )
    
    # Delete file from disk
    storage.delete_file(document.file_path)
    
    # Delete database record
    db.delete(document)
    
    # Audit log
    audit = AuditLog(
        request_id=request_id,
        user_id=current_user.id,
        action="document_deleted",
        details={"filename": document.original_filename, "doc_type": document.doc_type}
    )
    db.add(audit)
    
    db.commit()
    
    return MessageResponse(message="Document deleted", id=document_id)


# Separate router for document downloads (no request_id in path)
download_router = APIRouter(prefix="/documents", tags=["Documents"])


@download_router.get("/{document_id}/download")
async def download_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Download a document file"""
    document = db.query(Document).filter(Document.id == document_id).first()
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Get full file path
    file_path = storage.get_full_path(document.file_path)
    
    if not Path(file_path).exists():
        raise HTTPException(status_code=404, detail="File not found on disk")
    
    return FileResponse(
        path=file_path,
        filename=document.original_filename,
        media_type=document.mime_type
    )
