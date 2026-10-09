from __future__ import annotations

import io
import os
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any

import geopandas as gpd
from pyproj import CRS
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Point, Polygon


SUPPORTED_EXTENSIONS = {".kml", ".kmz", ".zip"}
KML_NS = {"k": "http://www.opengis.net/kml/2.2"}


def read_geospatial_file(filename: str, file_bytes: bytes) -> tuple[gpd.GeoDataFrame, str]:
    suffix = Path(filename).suffix.lower()

    if suffix == ".zip":
        return _read_shapefile_zip(file_bytes)
    if suffix in {".kml", ".kmz"}:
        return _read_kml(file_bytes)

    raise ValueError(f"Unsupported file type: {filename}. Supported formats are .zip (Shapefile), .kml, and .kmz.")


def _read_shapefile_zip(file_bytes: bytes) -> tuple[gpd.GeoDataFrame, str]:
    with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
        shp_files = sorted(name for name in archive.namelist() if name.lower().endswith(".shp"))
        if not shp_files:
            raise ValueError("The uploaded .zip archive does not contain a shapefile (.shp).")

        target_shp = shp_files[0]
        with tempfile.TemporaryDirectory() as temp_dir:
            archive.extractall(temp_dir)
            shp_path = os.path.join(temp_dir, target_shp)
            gdf = gpd.read_file(shp_path)
            crs_name = _normalize_crs(gdf)
            return gdf, crs_name


def _read_kml(file_bytes: bytes) -> tuple[gpd.GeoDataFrame, str]:
    if file_bytes.startswith(b"PK"):
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
            kml_files = sorted(name for name in archive.namelist() if name.lower().endswith(".kml"))
            if not kml_files:
                raise ValueError("The uploaded .kmz archive does not contain a KML file.")
            file_bytes = archive.read(kml_files[0])

    root = ET.fromstring(file_bytes)
    features: list[dict[str, Any]] = []
    for placemark in root.findall(".//k:Placemark", KML_NS):
        properties = {
            "name": _tag_text(placemark, "k:name"),
            "description": _tag_text(placemark, "k:description"),
        }

        geometry = _extract_placemark_geometry(placemark)
        if geometry is None:
            continue

        features.append({"geometry": geometry, **properties})

    if not features:
        raise ValueError("The KML file does not contain any supported geometries.")

    gdf = gpd.GeoDataFrame(features, geometry="geometry", crs="EPSG:4326")
    return gdf, "EPSG:4326"


def _tag_text(parent: ET.Element, tag_name: str) -> str:
    child = parent.find(tag_name, KML_NS)
    return child.text.strip() if child is not None and child.text else ""


def _extract_placemark_geometry(placemark: ET.Element) -> Any | None:
    for element_name in ("Polygon", "LineString", "Point", "MultiGeometry"):
        element = placemark.find(f"k:{element_name}", KML_NS)
        if element is None:
            continue
        if element_name == "Polygon":
            return _parse_polygon(element)
        if element_name == "LineString":
            return _parse_linestring(element)
        if element_name == "Point":
            return _parse_point(element)
        if element_name == "MultiGeometry":
            geometries = []
            for child in element:
                geometry = _extract_geometry_from_node(child)
                if geometry is not None:
                    geometries.append(geometry)
            if not geometries:
                return None
            if len(geometries) == 1:
                return geometries[0]
            return MultiLineString([geom.coords[:] for geom in geometries if hasattr(geom, "coords")]) or MultiPolygon([geom for geom in geometries if isinstance(geom, Polygon)])

    for element_name in ("Polygon", "LineString", "Point"):
        geometry = _extract_geometry_from_node(placemark.find(f"k:{element_name}", KML_NS))
        if geometry is not None:
            return geometry

    return None


