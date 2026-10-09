from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.schemas import FeatureMeasurement, FileMetadataResponse
from app.services.geospatial import build_measurements, read_geospatial_file

app = FastAPI(
    title="Geospatial File Measurement API",
    description="Upload geospatial files and return measurements for supported geometries.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FILE_STORE: dict[str, dict[str, Any]] = {}


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Geospatial File Measurement API is running."}


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/files/", response_model=FileMetadataResponse)
async def upload_file(file: UploadFile = File(...)) -> FileMetadataResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="A file is required.")

    filename = file.filename.lower()
    if not (filename.endswith(".zip") or filename.endswith(".kml") or filename.endswith(".kmz")):
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Please upload a .zip shapefile archive, .kml, or .kmz file.",
        )

    contents = await file.read()
    try:
        gdf, crs_name = read_geospatial_file(file.filename, contents)
    except Exception as exc:  # pragma: no cover - only used for user-facing validation
        raise HTTPException(status_code=400, detail=f"Unable to process geospatial file: {exc}") from exc

    measurements = build_measurements(gdf)
    file_id = str(uuid4())
    record = {
        "id": file_id,
        "filename": file.filename,
        "feature_count": len(gdf),
        "crs": crs_name,
        "status": "COMPLETED",
        "measurements": measurements,
    }
    FILE_STORE[file_id] = record

    return FileMetadataResponse(**{k: v for k, v in record.items() if k in {"id", "filename", "feature_count", "crs", "status"}})


@app.get("/api/files/{file_id}/", response_model=FileMetadataResponse)
async def get_file(file_id: str) -> FileMetadataResponse:
    record = FILE_STORE.get(file_id)
    if not record:
        raise HTTPException(status_code=404, detail="File not found.")

    return FileMetadataResponse(
        id=record["id"],
        filename=record["filename"],
        feature_count=record["feature_count"],
        crs=record["crs"],
        status=record["status"],
    )


@app.get("/api/files/{file_id}/measurements/", response_model=list[FeatureMeasurement])
async def get_measurements(file_id: str) -> list[FeatureMeasurement]:
    record = FILE_STORE.get(file_id)
    if not record:
        raise HTTPException(status_code=404, detail="File not found.")

    measurements = record["measurements"]
    return [FeatureMeasurement(**item) for item in measurements]
