import os
import uuid
import aiofiles
from pathlib import Path
from fastapi import HTTPException, UploadFile
from app.config import settings

# Allowed file types
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
ALLOWED_AUDIO_TYPES = {"audio/mpeg", "audio/wav", "audio/ogg", "audio/webm", "audio/mp4"}
ALLOWED_TYPES = ALLOWED_IMAGE_TYPES | ALLOWED_AUDIO_TYPES

# Max file sizes (bytes)
MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB
MAX_AUDIO_SIZE = 10 * 1024 * 1024  # 10MB

# Upload directory
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR = UPLOAD_DIR.resolve()

def get_file_type(mime_type: str) -> str:
    """Determine file type from MIME type"""
    if mime_type in ALLOWED_IMAGE_TYPES:
        return "image"
    elif mime_type in ALLOWED_AUDIO_TYPES:
        return "audio"
    else:
        return "unknown"

def validate_file(file: UploadFile) -> tuple[str, int]:
    """Validate uploaded file and return type and max size"""
    if not file.content_type or file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {file.content_type}")
    
    file_type = get_file_type(file.content_type)
    max_size = MAX_IMAGE_SIZE if file_type == "image" else MAX_AUDIO_SIZE
    
    return file_type, max_size

async def save_file(file: UploadFile, conversation_id: str) -> tuple[str, int, str]:
    """Save uploaded file and return (file_path, file_size, file_type)"""
    file_type, max_size = validate_file(file)
    
    # Generate unique filename
    file_ext = Path(file.filename).suffix if file.filename else ""
    unique_filename = f"{uuid.uuid4()}{file_ext}"
    
    # Create conversation subdirectory
    conv_dir = (UPLOAD_DIR / conversation_id).resolve()
    conv_dir.mkdir(parents=True, exist_ok=True)
    
    file_path = conv_dir / unique_filename
    file_size = 0
    
    # Save file with size check
    async with aiofiles.open(file_path, 'wb') as f:
        while chunk := await file.read(8192):  # 8KB chunks
            file_size += len(chunk)
            if file_size > max_size:
                # Remove partial file
                try:
                    os.unlink(file_path)
                except:
                    pass
                raise HTTPException(status_code=413, detail=f"File too large. Max size: {max_size//1024//1024}MB")
            await f.write(chunk)
    
    # Return path relative to uploads directory for database storage
    relative_path = file_path.relative_to(UPLOAD_DIR).as_posix()
    return relative_path, file_size, file_type

def delete_file(file_path: str) -> bool:
    """Delete file from filesystem"""
    try:
        if not file_path:
            return False
        candidate = Path(file_path)
        if not candidate.is_absolute():
            candidate_str = str(candidate).lstrip("/\\")
            if candidate_str.startswith("uploads/"):
                candidate_str = candidate_str[len("uploads/"):]
            candidate = (UPLOAD_DIR / candidate_str).resolve()
        candidate.relative_to(UPLOAD_DIR)  # ensure within uploads
        if candidate.exists():
            os.unlink(candidate)
            return True
    except Exception:
        pass
    return False

def get_file_url(file_path: str) -> str:
    """Generate file URL for serving"""
    if not file_path:
        return ""
    # Normalize path separators and ensure proper format
    normalized = file_path.replace(os.sep, '/').replace('\\', '/')
    # Remove leading slashes and uploads prefix if present
    normalized = normalized.lstrip('/')
    if normalized.startswith("uploads/"):
        normalized = normalized[len("uploads/"):]
    return f"/files/{normalized}"
