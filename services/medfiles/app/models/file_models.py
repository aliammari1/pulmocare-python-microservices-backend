from fastapi import UploadFile
from pydantic import BaseModel, Field


class FileMetadata(BaseModel):
    """Metadata for a file"""

    patient_id: str | None = None
    doctor_id: str | None = None
    study_id: str | None = None
    modality: str | None = None
    description: str | None = None
    tags: list[str] | None = Field(default_factory=list)
    custom_data: dict | None = Field(default_factory=dict)


class FileInfo(BaseModel):
    """Basic file information"""

    bucket: str
    object_name: str
    filename: str | None = None
    content_type: str | None = None
    size: int
    last_modified: str
    download_url: str | None = None
    metadata: dict | None = None


class FileResponse(BaseModel):
    """Response model for file operations"""

    bucket: str
    object_name: str
    filename: str
    content_type: str
    size: int
    url: str
    metadata: dict = Field(default_factory=dict)
    created_at: str | None = None
    download_url: str | None = None  # Add this field


class FileListResponse(BaseModel):
    """Response model for listing files"""

    files: list[FileInfo]
    folders: list[dict[str, str]]
    total_files: int
    total_folders: int
    marker: str | None = None
    bucket: str
    prefix: str | None = None


class FileRequest(BaseModel):
    """Request model for file operations"""

    file: UploadFile = (None,)
    bucket: str = ("",)
    folder: str | None = (None,)
    metadata: dict | None = (None,)
