"""Local HTTP API for the SiteIQ interface. Binds to localhost through ``run_siteiq``."""
from __future__ import annotations

import hashlib
import io
import json
import logging
from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from . import __version__
from .boundary import candidate_edge_lengths, export_boundary_dxf, parse_uploaded_boundary, polygon_from_candidate
from .engine import find_authority, land_use_categories, load_authority_registry, load_rule_profile, rule_status_problem
from .exporters import build_a3_comparison_board_pdf, build_a3_comparison_board_pptx, build_pdf_report, build_pptx_report
from .location import auto_identify_site, save_geojson_layer
from .service import assess, far_preview, parcel_from_boundary

logger = logging.getLogger("siteiq.api")
ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "frontend" / "dist"
MAX_UPLOAD_BYTES = 40 * 1024 * 1024
MAX_VERTICES = 5000

app = FastAPI(title="SiteIQ", version=__version__, docs_url=None, redoc_url=None)


@app.exception_handler(RequestValidationError)
async def validation_error(_request, exc: RequestValidationError) -> JSONResponse:
    # Never echo submitted values: they may be non-finite numbers that cannot be serialised.
    problems = [f"{'.'.join(str(part) for part in e['loc'] if part != 'body') or 'request'}: {e['msg']}" for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": "; ".join(problems[:5])})


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class LocationRequest(Strict):
    address: str = Field("", max_length=500)
    map_url: str = Field("", max_length=2000)
    coordinates: str = Field("", max_length=100)
    site_area_m2: float = Field(0, ge=0)
    proposed_use: str = Field("", max_length=100)
    road_width_m: Optional[float] = Field(None, ge=0)
    boundary_point_lonlat: Optional[list[float]] = Field(None, min_length=2, max_length=2)


class ValidateRequest(Strict):
    candidate: dict[str, Any]
    scale_to_m: Optional[float] = Field(None, gt=0)
    close_open: bool = False


class PreviewRequest(Strict):
    authority_key: str = Field(max_length=100)
    land_use_category: Optional[str] = Field(None, max_length=200)
    site_area_m2: float = Field(gt=0)
    road_width_m: float = Field(gt=0)
    surrounding_zone: Optional[str] = Field(None, max_length=200)
    proposed_use: Optional[str] = Field(None, max_length=100)
    statutory_deduction_pct: Optional[float] = Field(None, ge=0, le=50)


class Scenario(Strict):
    name: str = Field(max_length=80)
    height_m: Optional[float] = Field(None, gt=0, le=500)
    floors: Optional[int] = Field(None, gt=0, le=200)
    footprint_m2: Optional[float] = Field(None, gt=0)
    stilt: bool = False
    stilt_height_m: Optional[float] = Field(None, gt=0, le=10)
    setback_mode: Literal["automatic", "manual"] = "automatic"
    manual_all_round_setback_m: Optional[float] = Field(None, gt=0, le=100)
    basement_levels: int = Field(0, ge=0, le=10)
    basement_setback_mode: Literal["automatic", "manual"] = "automatic"
    manual_basement_front_m: Optional[float] = Field(None, gt=0, le=100)
    manual_basement_nonfront_m: Optional[float] = Field(None, gt=0, le=100)


class Overlay(Strict):
    status: Literal["unknown", "absent", "present"] = "unknown"
    edge: Optional[int] = Field(None, ge=0)
    extra_setback_m: Optional[float] = Field(None, gt=0, le=500)
    drain_class: Optional[Literal["primary", "secondary", "tertiary"]] = None


class RoadEdge(Strict):
    edge: int = Field(ge=0)
    width_m: float = Field(gt=0, le=300)


class Boundary(Strict):
    source_file: str = Field("", max_length=300)
    source_type: str = Field("", max_length=20)
    source_units: Optional[str] = Field(None, max_length=200)
    scale_to_m: Optional[float] = None
    source_fingerprint: Optional[str] = Field(None, max_length=128)
    candidate_id: Optional[str] = Field(None, max_length=40)
    points_m: list[list[float]] = Field(min_length=3, max_length=MAX_VERTICES)
    holes_m: list[list[list[float]]] = Field(default_factory=list, max_length=100)
    area_m2: float = Field(gt=0)
    perimeter_m: float = Field(gt=0)
    vertex_count: int = Field(ge=3)
    is_convex: bool = False
    validation_status: str = Field("valid", max_length=40)
    validation_notes: list[str] = Field(default_factory=list)
    use_computed_area: bool = True
    front_edges: list[int] = Field(default_factory=list)
    rear_edges: list[int] = Field(default_factory=list)
    source_points_wgs84: Optional[list[list[float]]] = None
    source_holes_wgs84: Optional[list[list[list[float]]]] = None


class AssessRequest(Strict):
    project_name: str = Field("Untitled site", max_length=200)
    client: str = Field("", max_length=200)
    address: str = Field("", max_length=500)
    map_url: str = Field("", max_length=2000)
    coordinates: str = Field("", max_length=100)
    authority_key: str = Field(max_length=100)
    authority_confirmed: bool = False
    land_use_category: str = Field(max_length=200)
    zone_confirmed: bool = False
    surrounding_zone: Optional[str] = Field(None, max_length=200)
    proposed_use: str = Field(max_length=100)
    site_area_m2: float = Field(gt=0)
    site_area_source: str = Field("user-entered survey/title area", max_length=100)
    area_stated_m2: Optional[float] = Field(None, gt=0)
    road_width_m: float = Field(gt=0, le=300)
    road_width_source: Literal["unknown", "notified", "survey", "measured"] = "unknown"
    road_edges: list[RoadEdge] = Field(default_factory=list)
    statutory_deduction_pct: Optional[float] = Field(None, ge=0, le=50)
    frontage_m: Optional[float] = Field(None, gt=0)
    depth_m: Optional[float] = Field(None, gt=0)
    approval_path: str = Field("Not sure / needs confirmation", max_length=200)
    rmp_ring: Optional[Literal["I", "II", "III", "unknown"]] = None
    dwelling_units: Optional[int] = Field(None, gt=0, le=100000)
    average_unit_area_m2: Optional[float] = Field(None, gt=0)
    land_status: Literal["unknown", "converted", "not_converted"] = "unknown"
    prior_sanction: Literal["unknown", "none", "exists"] = "unknown"
    overlays: dict[str, Overlay] = Field(default_factory=dict)
    scenarios: list[Scenario] = Field(min_length=1, max_length=6)
    boundary: Optional[Boundary] = None
    location: Optional[dict[str, Any]] = None


def _run_assessment(body: AssessRequest) -> dict:
    payload = body.model_dump()
    try:
        return assess(payload)
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=f"Unknown value: {exc}") from exc


