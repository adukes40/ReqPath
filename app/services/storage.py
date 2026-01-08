"""
File storage service - handles document uploads
"""
import os
import uuid
import aiofiles
from pathlib import Path
from typing import Optional
from datetime import datetime
from fastapi import UploadFile, HTTPException
from app.config import get_settings

settings = get_settings()


class StorageService:
    def __init__(self, base_path: Optional[str] = None):
        self.base_path = Path(base_path or settings.upload_dir)
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.max_size = settings.max_upload_size_mb * 1024 * 1024  # Convert to bytes
        self.allowed_extensions = set(settings.allowed_extensions.lower().split(","))
    
    def _get_extension(self, filename: str) -> str:
        """Extract file extension"""
        return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    
    def _validate_file(self, filename: str, size: int) -> None:
        """Validate file extension and size"""
        ext = self._get_extension(filename)
        
        if ext not in self.allowed_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"File type '{ext}' not allowed. Allowed: {', '.join(self.allowed_extensions)}"
            )
        
        if size > self.max_size:
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Maximum size: {settings.max_upload_size_mb}MB"
            )
    
    def _generate_path(self, request_id: int, filename: str) -> tuple[str, str]:
        """Generate unique file path: uploads/YYYY/MM/request_id/uuid_filename"""
        now = datetime.now()
        ext = self._get_extension(filename)
        unique_name = f"{uuid.uuid4().hex[:12]}.{ext}"
        
        # Organize by year/month/request_id
        relative_dir = f"{now.year}/{now.month:02d}/{request_id}"
        full_dir = self.base_path / relative_dir
        full_dir.mkdir(parents=True, exist_ok=True)
        
        relative_path = f"{relative_dir}/{unique_name}"
        full_path = str(full_dir / unique_name)
        
        return full_path, relative_path
    
    async def save_file(
        self, 
        file: UploadFile, 
        request_id: int
    ) -> dict:
        """
        Save uploaded file to disk
        Returns: {filename, original_filename, file_path, file_size, mime_type}
        """
        # Read file content
        content = await file.read()
        file_size = len(content)
        
        # Validate
        self._validate_file(file.filename, file_size)
        
        # Generate paths
        full_path, relative_path = self._generate_path(request_id, file.filename)
        
        # Write file
        async with aiofiles.open(full_path, "wb") as f:
            await f.write(content)
        
        return {
            "filename": os.path.basename(full_path),
            "original_filename": file.filename,
            "file_path": relative_path,
            "file_size": file_size,
            "mime_type": file.content_type
        }
    
    def get_full_path(self, relative_path: str) -> str:
        """Convert relative path to full filesystem path"""
        full_path = self.base_path / relative_path
        
        # Security: ensure path is within base directory
        try:
            full_path.resolve().relative_to(self.base_path.resolve())
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid file path")
        
        return str(full_path)
    
    def delete_file(self, relative_path: str) -> bool:
        """Delete a file from storage"""
        try:
            full_path = Path(self.get_full_path(relative_path))
            if full_path.exists():
                full_path.unlink()
                return True
        except Exception:
            pass
        return False
    
    def file_exists(self, relative_path: str) -> bool:
        """Check if file exists"""
        full_path = Path(self.get_full_path(relative_path))
        return full_path.exists()


# Singleton instance
storage = StorageService()
