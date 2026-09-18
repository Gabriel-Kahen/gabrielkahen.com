from dataclasses import replace
import asyncio
import json
import math
from pathlib import Path
import sqlite3
import subprocess
import sys
from uuid import uuid4
from types import SimpleNamespace

from fastapi.testclient import TestClient
from fastapi import HTTPException
import pytest

from app import MAX_BODY_BYTES, Settings, create_app
from drawing import InvalidDrawing, PrinterConfig, generate_gcode, validate_drawing


def payload(strokes=None, version=2):
    return {"version": version, "submission_id": str(uuid4()), "strokes": [[[0, 0], [3, 4]]] if strokes is None else strokes}


@pytest.fixture
def settings(tmp_path):
    return Settings(db_path=str(tmp_path / "drawings.sqlite3"))


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def test_trace_order_y_flip_scale_and_safe_lifts():
    config = PrinterConfig()
    strokes = [[[0, 0], [12, 30], [3, 50]], [[215, 175]]]
    output = generate_gcode(strokes, config)
    lines = output.splitlines()
    moves = [line for line in lines if line.startswith(("G0 X", "G1 X"))]
    for line, point in zip(moves, [p for stroke in strokes for p in stroke], strict=True):
        coordinates = {part[0]: float(part[1:]) for part in line.split()[1:]}
        x, y = config.transform(point)
        assert coordinates["X"] == pytest.approx(x, abs=0.000051)
        assert coordinates["Y"] == pytest.approx(y, abs=0.000051)
    assert config.transform([0, 0]) == pytest.approx((10, 191.3953488372))
    assert config.transform([215, 175]) == pytest.approx((210, 28.6046511628))
    assert output.count("G1 Z0.0000") == 2
    assert output.count("G0 Z3.0000") == 3
    assert "G4 P100" in output
    for i, line in enumerate(lines):
        if line.startswith("G0 X"):
            previous_move = next(x for x in reversed(lines[:i]) if not x.startswith(";"))
            assert previous_move.startswith("G0 Z3.0000")
        if line.startswith("G1 X"):
            assert " Z" not in line and " E" not in line
    commands = [line.split()[0] for line in lines if not line.startswith(";")]
    assert "G28" not in commands and "G92" not in commands and "M84" not in commands
    assert "M420 S0" in lines and "M104 S0" in lines and "M140 S0" in lines


def test_length_excludes_pen_up_travel_and_accepts_dots():
    _, _, length, _ = validate_drawing(payload([[[0, 0], [3, 4]], [[200, 200]]]))
    assert length == 5
    assert validate_drawing(payload([[[1, 2]]]))[2] == 0


def test_exact_limit():
    strokes = [[[0, 0], [200, 0], [0, 0], [200, 0], [0, 0], [200, 0], [0, 0], [19.2, 0]]]
    assert validate_drawing(payload(strokes))[2] == 1219.2
    strokes[0][-1][0] += 0.0001
    with pytest.raises(InvalidDrawing):
        validate_drawing(payload(strokes))


@pytest.mark.parametrize("strokes", [[], [[]], [[[True, 0]]], [[["0", 0]]], [[[math.nan, 0]]], [[[math.inf, 0]]], [[[-1, 0]]], [[[216, 0]]], [[[0, 280]]], [[[1, 2, 3]]], [[[0, 0]]] * 201, [[[0, 0]] * 20001]])
def test_reject_invalid_geometry(strokes):
    with pytest.raises(InvalidDrawing):
        validate_drawing(payload(strokes))


@pytest.mark.parametrize("change", [{"version": True}, {"version": 1.0}, {"version": 4}, {"submission_id": "bad"}, {"gcode": "anything"}])
def test_reject_invalid_schema(change):
    with pytest.raises(InvalidDrawing):
        validate_drawing(payload() | change)


@pytest.mark.parametrize("changes", [{"contact_z_mm": 3}, {"lifted_z_mm": -1}, {"margin_mm": 110}, {"drawing_feed_mm_min": 10000}, {"bed_width_mm": math.nan}, {"dot_dwell_ms": 1.5}])
def test_reject_unsafe_config(changes):
    with pytest.raises(ValueError):
        PrinterConfig(**changes)


def test_small_bed_is_uniformly_fitted():
    config = PrinterConfig(bed_width_mm=100, bed_height_mm=100)
    assert config.scale == pytest.approx(80 / 215)
    for point in ([0, 0], [215, 175]):
        assert all(10 <= coordinate <= 90 for coordinate in config.transform(point))


def test_calibrated_rectangle_version_validation_and_mapping():
    strokes = [[[0, 0], [215, 0], [215, 175], [0, 175], [0, 0]]]
    _, clean, length, canonical = validate_drawing(payload(strokes, version=3))
    assert length == 780
    assert json.loads(canonical)["version"] == 3
    config = PrinterConfig()
    output = generate_gcode(clean, config, version=3)
    assert "215 x 175 mm calibrated area" in output
    for point in ([215.001, 0], [0, 175.001]):
        with pytest.raises(InvalidDrawing):
            validate_drawing(payload([[point]], version=3))


def test_atomic_storage_idempotency_conflict_and_private_api(client, settings):
    data = payload()
    response = client.post("/draw-api/drawings", json=data)
    assert response.status_code == 201
    receipt = response.json()
    assert receipt["id"] == data["submission_id"]
    assert receipt["length_mm"] == 5
    assert receipt["status"] == "pending_calibration"
    retry = client.post("/drawings", json=data)
    assert retry.status_code == 200 and retry.json() == receipt
    conflict = client.post("/drawings", json=data | {"strokes": [[[1, 2]]]})
    assert conflict.status_code == 409 and "error" in conflict.json()
    with sqlite3.connect(settings.db_path) as db:
        row = db.execute("SELECT * FROM drawings").fetchone()
        assert db.execute("SELECT COUNT(*) FROM drawings").fetchone()[0] == 1
    assert json.loads(row[2])["strokes"] == data["strokes"]
    assert "G1 X" in row[4] and json.loads(row[5])["contact_z_mm"] == 0
    assert client.get("/drawings").status_code == 405
    assert client.get("/drawings/" + receipt["id"]).status_code == 404
    assert client.get("/health").json() == client.get("/draw-api/health").json()


