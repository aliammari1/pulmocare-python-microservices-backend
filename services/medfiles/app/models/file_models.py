from typing import Dict, List, Optional

from fastapi import UploadFile
from pydantic import BaseModel, Field


class FileMetadata(BaseModel):
    """Metadata for a file"""

    patient_id: Optional[str] = None
    doctor_id: Optional[str] = None
    study_id: Optional[str] = None
    modality: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = Field(default_factory=list)
    custom_data: Optional[Dict] = Field(default_factory=dict)


class FileInfo(BaseModel):
    """Basic file information"""

    bucket: str
    object_name: str
    filename: Optional[str] = None
    content_type: Optional[str] = None
    size: int
    last_modified: str
    download_url: Optional[str] = None
    metadata: Optional[Dict] = None


class FileResponse(BaseModel):
    """Response model for file operations"""

    bucket: str
    object_name: str
    filename: str
    content_type: str
    size: int
    url: str
    metadata: Dict = Field(default_factory=dict)
    created_at: Optional[str] = None
    download_url: Optional[str] = None  # Add this field


class FileListResponse(BaseModel):
    """Response model for listing files"""

    files: List[FileInfo]
    folders: List[Dict[str, str]]
    total_files: int
    total_folders: int
    marker: Optional[str] = None
    bucket: str
    prefix: Optional[str] = None


class FileRequest(BaseModel):
    """Request model for file operations"""

    file: UploadFile = (None,)
    bucket: str = ("",)
    folder: Optional[str] = (None,)
    metadata: Optional[dict] = (None,)