def _extract_geometry_from_node(node: ET.Element | None) -> Any | None:
    if node is None:
        return None

    if node.tag.endswith("Polygon"):
        return _parse_polygon(node)
    if node.tag.endswith("LineString"):
        return _parse_linestring(node)
    if node.tag.endswith("Point"):
        return _parse_point(node)
    if node.tag.endswith("MultiGeometry"):
        geometries = []
        for child in node:
            geometry = _extract_geometry_from_node(child)
            if geometry is not None:
                geometries.append(geometry)
        if not geometries:
            return None
        if len(geometries) == 1:
            return geometries[0]
        if all(isinstance(shape, Polygon) for shape in geometries):
            return MultiPolygon(geometries)
        if all(hasattr(shape, "coords") for shape in geometries):
            return MultiLineString([list(geom.coords) for geom in geometries])
    return None


def _parse_polygon(node: ET.Element) -> Polygon | None:
    ring = node.find("k:outerBoundaryIs/k:LinearRing/k:coordinates", KML_NS)
    if ring is None:
        return None
    return Polygon(_coordinates_from_text(ring.text))


def _parse_linestring(node: ET.Element) -> LineString | None:
    coordinates = node.find("k:coordinates", KML_NS)
    if coordinates is None or not coordinates.text:
        return None
    return LineString(_coordinates_from_text(coordinates.text))


def _parse_point(node: ET.Element) -> Point | None:
    coordinates = node.find("k:coordinates", KML_NS)
    if coordinates is None or not coordinates.text:
        return None
    points = _coordinates_from_text(coordinates.text)
    if not points:
        return None
    return Point(points[0])


def _coordinates_from_text(raw_text: str | None) -> list[tuple[float, float]]:
    if not raw_text:
        return []
    coords: list[tuple[float, float]] = []
    for token in raw_text.replace("\n", " ").split():
        cleaned = token.strip()
        if not cleaned:
            continue
        values = cleaned.split(",")
        if len(values) < 2:
            continue
        x = float(values[0])
        y = float(values[1])
        coords.append((x, y))
    return coords


def _normalize_crs(gdf: gpd.GeoDataFrame) -> str:
    crs = gdf.crs
    if crs is None:
        return "EPSG:4326"
    normalized = CRS.from_user_input(crs)
    return normalized.to_string()


def build_measurements(gdf: gpd.GeoDataFrame) -> list[dict[str, Any]]:
    projected = _project_for_measurement(gdf)
    projected_crs = _normalize_crs(projected)

    measurements: list[dict[str, Any]] = []
    for index, row in projected.iterrows():
        geom = row.geometry
        measurement = {
            "feature_id": row.get("id", index),
            "feature_index": index,
            "geometry_type": geom.geom_type if geom is not None and not geom.is_empty else "Unknown",
            "geometry": geom.__geo_interface__ if geom is not None and not geom.is_empty else None,
            "crs": projected_crs,
            "properties": row.drop(labels=["geometry"]).to_dict() if "geometry" in row.index else {},
            "area": None,
            "length": None,
            "unsupported_reason": None,
        }

        if geom is None or geom.is_empty:
            measurement["unsupported_reason"] = "Empty geometry"
            measurements.append(measurement)
            continue

        if geom.geom_type in {"Polygon", "MultiPolygon"}:
            measurement["area"] = round(float(geom.area), 6)
        elif geom.geom_type in {"LineString", "MultiLineString"}:
            measurement["length"] = round(float(geom.length), 6)
        elif geom.geom_type == "Point":
            measurement["unsupported_reason"] = "Point geometries do not require a measurement."
        else:
            measurement["unsupported_reason"] = f"Unsupported geometry type: {geom.geom_type}"

        measurements.append(measurement)

    return measurements


def _project_for_measurement(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if gdf.crs is None:
        return gdf.set_crs("EPSG:4326", allow_override=True)

    crs = CRS.from_user_input(gdf.crs)
    if crs.is_geographic:
        return gdf.to_crs("EPSG:3857")
    return gdf
