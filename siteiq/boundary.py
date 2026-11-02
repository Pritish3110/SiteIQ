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
from shapely.ops import unary_union
from shapely.validation import explain_validity
from shapely.ops import transform as shapely_transform

MAX_XML_BYTES = 50 * 1024 * 1024
MAX_KMZ_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
DEFAULT_MIN_CLEAR_WIDTH_M = 6.0  # Screening aid only; not a statutory value.
PLAUSIBLE_PARCEL_AREA_M2 = (20.0, 5_000_000.0)

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
    block_refs = sum(1 for e in modelspace if e.dxftype() == "INSERT")
    meta = {
        "format": "DXF", "block_references_not_read": block_refs, "insunits_code": insunits, "units": unit_name,
        "scale_to_m": scale, "open_polylines_ignored": ignored_open,
        "curved_polylines_tessellated": curve_notes,
        "warnings": ["Only closed LWPOLYLINE/POLYLINE entities are extracted. Put the site boundary on a clear layer and make it a closed polyline."]
    }
    if ignored_open:
        meta["warnings"].append(f"{ignored_open} open polyline(s) were ignored.")
    if block_refs:
        meta["warnings"].append(f"{block_refs} block reference(s) were not read. Explode the site boundary if it sits inside a block.")
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


def _local_transformer(points: list[tuple[float, float]]):
    """Transverse Mercator centred on the feature (scale 1), so parcel areas are true to well under 0.01%."""
    try:
        from pyproj import Transformer
    except ImportError as exc:
        raise RuntimeError("KML/KMZ coordinate conversion requires pyproj. Install requirements.txt and restart SiteIQ.") from exc
    lon = sum(p[0] for p in points) / len(points)
    lat = sum(p[1] for p in points) / len(points)
    crs = f"+proj=tmerc +lat_0={lat:.8f} +lon_0={lon:.8f} +k=1 +x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs"
    return Transformer.from_crs("EPSG:4326", crs, always_xy=True), lat, lon


def _project_lonlat(points: list[tuple[float, float]], transformer=None) -> tuple[list[tuple[float, float]], str]:
    if not points:
        return [], "WGS84"
    if transformer is None:
        transformer, lat, lon = _local_transformer(points)
        note = f"WGS84 projected to local transverse Mercator at {lat:.6f}, {lon:.6f} (metres, scale 1)"
    else:
        note = "WGS84 projected to local transverse Mercator (metres, scale 1)"
    return [(float(x), float(y)) for x, y in (transformer.transform(p[0], p[1]) for p in points)], note


def _coordinates_raw(text: str) -> list[tuple[float, float]]:
    """Parse KML lon,lat tuples, keeping the closing vertex so ring closure can be detected."""
    pts = []
    for token in text.strip().split():
        parts = token.split(",")
        if len(parts) >= 2:
            try:
                pts.append((float(parts[0]), float(parts[1])))  # KML lon,lat[,alt]
            except ValueError:
                continue
    return pts


def _coordinates_text(text: str) -> list[tuple[float, float]]:
    return _dedupe_consecutive(_coordinates_raw(text))


def _local_name(element) -> str:
    return str(element.tag).rsplit("}", 1)[-1]


def _descendants(element, name: str) -> list:
    return [e for e in element.iter() if _local_name(e) == name]


def _first_child(element, name: str):
    return next((e for e in element if _local_name(e) == name), None)


def _ring_coordinates(boundary_element) -> list[tuple[float, float]]:
    found = _descendants(boundary_element, "coordinates")
    return _coordinates_text(found[0].text) if found and found[0].text else []