def test_cors(client):
    allowed = client.post("/drawings", json=payload(), headers={"Origin": "https://gabrielkahen.com"})
    assert allowed.headers["access-control-allow-origin"] == "https://gabrielkahen.com"
    denied = client.post("/drawings", json=payload(), headers={"Origin": "https://example.org"})
    assert denied.status_code == 403 and "access-control-allow-origin" not in denied.headers
    preflight = client.options("/drawings", headers={"Origin": "https://www.gabrielkahen.com", "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "Content-Type"})
    assert preflight.status_code == 200


def test_body_bounds_json_and_encoding(client):
    assert client.post("/drawings", content="{}", headers={"Content-Type": "text/plain"}).status_code == 415
    assert client.post("/drawings", json=payload(), headers={"Content-Encoding": "gzip"}).status_code == 415
    assert client.post("/drawings", content="{}", headers={"Content-Type": "application/json", "Content-Length": str(MAX_BODY_BYTES + 1)}).status_code == 413
    chunks = (b" " * (MAX_BODY_BYTES // 2) for _ in range(3))
    assert client.post("/drawings", content=chunks, headers={"Content-Type": "application/json"}).status_code == 413
    for invalid in ('{"version":1,"version":1}', "[" * 2000, "NaN", "{}"):
        assert client.post("/drawings", content=invalid, headers={"Content-Type": "application/json"}).status_code == 422


def test_capacity_keeps_existing_retry(settings):
    with TestClient(create_app(replace(settings, max_drawings=1))) as client:
        data = payload()
        assert client.post("/drawings", json=data).status_code == 201
        assert client.post("/drawings", json=payload()).status_code == 503
        assert client.post("/drawings", json=data).status_code == 200


def test_rate_limit(settings):
    with TestClient(create_app(replace(settings, requests_per_minute=1))) as client:
        assert client.post("/drawings", json=payload()).status_code == 201
        response = client.post("/drawings", json=payload())
        assert response.status_code == 429 and response.headers["Retry-After"] == "60"


def test_local_export(client, settings, tmp_path):
    data = payload()
    client.post("/drawings", json=data)
    output = tmp_path / "test.gcode"
    result = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / "export.py"), data["submission_id"], "--db", settings.db_path, "--output", str(output)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "PENDING CALIBRATION" in output.read_text()


def test_storage_byte_cap(settings):
    with TestClient(create_app(replace(settings, max_storage_bytes=1_048_576))) as client:
        # Stationary samples exercise byte limits without exceeding the ink limit.
        data = payload([[[1, 1]] * 20000])
        statuses = [client.post("/drawings", json=data | {"submission_id": str(uuid4())}).status_code for _ in range(3)]
        assert 503 in statuses
        assert Path(settings.db_path).stat().st_size <= 1_048_576


def test_stalled_body_deadline(settings, monkeypatch):
    monkeypatch.setattr("app.BODY_TIMEOUT_SECONDS", 0.01)
    app = create_app(settings)
    endpoint = next(route.endpoint for route in app.routes if route.path == "/drawings")

    async def stalled_stream():
        yield b"{"
        await asyncio.sleep(1)
        yield b"}"

    request = SimpleNamespace(headers={"content-type": "application/json"}, stream=stalled_stream)
    with pytest.raises(HTTPException) as error:
        asyncio.run(endpoint(request))
    assert error.value.status_code == 408


def test_square_boundary_validation_and_one_to_one_mapping():
    strokes = [[[0, 0], [200, 0], [200, 200], [0, 200], [0, 0]]]
    _, clean, length, canonical = validate_drawing(payload(strokes))
    assert length == 800
    assert json.loads(canonical)["version"] == 2
    config = PrinterConfig()
    assert config.scale_for(2) == 1
    output = generate_gcode(clean, config, version=2)
    for command in ("G0 X10.0000 Y210.0000", "G1 X210.0000 Y210.0000",
                    "G1 X210.0000 Y10.0000", "G1 X10.0000 Y10.0000"):
        assert command in output
    for point in ([200.001, 0], [0, 200.001]):
        with pytest.raises(InvalidDrawing):
            validate_drawing(payload([[point]]))


def test_letter_compatibility_preserves_mapping_and_retries(client, settings):
    strokes = [[[0, 0], [215.9, 279.4]]]
    data = payload(strokes, version=1)
    assert client.post("/drawings", json=data).status_code == 201
    with sqlite3.connect(settings.db_path) as db:
        original = db.execute("SELECT vector_json, gcode, printer_config_json FROM drawings").fetchone()
    assert json.loads(original[0])["version"] == 1
    assert "G0 X32.7273 Y210.0000" in original[1]
    assert "G1 X187.2727 Y10.0000" in original[1]
    assert client.post("/drawings", json=data).status_code == 200
    with sqlite3.connect(settings.db_path) as db:
        assert db.execute("SELECT vector_json, gcode, printer_config_json FROM drawings").fetchone() == original


def test_same_uuid_with_new_coordinate_version_conflicts(client):
    data = payload([[[1, 1]]], version=1)
    assert client.post("/drawings", json=data).status_code == 201
    assert client.post("/drawings", json=data | {"version": 2}).status_code == 409
