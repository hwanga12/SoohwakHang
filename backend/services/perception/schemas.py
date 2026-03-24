from __future__ import annotations

from pydantic import BaseModel, Field


class BoundingBox(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float


class ThinInferenceConfirmRequest(BaseModel):
    observation_id: str | None = None
    robot_id: str = ''
    zone_id: str = ''
    plant_id: str = ''
    fruit_id: str = ''
    frame_id: str = ''
    preliminary_label: str = ''
    preliminary_confidence: float = Field(default=0.0, ge=0.0)
    image_base64: str
    image_format: str = 'jpg'
    bbox: BoundingBox | None = None


class ThinInferenceConfirmResponse(BaseModel):
    observation_id: str
    preliminary_label: str
    preliminary_confidence: float
    final_label: str
    final_confidence: float
    image_path: str
    reviewed_at: str
    decision_source: str