def _read_kml_bytes(data: bytes, filename: str) -> bytes:
    """Return KML XML from KML/KMZ bytes, refusing archive bombs and entity-expansion payloads."""
    if filename.lower().endswith(".kmz"):
        try:
            with zipfile.ZipFile(BytesIO(data)) as zf:
                infos = [i for i in zf.infolist() if i.filename.lower().endswith(".kml")]
                if not infos:
                    raise ValueError("KMZ archive contains no KML file.")
                if sum(i.file_size for i in zf.infolist()) > MAX_KMZ_UNCOMPRESSED_BYTES:
                    raise ValueError("KMZ archive is too large when uncompressed.")
                chosen = next((i for i in infos if i.filename.lower().endswith("doc.kml")), infos[0])
                data = zf.read(chosen)
        except zipfile.BadZipFile as exc:
            raise ValueError("KMZ file is not a valid ZIP/KMZ archive.") from exc
    if len(data) > MAX_XML_BYTES:
        raise ValueError("KML file is too large to process safely.")
    head = data[:4096].upper()
    if b"<!DOCTYPE" in head or b"<!ENTITY" in data.upper():
        raise ValueError("KML files containing DOCTYPE or ENTITY declarations are not accepted.")
    return data


def parse_kml(data: bytes, filename: str = "site.kml") -> tuple[list[dict], dict]:
    """Extract KML polygons (with holes) and LineStrings into local metric coordinates.

    Matching ignores the XML namespace, so KML 2.0/2.1/2.2 and Google gx files all parse.
    """
    data = _read_kml_bytes(data, filename)
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ValueError(f"Could not read KML/XML: {exc}") from exc
    names: dict[int, str] = {}
    for placemark in _descendants(root, "Placemark"):
        name_el = _first_child(placemark, "name")
        label = (name_el.text or "").strip() if name_el is not None else ""
        if label:
            for geom in placemark.iter():
                names[id(geom)] = label
    candidates: list[dict] = []
    open_count = 0
    hole_count = 0
    for idx, poly_elem in enumerate(_descendants(root, "Polygon"), 1):
        outer = _first_child(poly_elem, "outerBoundaryIs")
        raw_lonlat = _ring_coordinates(outer) if outer is not None else []
        if len(raw_lonlat) < 3:
            continue
        transformer, _, _ = _local_transformer(raw_lonlat)
        projected, crs_note = _project_lonlat(raw_lonlat)
        holes_wgs84 = [r for r in (_ring_coordinates(e) for e in poly_elem if _local_name(e) == "innerBoundaryIs") if len(r) >= 3]
        holes_m = [_project_lonlat(r, transformer)[0] for r in holes_wgs84]
        hole_count += len(holes_m)
        placemark = names.get(id(poly_elem))
        name = f"{placemark} · polygon {idx}" if placemark else f"KML Polygon {idx}"
        note = "Coordinates projected from WGS84."
        if holes_m:
            note += f" {len(holes_m)} inner ring(s) are excluded from the parcel area."
        cand = _candidate(projected, len(candidates)+1, name, "kml", crs_note, 1.0, True, "", None, note)
        if cand:
            geographic_poly = Polygon(raw_lonlat, holes_wgs84)
            valid = bool(geographic_poly.is_valid and not geographic_poly.is_empty and geographic_poly.area > 0)
            if valid:
                centroid = geographic_poly.centroid
                inside = geographic_poly.contains(centroid)
                location_pt = centroid if inside else geographic_poly.representative_point()
                location_method = "KML polygon centroid" if inside else "KML polygon interior point (centroid falls outside this concave parcel)"
            else:
                # For jurisdiction search only, use a stable anchor from the source vertices.
                # This does NOT repair the parcel or validate its area/buildable envelope.
                location_pt = LineString(raw_lonlat).centroid if len(raw_lonlat) >= 2 else None
                location_method = "KML polygon path centroid (geometry needs review)"
            cand_dict = cand.to_dict()
            cand_dict["holes"] = [[list(p) for p in r] for r in holes_m]
            cand_dict["source_points_wgs84"] = [[float(x), float(y)] for x, y in raw_lonlat]
            cand_dict["source_holes_wgs84"] = [[[float(x), float(y)] for x, y in r] for r in holes_wgs84]
            cand_dict["source_centroid_wgs84"] = [float(geographic_poly.centroid.x), float(geographic_poly.centroid.y)] if valid else None
            cand_dict["source_geometry_valid_wgs84"] = valid
            cand_dict["source_location_point_wgs84"] = [float(location_pt.x), float(location_pt.y)] if location_pt is not None else None
            cand_dict["source_location_method"] = location_method
            candidates.append(cand_dict)
    # Open paths can still provide a location-search anchor, but they cannot yield a parcel
    # area until closure is confirmed and geometry validated.
    for idx, line_elem in enumerate(_descendants(root, "LineString"), 1):
        coords_el = _first_child(line_elem, "coordinates")
        if coords_el is None or not coords_el.text:
            continue
        raw_with_closure = _coordinates_raw(coords_el.text)
        raw_lonlat = _dedupe_consecutive(raw_with_closure)
        if len(raw_lonlat) < 3:
            continue
        closed = math.hypot(raw_with_closure[0][0]-raw_with_closure[-1][0], raw_with_closure[0][1]-raw_with_closure[-1][1]) < 1e-7
        projected, crs_note = _project_lonlat(raw_lonlat)
        note = "Google Earth LineString; open paths can locate the site, but the last-to-first edge must be confirmed before area/envelope calculations." if not closed else "Closed LineString projected to local metric coordinates."
        if not closed:
            open_count += 1
        placemark = names.get(id(line_elem))
        cand = _candidate(projected, len(candidates)+1, f"{placemark} · path {idx}" if placemark else f"KML LineString {idx}", "kml", crs_note, 1.0, closed, "", None, note)
        if cand:
            line_geom = LineString(raw_lonlat)
            cand_dict = cand.to_dict()
            cand_dict["source_points_wgs84"] = [[float(x), float(y)] for x, y in raw_lonlat]
            cand_dict["source_location_point_wgs84"] = [float(line_geom.centroid.x), float(line_geom.centroid.y)] if not line_geom.is_empty else None
            cand_dict["source_location_method"] = "KML line centroid (lookup only; open path)" if not closed else "KML closed-line polygon centroid"
            cand_dict["source_centroid_wgs84"] = None
            cand_dict["source_geometry_valid_wgs84"] = False
            if closed:
                geographic_poly = Polygon(raw_lonlat)
                if geographic_poly.is_valid and not geographic_poly.is_empty and geographic_poly.area > 0:
                    centroid = geographic_poly.centroid
                    cand_dict["source_centroid_wgs84"] = [float(centroid.x), float(centroid.y)]  # [lon, lat]
                    cand_dict["source_location_point_wgs84"] = [float(centroid.x), float(centroid.y)]
                    cand_dict["source_geometry_valid_wgs84"] = True
            candidates.append(cand_dict)
    meta = {
        "format": "KML/KMZ", "units": "metres after local projection", "scale_to_m": 1.0,
        "open_paths": open_count, "inner_rings": hole_count,
        "warnings": ["Check that the Google Earth outline follows the legal site boundary, not a visual estimate or road centreline."],
    }
    if open_count:
        meta["warnings"].append("One or more paths are open. The site boundary will need explicit confirmation to connect the start and end points.")
    if hole_count:
        meta["warnings"].append(f"{hole_count} inner ring(s) found. They are excluded from parcel area; confirm they are genuinely outside the title.")
    if not candidates:
        meta["warnings"].append("No Polygon or LineString geometry was found in this file.")
    return candidates, meta


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
    holes_m = [[(float(p[0]) * float(factor), float(p[1]) * float(factor)) for p in ring] for ring in (candidate.get("holes") or [])]
    poly = Polygon(pts_m, holes_m)
    if not poly.is_valid:
        return None, {"status": "invalid_geometry", "message": f"The boundary is invalid: {explain_validity(poly)}. Correct the source boundary; SiteIQ will not silently repair it."}
    if poly.is_empty or poly.area <= 1e-6:
        return None, {"status": "zero_area", "message": "The imported boundary has zero or negligible area."}
    if not poly.exterior.is_simple:
        return None, {"status": "self_intersection", "message": "The parcel outline self-intersects. Correct the source drawing before using this boundary."}
    if holes_m:
        hole_area = sum(Polygon(r).area for r in holes_m)
        notes.append(f"{len(holes_m)} inner ring(s) totalling {hole_area:,.2f} m² are excluded from the area.")
    if not PLAUSIBLE_PARCEL_AREA_M2[0] <= poly.area <= PLAUSIBLE_PARCEL_AREA_M2[1]:
        notes.append(f"Area of {poly.area:,.2f} m² is unusual for a parcel. Check the drawing units and scale.")
    return poly, {
        "status": "valid",
        "message": "Boundary closes and passes basic geometry validation. Match the imported outline to the authenticated survey before design use.",
        "notes": notes,
        "area_m2": float(poly.area), "perimeter_m": float(poly.length),
        "hole_count": len(holes_m), "vertex_count": len(pts), "bounds_m": [float(v) for v in poly.bounds],
        "is_convex": bool(poly.equals(poly.convex_hull)),
        "area_method": "polygon area from imported, scaled boundary coordinates",
    }


