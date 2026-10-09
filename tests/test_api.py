from io import BytesIO

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _kml_bytes():
    return b"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<kml xmlns=\"http://www.opengis.net/kml/2.2\">
  <Document>
    <Placemark>
      <name>Square</name>
      <Polygon>
        <outerBoundaryIs>
          <LinearRing>
            <coordinates>
              0,0,0 0,1,0 1,1,0 1,0,0 0,0,0
            </coordinates>
          </LinearRing>
        </outerBoundaryIs>
      </Polygon>
    </Placemark>
    <Placemark>
      <name>Line</name>
      <LineString>
        <coordinates>
          0,0,0 0,2,0
        </coordinates>
      </LineString>
    </Placemark>
  </Document>
</kml>
"""


def test_upload_and_measure_kml():
    response = client.post(
        "/api/files/",
        files={"file": ("sample.kml", _kml_bytes(), "application/vnd.google-earth.kml+xml")},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["filename"] == "sample.kml"
    assert payload["status"] == "COMPLETED"
    assert payload["feature_count"] >= 2
    file_id = payload["id"]

    info_response = client.get(f"/api/files/{file_id}/")
    assert info_response.status_code == 200
    info = info_response.json()
    assert info["filename"] == "sample.kml"

    metrics_response = client.get(f"/api/files/{file_id}/measurements/")
    assert metrics_response.status_code == 200
    metrics = metrics_response.json()
    assert len(metrics) >= 2
    assert any(item["geometry_type"] == "Polygon" for item in metrics)
    assert any(item["geometry_type"] == "LineString" for item in metrics)
    assert any(item["area"] is not None or item["length"] is not None for item in metrics)


def test_upload_rejects_invalid_extension():
    response = client.post(
        "/api/files/",
        files={"file": ("bad.txt", b"not a geospatial file", "text/plain")},
    )

    assert response.status_code == 400
    assert "Unsupported" in response.json()["detail"]
