from typing import Any

from pydantic import BaseModel, Field


class FileMetadataResponse(BaseModel):
    id: str
    filename: str
    feature_count: int = Field(..., ge=0)
    crs: str
    status: str


class FeatureMeasurement(BaseModel):
    feature_id: str | int
    feature_index: int
    geometry_type: str
    crs: str
    geometry: dict[str, Any] | None = None
    properties: dict[str, Any]
    area: float | None = None
    length: float | None = None
    unsupported_reason: str | None = None