def _unit(dx: float, dy: float) -> tuple[float, float] | None:
    length = math.hypot(dx, dy)
    return (dx / length, dy / length) if length > 1e-9 else None


def _line_intersection(p, d, q, e) -> tuple[float, float] | None:
    denom = d[0] * e[1] - d[1] * e[0]
    if abs(denom) < 1e-9:
        return None
    t = ((q[0] - p[0]) * e[1] - (q[1] - p[1]) * e[0]) / denom
    return (p[0] + t * d[0], p[1] + t * d[1])


def _setback_zone(ring: list[tuple[float, float]], distances: list[float]):
    """Union of per-edge setback strips and mitred corner fills along one CCW ring.

    Each strip is limited to its own edge, so a setback never reaches beyond that edge onto
    unrelated parts of a concave plot. With equal distances the result matches a mitred
    inward buffer; half-plane intersection is deliberately not used because it fails on
    concave plots.
    """
    n = len(ring)
    pieces = []
    for i in range(n):
        a, b = ring[i], ring[(i + 1) % n]
        d = distances[i]
        direction = _unit(b[0] - a[0], b[1] - a[1])
        if direction is None or d <= 0:
            continue
        nx, ny = -direction[1], direction[0]
        strip = Polygon([a, b, (b[0] + nx * d, b[1] + ny * d), (a[0] + nx * d, a[1] + ny * d)])
        if strip.is_valid and strip.area > 0:
            pieces.append(strip)
    for j in range(n):
        v = ring[j]
        prev_pt, next_pt = ring[j - 1], ring[(j + 1) % n]
        d1, d2 = distances[j - 1], distances[j]
        u1 = _unit(v[0] - prev_pt[0], v[1] - prev_pt[1])
        u2 = _unit(next_pt[0] - v[0], next_pt[1] - v[1])
        if u1 is None or u2 is None or max(d1, d2) <= 0:
            continue
        n1, n2 = (-u1[1], u1[0]), (-u2[1], u2[0])
        o1 = (v[0] + n1[0] * d1, v[1] + n1[1] * d1)
        o2 = (v[0] + n2[0] * d2, v[1] + n2[1] * d2)
        corner = [v, o1, o2]
        mitre = _line_intersection(o1, u1, o2, u2)
        if mitre is not None and math.hypot(mitre[0] - v[0], mitre[1] - v[1]) <= 5.0 * max(d1, d2):
            corner.append(mitre)
        hull = Polygon(corner).convex_hull if len(corner) >= 3 else None
        if hull is not None and hull.geom_type == "Polygon" and hull.area > 0:
            pieces.append(hull)
    return unary_union(pieces) if pieces else GeometryCollection()


