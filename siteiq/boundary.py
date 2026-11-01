"""SiteIQ boundary import, validation and preliminary setback-envelope tools.

Supported inputs:
- DXF: closed LWPOLYLINE/POLYLINE entities; common $INSUNITS converted to metres.
- KML/KMZ: Polygon outer rings and LineString paths, reprojected from WGS84 to local UTM.
- Vector PDF: closed, straight-line vector paths and rectangles. Raster/scanned PDF tracing is not yet automated.

Native DWG is not read directly in this version. Export from AutoCAD as DXF.
All geometry outputs are preliminary and must be reconciled with an authenticated survey.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any
import math
import re
import zipfile
import xml.etree.ElementTree as ET

from shapely.geometry import Polygon, LineString, MultiPolygon, GeometryCollection, mapping
from shapely.validation import explain_validity
from shapely.ops import transform as shapely_transform

UNIT_TO_M = {
    0: None,  # unitless
    1: 0.0254,           # inches
    2: 0.3048,           # feet
    3: 1609.344,         # miles
    4: 0.001,            # millimetres
    5: 0.01,             # centimetres
    6: 1.0,              # metres
    7: 1000.0,           # kilometres
    8: 0.0000000254,     # microinches
    9: 0.0000254,        # mils
    10: 0.9144,          # yards
    11: 1e-10,           # angstroms
    12: 1e-9,            # nanometres
    13: 1e-6,            # microns
    14: 0.1,             # decimetres
    15: 10.0,            # decametres
    16: 100.0,           # hectometres
    17: 1e9,             # gigametres
    18: 149597870700.0,  # astronomical units
    19: 9.460730472e15,  # light years
    20: 3.085677581491367e16,  # parsecs
}
UNIT_NAMES = {
    0: "unitless / unknown", 1: "inches", 2: "feet", 3: "miles", 4: "millimetres",
    5: "centimetres", 6: "metres", 7: "kilometres", 8: "microinches", 9: "mils",
    10: "yards", 11: "angstroms", 12: "nanometres", 13: "microns", 14: "decimetres",
    15: "decametres", 16: "hectometres", 17: "gigametres", 18: "astronomical units",
    19: "light years", 20: "parsecs",
}


@dataclass
class BoundaryCandidate:
    candidate_id: str
    label: str
    points: list[tuple[float, float]]
    source_type: str
    source_units: str
    scale_to_m: float | None
    closed: bool = True
    layer: str = ""
    page: int | None = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _point_tuple(p) -> tuple[float, float]:
    return (float(p[0]), float(p[1]))


def _dedupe_consecutive(points: list[tuple[float, float]], tol: float = 1e-8) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for p in points:
        if not out or math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) > tol:
            out.append(p)
    if len(out) > 1 and math.hypot(out[0][0] - out[-1][0], out[0][1] - out[-1][1]) <= tol:
        out.pop()
    return out


def _candidate(points, candidate_id, label, source_type, source_units, scale_to_m, closed=True, layer="", page=None, notes=""):
    pts = _dedupe_consecutive([_point_tuple(p) for p in points])
    if len(pts) < 3:
        return None
    return BoundaryCandidate(
        candidate_id=str(candidate_id), label=str(label), points=pts,
        source_type=source_type, source_units=source_units, scale_to_m=scale_to_m,
        closed=bool(closed), layer=str(layer or ""), page=page, notes=str(notes or "")
    )


def parse_dxf(data: bytes) -> tuple[list[dict], dict]:
    """Extract closed polylines from DXF; returns candidates and file metadata."""
    try:
        import ezdxf
        from ezdxf.path import make_path
    except ImportError as exc:
        raise RuntimeError("DXF import requires ezdxf. Install requirements.txt and restart SiteIQ.") from exc
    try:
        # DXF geometry and entity text is largely ASCII, but replacement avoids a hard failure on labels.
        doc = ezdxf.read(StringIO(data.decode("utf-8", errors="replace")))
    except Exception as exc:
        raise ValueError(f"SiteIQ could not read this DXF file: {exc}") from exc
    insunits = int(doc.header.get("$INSUNITS", 0) or 0)
    scale = UNIT_TO_M.get(insunits)
    unit_name = UNIT_NAMES.get(insunits, "unknown")
    modelspace = doc.modelspace()
    candidates: list[BoundaryCandidate] = []
    ignored_open = 0
    curve_notes = 0
    for entity in modelspace:
        kind = entity.dxftype()
        if kind not in {"LWPOLYLINE", "POLYLINE"}:
            continue
        try:
            is_closed = bool(entity.closed if kind == "LWPOLYLINE" else entity.is_closed)
            if not is_closed:
                ignored_open += 1
                continue
            path = make_path(entity)
            # Flatten arcs in a polyline so the boundary remains polygonal for calculation.
            # Native-unit tolerance is modest; this is a computational approximation of curved edges.
            flat_tol = 0.02 / scale if scale else 0.01
            points = [(v.x, v.y) for v in path.flattening(distance=max(flat_tol, 1e-6), segments=8)]
            if len(points) < 3:
                continue
            bulged = False
            if kind == "LWPOLYLINE":
                try:
                    bulged = any(abs(float(row[4])) > 1e-9 for row in entity.get_points("xyseb"))
                except Exception:
                    pass
            note = "Curved polyline segments tessellated for computation." if bulged else ""
            if bulged:
                curve_notes += 1
            cand = _candidate(points, len(candidates) + 1, f"{kind} · layer {entity.dxf.layer} · handle {entity.dxf.handle}", "dxf", unit_name, scale, True, entity.dxf.layer, None, note)
            if cand:
                candidates.append(cand)
        except Exception:
            continue
    candidates.sort(key=lambda c: _candidate_raw_area(c), reverse=True)
    for i, cand in enumerate(candidates, 1):
        cand.candidate_id = str(i)
    meta = {
        "format": "DXF", "insunits_code": insunits, "units": unit_name,
        "scale_to_m": scale, "open_polylines_ignored": ignored_open,
        "curved_polylines_tessellated": curve_notes,
        "warnings": ["Only closed LWPOLYLINE/POLYLINE entities are extracted. Put the site boundary on a clear layer and make it a closed polyline."]
    }
    if scale is None:
        meta["warnings"].append("DXF has unitless/unknown units. Calibrate from a known boundary edge or select the drawing units before calculating area.")
    return [c.to_dict() if hasattr(c, "to_dict") else c for c in candidates], meta


def _candidate_raw_area(candidate: BoundaryCandidate) -> float:
    try:
        return abs(Polygon(candidate.points).area)
    except Exception:
        return 0.0


def _utm_epsg_for_lon(lon: float, lat: float) -> int:
    zone = int(math.floor((lon + 180.0) / 6.0) + 1)
    zone = max(1, min(60, zone))
    return (32600 if lat >= 0 else 32700) + zone


def _project_lonlat(points: list[tuple[float, float]]) -> tuple[list[tuple[float, float]], str]:
    try:
        from pyproj import Transformer
    except ImportError as exc:
        raise RuntimeError("KML/KMZ coordinate conversion requires pyproj. Install requirements.txt and restart SiteIQ.") from exc
    if not points:
        return [], "WGS84"
    lon = sum(p[0] for p in points) / len(points)
    lat = sum(p[1] for p in points) / len(points)
    epsg = _utm_epsg_for_lon(lon, lat)
    transformer = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    return [(float(x), float(y)) for x, y in (transformer.transform(p[0], p[1]) for p in points)], f"WGS84 projected to EPSG:{epsg} (metres)"


def _coordinates_text(text: str) -> list[tuple[float, float]]:
    pts = []
    for token in text.strip().split():
        parts = token.split(",")
        if len(parts) >= 2:
            try:
                pts.append((float(parts[0]), float(parts[1])))  # KML lon,lat[,alt]
            except ValueError:
                continue
    return _dedupe_consecutive(pts)


def parse_kml(data: bytes, filename: str = "site.kml") -> tuple[list[dict], dict]:
    """Extract KML polygons and LineStrings. Coordinates are projected to local UTM metres."""
    if filename.lower().endswith(".kmz"):
        try:
            with zipfile.ZipFile(BytesIO(data)) as zf:
                kml_names = [n for n in zf.namelist() if n.lower().endswith(".kml")]
                if not kml_names:
                    raise ValueError("KMZ archive contains no KML file.")
                data = zf.read(kml_names[0])
        except zipfile.BadZipFile as exc:
            raise ValueError("KMZ file is not a valid ZIP/KMZ archive.") from exc
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ValueError(f"Could not read KML/XML: {exc}") from exc
    ns = {"k": "http://www.opengis.net/kml/2.2"}
    candidates: list[BoundaryCandidate] = []
    open_count = 0
    for idx, poly_elem in enumerate(root.findall(".//k:Polygon", ns), 1):
        coords_el = poly_elem.find(".//k:outerBoundaryIs/k:LinearRing/k:coordinates", ns)
        if coords_el is None or not coords_el.text:
            continue
        raw_lonlat = _coordinates_text(coords_el.text)
        if len(raw_lonlat) < 3:
            continue
        projected, crs_note = _project_lonlat(raw_lonlat)
        name = f"KML Polygon {idx}"
        cand = _candidate(projected, len(candidates)+1, name, "kml", crs_note, 1.0, True, "", None,
                          "Coordinates projected from WGS84. Inner rings are not yet modelled; verify source polygon has no relevant holes.")
        if cand:
            geographic_poly = Polygon(raw_lonlat)
            valid = bool(geographic_poly.is_valid and not geographic_poly.is_empty and geographic_poly.area > 0)
            if valid:
                location_pt = geographic_poly.centroid
                location_method = "KML polygon centroid"
            else:
                # For jurisdiction search only, use a stable anchor from the source vertices.
                # This does NOT repair the parcel or validate its area/buildable envelope.
                location_pt = LineString(raw_lonlat).centroid if len(raw_lonlat) >= 2 else None
                location_method = "KML polygon path centroid (geometry needs review)"
            cand_dict = cand.to_dict()
            cand_dict["source_points_wgs84"] = [[float(x), float(y)] for x, y in raw_lonlat]
            cand_dict["source_centroid_wgs84"] = [float(geographic_poly.centroid.x), float(geographic_poly.centroid.y)] if valid else None
            cand_dict["source_geometry_valid_wgs84"] = valid
            cand_dict["source_location_point_wgs84"] = [float(location_pt.x), float(location_pt.y)] if location_pt is not None else None
            cand_dict["source_location_method"] = location_method
            candidates.append(cand_dict)
    # Handle paths named as LineStrings. Open paths can still provide a location-search anchor,
    # but they cannot yield a parcel area until closure is confirmed and geometry validated.
    for idx, line_elem in enumerate(root.findall(".//k:LineString", ns), 1):
        coords_el = line_elem.find("k:coordinates", ns)
        if coords_el is None or not coords_el.text:
            continue
        raw_lonlat = _coordinates_text(coords_el.text)
        if len(raw_lonlat) < 3:
            continue
        closed = math.hypot(raw_lonlat[0][0]-raw_lonlat[-1][0], raw_lonlat[0][1]-raw_lonlat[-1][1]) < 1e-8
        projected, crs_note = _project_lonlat(raw_lonlat)
        note = "Google Earth LineString; open paths can locate the site, but the last-to-first edge must be confirmed before area/envelope calculations." if not closed else "Closed LineString projected to local UTM coordinates."
        if not closed:
            open_count += 1
        cand = _candidate(projected, len(candidates)+1, f"KML LineString {idx}", "kml", crs_note, 1.0, closed, "", None, note)
        if cand:
            line_geom = LineString(raw_lonlat)
            cand_dict = cand.to_dict()
            cand_dict["source_points_wgs84"] = [[float(x), float(y)] for x, y in raw_lonlat]
            cand_dict["source_location_point_wgs84"] = [float(line_geom.centroid.x), float(line_geom.centroid.y)] if not line_geom.is_empty else None
            cand_dict["source_location_method"] = "KML line centroid (lookup only; open path)" if not closed else "KML closed-line polygon centroid"
            if closed:
                geographic_poly = Polygon(raw_lonlat)
                valid = bool(geographic_poly.is_valid and not geographic_poly.is_empty and geographic_poly.area > 0)
                if valid:
                    centroid = geographic_poly.centroid
                    cand_dict["source_centroid_wgs84"] = [float(centroid.x), float(centroid.y)]  # [lon, lat]
                    cand_dict["source_location_point_wgs84"] = [float(centroid.x), float(centroid.y)]
                    cand_dict["source_geometry_valid_wgs84"] = True
                else:
                    cand_dict["source_centroid_wgs84"] = None
                    cand_dict["source_geometry_valid_wgs84"] = False
            else:
                cand_dict["source_centroid_wgs84"] = None
                cand_dict["source_geometry_valid_wgs84"] = False
            candidates.append(cand_dict)
    meta = {
        "format": "KML/KMZ", "units": "metres after UTM projection", "scale_to_m": 1.0,
        "open_paths": open_count,
        "warnings": ["Check that the Google Earth outline follows the legal site boundary, not a visual estimate or road centreline."],
    }
    if open_count:
        meta["warnings"].append("One or more paths are open. The site boundary will need explicit confirmation to connect the start and end points.")
    return [c.to_dict() if hasattr(c, "to_dict") else c for c in candidates], meta


def _pdf_drawing_points(drawing: dict) -> tuple[list[tuple[float, float]], bool, str] | None:
    points: list[tuple[float, float]] = []
    for item in drawing.get("items", []):
        if not item:
            continue
        typ = item[0]
        if typ == "l":
            p1, p2 = item[1], item[2]
            a, b = (float(p1.x), -float(p1.y)), (float(p2.x), -float(p2.y))
            if not points:
                points.append(a)
            elif math.hypot(points[-1][0]-a[0], points[-1][1]-a[1]) > 0.75:
                # Disconnected segments in one PDF drawing are not silently joined.
                return None
            points.append(b)
        elif typ == "re":
            rect = item[1]
            return ([(float(rect.x0), -float(rect.y0)), (float(rect.x1), -float(rect.y0)),
                     (float(rect.x1), -float(rect.y1)), (float(rect.x0), -float(rect.y1))], True, "PDF vector rectangle")
        elif typ == "qu":
            quad = item[1]
            qpts = [quad.ul, quad.ur, quad.lr, quad.ll]
            return ([(float(p.x), -float(p.y)) for p in qpts], True, "PDF vector quadrilateral")
        elif typ == "c":
            # Curves are not sampled in the first importer; avoid pretending they were recovered.
            return None
        else:
            return None
    if len(points) < 3:
        return None
    is_closed = bool(drawing.get("closePath")) or math.hypot(points[0][0]-points[-1][0], points[0][1]-points[-1][1]) <= 0.75
    return (points, is_closed, "PDF vector path")


def parse_pdf(data: bytes, max_pages: int = 6) -> tuple[list[dict], dict]:
    """Extract simple vector boundary candidates from PDF pages; coordinates remain PDF points."""
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PDF boundary extraction requires PyMuPDF. Install requirements.txt and restart SiteIQ.") from exc
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise ValueError(f"Could not open PDF: {exc}") from exc
    candidates: list[BoundaryCandidate] = []
    candidate_index = 0
    pages_checked = min(len(doc), max_pages)
    for page_i in range(pages_checked):
        page = doc[page_i]
        for drawing_i, drawing in enumerate(page.get_drawings(), 1):
            parsed = _pdf_drawing_points(drawing)
            if parsed is None:
                continue
            points, closed, note = parsed
            # Also expose open paths (>=3 vertices) to the UI; user must explicitly close them.
            if len(_dedupe_consecutive(points)) < 3:
                continue
            candidate_index += 1
            cand = _candidate(points, candidate_index, f"PDF page {page_i+1} · vector {drawing_i}", "pdf", "PDF points (72 points = 1 inch on source page)", None, closed, "", page_i+1, note)
            if cand:
                if not closed:
                    cand.notes += " Open path: must be explicitly confirmed/closed to use as a boundary."
                candidates.append(cand)
    doc.close()
    candidates.sort(key=lambda c: _candidate_raw_area(c), reverse=True)
    for i, cand in enumerate(candidates, 1):
        cand.candidate_id = str(i)
    meta = {
        "format": "PDF vector geometry", "units": "PDF points (needs scale calibration)", "scale_to_m": None,
        "pages_checked": pages_checked, "warnings": [
            "Only simple vector line paths, rectangles and quadrilaterals are extracted in this version.",
            "Raster/scanned PDFs do not expose parcel lines as vector geometry and need DXF/KML input or a manual tracing workflow.",
            "A scale calibration is mandatory: PDF page units do not establish real-world dimensions by themselves."
        ]
    }
    if not candidates:
        meta["warnings"].append("No closed/vector-like boundary candidates found. The PDF may be scanned, or the boundary may be fragmented across separate line objects.")
    return [c.to_dict() if hasattr(c, "to_dict") else c for c in candidates], meta


def parse_uploaded_boundary(filename: str, data: bytes) -> tuple[list[dict], dict]:
    ext = Path(filename).suffix.lower()
    if ext == ".dxf":
        return parse_dxf(data)
    if ext in {".kml", ".kmz"}:
        return parse_kml(data, filename)
    if ext == ".pdf":
        return parse_pdf(data)
    if ext == ".dwg":
        raise ValueError("Native DWG is not read directly in this version. In AutoCAD, use SAVEAS / export to DXF, then upload the DXF.")
    raise ValueError("Unsupported file type. Upload DXF, KML, KMZ or a vector PDF. Native DWG requires DXF export first.")


def candidate_edge_lengths(points: list[tuple[float, float]], scale_to_m: float | None = None) -> list[dict]:
    pts = _dedupe_consecutive([_point_tuple(p) for p in points])
    out = []
    if len(pts) < 3:
        return out
    factor = scale_to_m if scale_to_m is not None else 1.0
    for i, a in enumerate(pts):
        b = pts[(i+1) % len(pts)]
        length = math.hypot(b[0]-a[0], b[1]-a[1]) * factor
        out.append({"edge_index": i, "edge_label": f"Edge {i+1}", "length": length})
    return out


def polygon_from_candidate(candidate: dict, scale_to_m: float | None = None, close_open: bool = False) -> tuple[Polygon | None, dict]:
    """Create and validate a metric polygon. Never silently trusts open or invalid geometry."""
    pts = _dedupe_consecutive([_point_tuple(p) for p in candidate.get("points", [])])
    closed = bool(candidate.get("closed", False))
    notes = []
    if not closed and not close_open:
        return None, {"status": "open_boundary", "message": "The line does not return to its start. Confirm that the closing edge belongs to the legal plot boundary before continuing."}
    if not closed and close_open:
        notes.append("Open path was connected from its last point to its first point at user request. Verify that this closing segment matches the legal boundary.")
    if len(pts) < 3:
        return None, {"status": "insufficient_points", "message": "At least three unique boundary vertices are required."}
    factor = scale_to_m if scale_to_m is not None else candidate.get("scale_to_m")
    if factor is None or not math.isfinite(float(factor)) or float(factor) <= 0:
        return None, {"status": "scale_required", "message": "A reliable scale-to-metres conversion is required before calculating area or setbacks."}
    pts_m = [(x * float(factor), y * float(factor)) for x, y in pts]
    poly = Polygon(pts_m)
    if not poly.is_valid:
        return None, {"status": "invalid_geometry", "message": f"The boundary is invalid: {explain_validity(poly)}. Correct the source boundary; SiteIQ will not silently repair it."}
    if poly.is_empty or poly.area <= 1e-6:
        return None, {"status": "zero_area", "message": "The imported boundary has zero or negligible area."}
    if not poly.exterior.is_simple:
        return None, {"status": "self_intersection", "message": "The parcel outline self-intersects. Correct the source drawing before using this boundary."}
    return poly, {
        "status": "valid",
        "message": "Boundary closes and passes basic geometry validation. Match the imported outline to the authenticated survey before design use.",
        "notes": notes,
        "area_m2": float(poly.area), "perimeter_m": float(poly.length),
        "vertex_count": len(pts), "bounds_m": [float(v) for v in poly.bounds],
        "is_convex": bool(poly.equals(poly.convex_hull)),
        "area_method": "polygon area from imported, scaled boundary coordinates",
    }


def _edge_band(poly: Polygon, a: tuple[float, float], b: tuple[float, float], distance: float, extension: float) -> Any:
    """Return a conservative setback strip associated with one boundary edge."""
    line = LineString([a, b])
    length = line.length
    if length <= 1e-8 or distance <= 0:
        return GeometryCollection()
    ux, uy = (b[0]-a[0]) / length, (b[1]-a[1]) / length
    aa = (a[0] - ux*extension, a[1] - uy*extension)
    bb = (b[0] + ux*extension, b[1] + uy*extension)
    extended = LineString([aa, bb])
    # Flat caps approximate a parallel offset strip; clipping to parcel keeps it inside the site.
    return extended.buffer(distance, cap_style="flat", join_style="mitre").intersection(poly)


def calculate_setback_envelope(poly: Polygon, setback_result: dict, front_edges: list[int] | None = None, rear_edges: list[int] | None = None) -> dict:
    """Calculate an indicative inner polygon for an option.

    Uniform all-round setbacks use GEOS/GEOS-backed polygon erosion (mitred corners).
    Different front/rear/side setbacks remove per-edge strips. For complex concave geometry
    this is an indicative screening geometry and must be checked by the architect in CAD.
    Edge numbers are zero-based indices into the imported ring vertex order.
    """
    if poly is None or poly.is_empty or not poly.is_valid:
        return {"status": "invalid_input_geometry", "message": "A valid imported parcel polygon is required."}
    all_round = setback_result.get("all_round_m")
    if all_round is not None:
        d = float(all_round)
        env = poly.buffer(-d, join_style="mitre") if d > 0 else poly
        if env.is_empty:
            return {"status": "no_remaining_envelope", "message": f"A {d:.2f} m inset leaves no remaining buildable polygon.", "setback_m": d, "area_m2": 0.0, "geometry": None, "method": "uniform inward offset"}
        return _envelope_result(env, poly, "uniform inward offset", f"A uniform {d:.2f} m inset was applied to the imported boundary. Confirm the applicable rule and the boundary survey.", d)

    keys = ("front_m", "rear_m", "left_m", "right_m")
    if not all(setback_result.get(k) is not None for k in keys):
        return {"status": "setbacks_unresolved", "message": "Setback values are not configured, so SiteIQ did not calculate a buildable envelope."}
    pts = list(poly.exterior.coords)[:-1]
    n = len(pts)
    if n < 3:
        return {"status": "invalid_input_geometry", "message": "Boundary has fewer than three vertices."}
    front_set = set(front_edges or [])
    rear_set = set(rear_edges or [])
    if not front_set:
        return {"status": "frontage_classification_required", "message": "Identify the road-facing boundary edge(s) before applying different front/rear/side setbacks."}
    if front_set & rear_set:
        return {"status": "edge_role_conflict", "message": "An edge cannot be both front and rear."}
    if any(i < 0 or i >= n for i in front_set | rear_set):
        return {"status": "edge_index_invalid", "message": "A selected frontage/rear edge number does not match the imported boundary."}
    distances = []
    for i in range(n):
        if i in front_set:
            distances.append(float(setback_result["front_m"]))
        elif i in rear_set:
            distances.append(float(setback_result["rear_m"]))
        else:
            # Table 8 side setbacks may be equal; if values differ, default to the greater (conservative) side distance.
            distances.append(max(float(setback_result["left_m"]), float(setback_result["right_m"])))
    min_d = min(distances)
    base = poly.buffer(-min_d, join_style="mitre") if min_d > 0 else poly
    if base.is_empty:
        return {"status": "no_remaining_envelope", "message": "The minimum setback inset leaves no remaining buildable polygon.", "area_m2": 0.0, "geometry": None, "method": "variable edge setbacks"}
    # Remove additional strips wherever an edge's setback exceeds the minimum inward inset.
    envelope = base
    max_d = max(distances)
    for i, d in enumerate(distances):
        if d <= min_d + 1e-6:
            continue
        a, b = pts[i], pts[(i+1) % n]
        band = _edge_band(poly, a, b, d, extension=max_d*2 + 0.1)
        envelope = envelope.difference(band)
    if envelope.is_empty:
        return {"status": "no_remaining_envelope", "message": "The selected setbacks leave no remaining buildable polygon.", "area_m2": 0.0, "geometry": None, "method": "variable edge setbacks"}
    # simplify very small topology artifacts only, without changing the reported source geometry
    envelope = envelope.buffer(0)
    method = "variable edge setback strips (indicative for irregular geometry)"
    warning = "Front/rear/sides were assigned using your selected boundary edges. Variable edge strips are a preliminary geometry approximation, particularly near concave corners; inspect the resulting polygon against the CAD survey before design use."
    return _envelope_result(envelope, poly, method, warning, None)


def _envelope_result(env, site_poly, method, message, setback_m=None) -> dict:
    if isinstance(env, GeometryCollection):
        geoms = [g for g in env.geoms if g.geom_type in {"Polygon", "MultiPolygon"} and not g.is_empty]
        if not geoms:
            return {"status":"no_remaining_envelope", "message":"No usable polygon remains after setbacks.", "geometry":None, "area_m2":0.0, "method":method}
        from shapely.ops import unary_union
        env = unary_union(geoms)
    if env.geom_type not in {"Polygon", "MultiPolygon"}:
        return {"status":"unexpected_geometry", "message":"Setback operation did not result in a polygon. Review geometry manually.", "geometry":None, "area_m2":None, "method":method}
    polygons = [env] if env.geom_type == "Polygon" else list(env.geoms)
    component_count = len(polygons)
    warnings = []
    if component_count > 1:
        warnings.append(f"Setbacks split the envelope into {component_count} disjoint parts.")
    if env.area > 50 and env.buffer(-3.0).is_empty:
        warnings.append("Calculated envelope has narrow sections under 6.0 m in width.")
    return {
        "status": "calculated_preliminary",
        "message": message,
        "area_m2": float(env.area),
        "perimeter_m": float(env.length),
        "geometry_type": env.geom_type,
        "component_count": component_count,
        "warnings": warnings,
        "is_split": component_count > 1,
        "has_narrow_neck": bool(env.area > 50 and env.buffer(-3.0).is_empty),
        "setback_m": setback_m,
        "method": method,
        "geometry": mapping(env),
    }


def candidate_geojson(candidate: dict, scale_to_m: float | None = None, close_open: bool = False) -> dict:
    poly, validation = polygon_from_candidate(candidate, scale_to_m, close_open)
    if poly is None:
        raise ValueError(validation.get("message", "Boundary geometry could not be converted."))
    props = {
        "name": candidate.get("label", "Imported boundary"),
        "source_type": candidate.get("source_type"),
        "source_units": candidate.get("source_units"),
        "area_m2": validation["area_m2"],
        "perimeter_m": validation["perimeter_m"],
        "status": validation["status"],
    }
    return {"type":"FeatureCollection", "features":[{"type":"Feature", "geometry":mapping(poly), "properties":props}], "siteiq_crs":"Local metric coordinates; not a georeferenced deliverable unless source is KML/KMZ with UTM transformation."}


def make_boundary_preview(poly: Polygon, envelopes: dict[str, dict] | None = None, figsize=(9, 7)):
    """Return a matplotlib figure drawing the parcel and computed envelopes."""
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError("Boundary preview requires matplotlib.") from exc
    fig, ax = plt.subplots(figsize=figsize)
    x, y = poly.exterior.xy
    ax.fill(x, y, color="#e7efeb", alpha=1.0, zorder=1)
    ax.plot(x, y, color="#1f3338", linewidth=2.2, label="Imported plot boundary", zorder=3)
    palette = ["#d97743", "#5477a4", "#2c7a67", "#9467bd", "#b24a4a"]
    for idx, (name, result) in enumerate((envelopes or {}).items()):
        geom = result.get("geometry")
        if not geom:
            continue
        from shapely.geometry import shape
        g = shape(geom)
        geoms = [g] if g.geom_type == "Polygon" else list(g.geoms) if g.geom_type == "MultiPolygon" else []
        for j, p in enumerate(geoms):
            gx, gy = p.exterior.xy
            ax.fill(gx, gy, color=palette[idx % len(palette)], alpha=0.23, zorder=2)
            ax.plot(gx, gy, color=palette[idx % len(palette)], linewidth=1.8, label=name if j == 0 else None, zorder=4)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("Local coordinate (m)")
    ax.set_ylabel("Local coordinate (m)")
    ax.grid(True, color="#d5ded9", linewidth=0.6)
    ax.legend(loc="best", frameon=True, fontsize=8)
    ax.set_title("Imported boundary and preliminary setback envelopes", loc="left", fontweight="bold")
    fig.tight_layout()
    return fig



def make_boundary_edge_preview(poly: Polygon, figsize=None):
    """Draw a candidate boundary with numbered edges so frontage/rear selection is auditable."""
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError("Boundary preview requires matplotlib.") from exc
    minx, miny, maxx, maxy = poly.bounds
    width, height = max(maxx-minx, 1e-6), max(maxy-miny, 1e-6)
    ratio = width / height
    if figsize is None:
        figsize = (5.5, 7.5) if ratio < 0.8 else ((8, 5.5) if ratio > 1.4 else (6.5, 6.5))
    fig, ax = plt.subplots(figsize=figsize)
    xs, ys = poly.exterior.xy
    ax.fill(xs, ys, color="#e7efeb", alpha=1.0)
    ax.plot(xs, ys, color="#1f3338", linewidth=2.1, zorder=3)
    coords = list(poly.exterior.coords)[:-1]
    # Keep the preview readable for highly segmented vector-PDF/CAD boundaries.
    label_step = max(1, math.ceil(len(coords) / 28))
    for i, a in enumerate(coords):
        b = coords[(i+1) % len(coords)]
        length = math.hypot(b[0]-a[0], b[1]-a[1])
        ax.plot([a[0]], [a[1]], marker="o", markersize=2.5, color="#1f3338", zorder=4)
        if i % label_step == 0 or len(coords) <= 28:
            mx, my = (a[0]+b[0])/2, (a[1]+b[1])/2
            ax.annotate(f"E{i+1}  {length:.1f} m", (mx, my), xytext=(0, 0), textcoords="offset points",
                        ha="center", va="center", fontsize=8, fontweight="bold", color="#1f3338",
                        bbox={"boxstyle":"round,pad=0.22", "fc":"white", "ec":"#aab8b2", "alpha":0.95}, zorder=5)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("Local coordinate (m)")
    ax.set_ylabel("Local coordinate (m)")
    ax.grid(True, color="#d5ded9", linewidth=0.6)
    ax.set_title("Boundary candidate — edge IDs for frontage selection", loc="left", fontweight="bold")
    fig.tight_layout()
    return fig

def boundary_preview_png(poly: Polygon, envelopes: dict[str, dict] | None = None, figsize=(10, 7), dpi=180) -> bytes:
    """Render a clean boundary/envelope figure as PNG bytes for reports or downloads."""
    from io import BytesIO
    fig = make_boundary_preview(poly, envelopes, figsize=figsize)
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight", facecolor="white")
    try:
        import matplotlib.pyplot as plt
        plt.close(fig)
    except Exception:
        pass
    return buf.getvalue()


def export_boundary_dxf(poly: Polygon, envelopes: dict[str, dict] | None = None) -> bytes:
    """Export imported site polygon and calculated option envelopes as metric-coordinate DXF."""
    try:
        import ezdxf
    except ImportError as exc:
        raise RuntimeError("DXF export requires ezdxf. Install requirements.txt.") from exc
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6  # metres
    for layer, color in [("SITE_BOUNDARY", 7), ("ENVELOPE_OPT01", 1), ("ENVELOPE_OPT02", 5), ("ENVELOPE_OPT03", 3), ("ENVELOPE_OTHER", 6)]:
        if layer not in doc.layers:
            doc.layers.new(layer, dxfattribs={"color": color})
    msp = doc.modelspace()
    msp.add_lwpolyline(list(poly.exterior.coords)[:-1], close=True, dxfattribs={"layer": "SITE_BOUNDARY"})
    for idx, (name, result) in enumerate((envelopes or {}).items(), 1):
        geom_map = result.get("geometry")
        if not geom_map:
            continue
        from shapely.geometry import shape
        geom = shape(geom_map)
        layer = f"ENVELOPE_OPT{idx:02d}" if idx <= 3 else "ENVELOPE_OTHER"
        if layer not in doc.layers:
            doc.layers.new(layer, dxfattribs={"color": 6})
        polygons = [geom] if geom.geom_type == "Polygon" else list(geom.geoms) if geom.geom_type == "MultiPolygon" else []
        for p in polygons:
            msp.add_lwpolyline(list(p.exterior.coords)[:-1], close=True, dxfattribs={"layer": layer})
            for ring in p.interiors:
                msp.add_lwpolyline(list(ring.coords)[:-1], close=True, dxfattribs={"layer": layer})
    out = StringIO()
    doc.write(out)
    return out.getvalue().encode("utf-8")