@app.get("/api/meta")
def meta() -> dict:
    registry = load_authority_registry()
    rows = []
    for a in registry.get("authorities", []):
        profile = load_rule_profile(a["rule_profile"]) if a.get("rule_profile") else None
        rows.append({"key": a["key"], "name": a["name"], "status": a.get("status"), "group": a.get("coverage_group"), "has_rules": bool(profile), "source_status": (profile or {}).get("source_status", "not_configured"), "scope_note": a.get("scope_note")})
    return {"version": __version__, "authorities": rows}


@app.get("/api/authorities/{key}")
def authority_detail(key: str) -> dict:
    registry = load_authority_registry()
    try:
        authority = find_authority(registry, key)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown authority.") from exc
    profile = load_rule_profile(authority["rule_profile"]) if authority.get("rule_profile") else None
    return {
        "key": key, "name": authority["name"], "scope_note": authority.get("scope_note"),
        "has_rules": bool(profile),
        "profile_name": (profile or {}).get("profile_name"), "profile_status": (profile or {}).get("profile_status"),
        "source_status": (profile or {}).get("source_status", "not_configured"),
        "status_problem": rule_status_problem(profile) if profile else None,
        "has_apartment_rings": bool((profile or {}).get("apartment_rules")),
        "categories": [{"key": c.get("key"), "label": c.get("label"), "table": c.get("table"), "method": c.get("method")} for c in land_use_categories(profile)],
        "sources": (profile or {}).get("sources", []),
    }


@app.post("/api/location/identify")
def identify(body: LocationRequest) -> dict:
    coordinates, map_url = body.coordinates, body.map_url
    if body.boundary_point_lonlat:
        coordinates = f"{body.boundary_point_lonlat[1]:.7f}, {body.boundary_point_lonlat[0]:.7f}"
        map_url = ""
    try:
        result = auto_identify_site(address=body.address, map_url=map_url, coordinates_text=coordinates, site_area_m2=body.site_area_m2, proposed_use=body.proposed_use, road_width_m=body.road_width_m)
    except (RuntimeError, ValueError) as exc:
        # Failing closed: the client clears any previous location and authority result.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if body.boundary_point_lonlat:
        result["location_source"] = "Imported boundary"
    return result