def calculate_setback_envelope(
    poly: Polygon, setback_result: dict, front_edges: list[int] | None = None, rear_edges: list[int] | None = None,
    edge_extra_m: dict[int, float] | None = None, min_clear_width_m: float = DEFAULT_MIN_CLEAR_WIDTH_M,
) -> dict:
    """Calculate a preliminary inner polygon for an option.

    Edge numbers are zero-based indices into the imported ring vertex order. ``edge_extra_m``
    adds a further no-build depth along named edges (road widening, drain buffer) on top of
    the rule setback. Inner rings carry the side distance.
    """
    if poly is None or poly.is_empty or not poly.is_valid:
        return {"status": "invalid_input_geometry", "message": "A valid imported parcel polygon is required."}
    extras = {int(k): float(v) for k, v in (edge_extra_m or {}).items() if float(v) > 0}
    pts = list(poly.exterior.coords)[:-1]
    n = len(pts)
    if n < 3:
        return {"status": "invalid_input_geometry", "message": "Boundary has fewer than three vertices."}
    if any(i < 0 or i >= n for i in extras):
        return {"status": "edge_index_invalid", "message": "A no-build edge number does not match the imported boundary."}
    all_round = setback_result.get("all_round_m")
    if all_round is not None and not extras:
        d = float(all_round)
        env = poly.buffer(-d, join_style="mitre") if d > 0 else poly
        if env.is_empty:
            return {"status": "no_remaining_envelope", "message": f"A {d:.2f} m inset leaves no remaining buildable polygon.", "setback_m": d, "area_m2": 0.0, "geometry": None, "method": "uniform inward offset"}
        return _envelope_result(env, poly, "uniform inward offset", f"A uniform {d:.2f} m inset was applied to the imported boundary. Confirm the applicable rule and the boundary survey.", d, min_clear_width_m)

    front_set = set(front_edges or [])
    rear_set = set(rear_edges or [])
    if all_round is not None:
        base = [float(all_round)] * n
        side = float(all_round)
    else:
        keys = ("front_m", "rear_m", "left_m", "right_m")
        if not all(setback_result.get(k) is not None for k in keys):
            return {"status": "setbacks_unresolved", "message": "Setback values are not configured, so SiteIQ did not calculate a buildable envelope."}
        if not front_set:
            return {"status": "frontage_classification_required", "message": "Identify the road-facing boundary edge(s) before applying different front/rear/side setbacks."}
        if front_set & rear_set:
            return {"status": "edge_role_conflict", "message": "An edge cannot be both front and rear."}
        if any(i < 0 or i >= n for i in front_set | rear_set):
            return {"status": "edge_index_invalid", "message": "A selected frontage/rear edge number does not match the imported boundary."}
        # Left and right are not tagged per edge, so the greater side distance applies to every side edge.
        side = max(float(setback_result["left_m"]), float(setback_result["right_m"]))
        base = [float(setback_result["front_m"]) if i in front_set else float(setback_result["rear_m"]) if i in rear_set else side for i in range(n)]
    distances = [base[i] + extras.get(i, 0.0) for i in range(n)]
    ccw = poly.exterior.is_ccw
    ring = pts if ccw else pts[::-1]
    # Reversing a ring shifts edge i to n-2-i modulo n, so the distances must follow it.
    ring_distances = distances if ccw else [distances[(n - 2 - i) % n] for i in range(n)]
    removed = [_setback_zone(ring, ring_distances)]
    for interior in poly.interiors:
        removed.append(Polygon(interior).buffer(side, join_style="mitre"))
    envelope = poly.difference(unary_union(removed))
    method = "per-edge setback offset"
    if envelope.is_empty:
        return {"status": "no_remaining_envelope", "message": "The selected setbacks leave no remaining buildable polygon.", "area_m2": 0.0, "geometry": None, "method": method}
    envelope = envelope.buffer(0)
    message = "Each boundary edge was offset by its own setback. Confirm the edge roles and the boundary survey before design use."
    return _envelope_result(envelope, poly, method, message, None, min_clear_width_m)


