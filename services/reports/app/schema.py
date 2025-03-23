from pydantic import BaseModel, Field, validator
from typing import List, Optional
from datetime import datetime
from enum import Enum

class Severity(str, Enum):
    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"

class AnnotationType(str, Enum):
    DRAWING = "drawing"
    TEXT = "text"

class Point(BaseModel):
    x: float = Field(..., description="X coordinate")
    y: float = Field(..., description="Y coordinate")
    color: int = Field(..., description="Color in ARGB format")
    strokeWidth: float = Field(..., description="Width of the stroke")

class Annotation(BaseModel):
    type: AnnotationType
    points: Optional[List[Point]] = None
    text: Optional[str] = None
    timestamp: datetime

    @validator('points')
    def points_required_for_drawing(cls, v, values):
        if values.get('type') == AnnotationType.DRAWING and not v:
            raise ValueError('Points are required for drawing annotations')
        return v

    @validator('text')
    def text_required_for_text_type(cls, v, values):
        if values.get('type') == AnnotationType.TEXT and not v:
            raise ValueError('Text is required for text annotations')
        return v

class Finding(BaseModel):
    condition: str = Field(..., description="Medical condition identified")
    severity: Severity
    description: str = Field(..., description="Detailed description of the finding")
    confidence_score: float = Field(..., ge=0, le=100, description="Confidence score (0-100)")
    probability: float = Field(..., ge=0, le=1, description="Probability (0-1)")

class ImageQualityMetrics(BaseModel):
    contrast: str = Field(..., description="Image contrast quality")
    sharpness: str = Field(..., description="Image sharpness quality")
    exposure: str = Field(..., description="Image exposure quality")
    positioning: str = Field(..., description="Patient positioning quality")
    noise_level: str = Field(..., description="Image noise level")

class TechnicalDetails(BaseModel):
    quality_metrics: ImageQualityMetrics
    image_stats: dict = Field(..., description="Raw image statistics")

class Analysis(BaseModel):
    findings: List[Finding]
    technical_details: TechnicalDetails

class Report(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)
    patient_id: str = Field(..., description="ID of the patient")
    doctor_id: str = Field(..., description="ID of the doctor")
    analysis: Optional[Analysis] = None
    annotations: Optional[List[Annotation]] = None
    tags: Optional[List[str]] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        
    @validator('updated_at')
    def updated_at_must_be_after_created(cls, v, values):
        if 'created_at' in values and v < values['created_at']:
            raise ValueError('updated_at must be after created_at')
        return v