async def _read_upload(file: UploadFile) -> bytes:
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="This file is larger than the 40 MB limit.")
    return data


@app.post("/api/boundary/parse")
async def parse_boundary(file: UploadFile = File(...)) -> dict:
    data = await _read_upload(file)
    name = Path(file.filename or "upload").name
    try:
        candidates, file_meta = parse_uploaded_boundary(name, data)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"filename": name, "fingerprint": hashlib.sha256(data).hexdigest(), "candidates": candidates, "meta": file_meta}


@app.post("/api/boundary/validate")
def validate_boundary(body: ValidateRequest) -> dict:
    if len(body.candidate.get("points", [])) > MAX_VERTICES:
        raise HTTPException(status_code=422, detail=f"Boundaries are limited to {MAX_VERTICES} vertices.")
    try:
        poly, validation = polygon_from_candidate(body.candidate, scale_to_m=body.scale_to_m, close_open=body.close_open)
    except (TypeError, ValueError, IndexError) as exc:
        raise HTTPException(status_code=422, detail="This boundary candidate could not be read.") from exc
    if poly is None:
        return {"valid": False, "validation": validation}
    coords = [list(p) for p in list(poly.exterior.coords)[:-1]]
    return {"valid": True, "validation": validation, "points_m": coords, "holes_m": [[list(p) for p in list(r.coords)[:-1]] for r in poly.interiors], "edges": candidate_edge_lengths(coords)}


@app.post("/api/far/preview")
def preview(body: PreviewRequest) -> dict:
    try:
        return far_preview(body.authority_key, body.land_use_category, body.site_area_m2, body.road_width_m, surrounding_zone=body.surrounding_zone, proposed_use=body.proposed_use, statutory_deduction_pct=body.statutory_deduction_pct)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown authority.") from exc


@app.post("/api/assess")
def run_assess(body: AssessRequest) -> dict:
    return _run_assessment(body)


EXPORTS = {
    "report-pdf": ("application/pdf", "Feasibility_Report.pdf"),
    "report-pptx": ("application/vnd.openxmlformats-officedocument.presentationml.presentation", "Feasibility_Report.pptx"),
    "board-pdf": ("application/pdf", "Comparison_Board_A3.pdf"),
    "board-pptx": ("application/vnd.openxmlformats-officedocument.presentationml.presentation", "Comparison_Board_A3.pptx"),
    "assessment-json": ("application/json", "Assessment.json"),
    "envelopes-dxf": ("application/dxf", "Envelopes.dxf"),
}


@app.post("/api/export/{kind}")
def export(kind: str, body: AssessRequest) -> Response:
    """Recalculate from the inputs, so a download can never be older than what is on screen."""
    if kind not in EXPORTS:
        raise HTTPException(status_code=404, detail="Unknown export type.")
    report = _run_assessment(body)
    if kind == "report-pdf":
        data = build_pdf_report(report)
    elif kind == "report-pptx":
        data = build_pptx_report(report)
    elif kind == "board-pdf":
        data = build_a3_comparison_board_pdf(report)
    elif kind == "board-pptx":
        data = build_a3_comparison_board_pptx(report)
    elif kind == "assessment-json":
        data = json.dumps(report, indent=2, ensure_ascii=False).encode("utf-8")
    else:
        boundary = report.get("boundary_analysis")
        if not boundary:
            raise HTTPException(status_code=422, detail="Apply a boundary before exporting envelopes.")
        layers: dict[str, dict] = {}
        for item in boundary["options"]:
            layers[item["name"]] = item.get("envelope") or {}
            if (item.get("basement_envelope") or {}).get("geometry"):
                layers[item["name"] + " basement"] = item["basement_envelope"]
        parcel = parcel_from_boundary(body.boundary.model_dump())
        data = export_boundary_dxf(parcel, layers)
    media, name = EXPORTS[kind]
    return Response(content=data, media_type=media, headers={"Content-Disposition": f'attachment; filename="SiteIQ_{name}"', "X-SiteIQ-Fingerprint": report["input_fingerprint"]})


@app.post("/api/admin/layers/{layer}")
async def install_layer(layer: Literal["authority", "zone"], file: UploadFile = File(...)) -> dict:
    data = await _read_upload(file)
    name = "authority_boundaries.geojson" if layer == "authority" else "land_use_zones.geojson"
    try:
        return save_geojson_layer(name, data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(status_code=404)
        candidate = (DIST / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(DIST.resolve()):
            return FileResponse(candidate)
        return FileResponse(DIST / "index.html")