def _narrow_sections(env, min_clear_width_m: float) -> tuple[bool, float]:
    """Find parts of the envelope a rectangle of the given clear width cannot reach (morphological opening)."""
    half = min_clear_width_m / 2.0
    eroded = env.buffer(-half, join_style="mitre")
    opened = eroded.buffer(half, join_style="mitre") if not eroded.is_empty else eroded
    narrow = env.difference(opened) if not opened.is_empty else env
    narrow_area = float(narrow.area)
    return narrow_area > max(1.0, 0.005 * float(env.area)), narrow_area


def _envelope_result(env, site_poly, method, message, setback_m=None, min_clear_width_m: float = DEFAULT_MIN_CLEAR_WIDTH_M) -> dict:
    if isinstance(env, GeometryCollection):
        geoms = [g for g in env.geoms if g.geom_type in {"Polygon", "MultiPolygon"} and not g.is_empty]
        if not geoms:
            return {"status":"no_remaining_envelope", "message":"No usable polygon remains after setbacks.", "geometry":None, "area_m2":0.0, "method":method}
        env = unary_union(geoms)
    if env.geom_type not in {"Polygon", "MultiPolygon"}:
        return {"status":"unexpected_geometry", "message":"Setback operation did not result in a polygon. Review geometry manually.", "geometry":None, "area_m2":None, "method":method}
    polygons = [env] if env.geom_type == "Polygon" else list(env.geoms)
    component_count = len(polygons)
    warnings = []
    if component_count > 1:
        warnings.append(f"Setbacks split the envelope into {component_count} disjoint parts.")
    has_narrow, narrow_area = _narrow_sections(env, min_clear_width_m)
    if has_narrow:
        warnings.append(f"About {narrow_area:,.1f} m² of the envelope is narrower than {min_clear_width_m:g} m clear width (screening check, not a statutory limit).")
    return {
        "status": "calculated_preliminary",
        "message": message,
        "area_m2": float(env.area),
        "perimeter_m": float(env.length),
        "geometry_type": env.geom_type,
        "component_count": component_count,
        "warnings": warnings,
        "is_split": component_count > 1,
        "has_narrow_neck": has_narrow,
        "narrow_area_m2": round(narrow_area, 2),
        "min_clear_width_m": min_clear_width_m,
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
    ax.fill(x, y, color="#F4F4F4", alpha=1.0, zorder=1)
    ax.plot(x, y, color="#111111", linewidth=2.2, label="Imported plot boundary", zorder=3)
    palette = ["#111111", "#555555", "#888888", "#333333", "#AAAAAA"]
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
    ax.grid(True, color="#E5E5E5", linewidth=0.5)
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
    ax.fill(xs, ys, color="#F4F4F4", alpha=1.0)
    ax.plot(xs, ys, color="#111111", linewidth=2.1, zorder=3)
    coords = list(poly.exterior.coords)[:-1]
    # Keep the preview readable for highly segmented vector-PDF/CAD boundaries.
    label_step = max(1, math.ceil(len(coords) / 28))
    for i, a in enumerate(coords):
        b = coords[(i+1) % len(coords)]
        length = math.hypot(b[0]-a[0], b[1]-a[1])
        ax.plot([a[0]], [a[1]], marker="o", markersize=2.5, color="#111111", zorder=4)
        if i % label_step == 0 or len(coords) <= 28:
            mx, my = (a[0]+b[0])/2, (a[1]+b[1])/2
            ax.annotate(f"E{i+1}  {length:.1f} m", (mx, my), xytext=(0, 0), textcoords="offset points",
                        ha="center", va="center", fontsize=8, fontweight="bold", color="#111111",
                        bbox={"boxstyle":"square,pad=0.22", "fc":"white", "ec":"#BBBBBB", "alpha":0.95}, zorder=5)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("Local coordinate (m)")
    ax.set_ylabel("Local coordinate (m)")
    ax.grid(True, color="#E5E5E5", linewidth=0.5)
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
    for ring in poly.interiors:
        msp.add_lwpolyline(list(ring.coords)[:-1], close=True, dxfattribs={"layer": "SITE_BOUNDARY"})
    option_index = 0
    for name, result in (envelopes or {}).items():
        is_basement = str(name).lower().endswith(" basement")
        if not is_basement:
            option_index += 1
        geom_map = result.get("geometry")
        if not geom_map:
            continue
        from shapely.geometry import shape
        geom = shape(geom_map)
        if is_basement:
            layer = f"BASEMENT_OPT{max(option_index, 1):02d}"
        else:
            layer = f"ENVELOPE_OPT{option_index:02d}" if option_index <= 3 else "ENVELOPE_OTHER"
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
