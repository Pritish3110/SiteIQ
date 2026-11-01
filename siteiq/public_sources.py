"""Curated official-source discovery for SiteIQ.

This module helps the architect find the right official map/regulation page without
having to prepare GIS files. It deliberately does not scrape or redistribute GIS
geometry from portals whose terms restrict reuse. An official reference page is not
considered a machine-readable zoning service unless one is explicitly configured.
"""
from __future__ import annotations

from typing import Iterable

# Sources reviewed for navigation. `queryable_geometry=False` means SiteIQ does not
# claim it can use the page itself to determine a legal boundary/zone automatically.
SOURCE_CATALOG = [
    {
        "id": "kanakapura_authority_directory",
        "title": "Planning Authority Kanakapura — official district directory",
        "url": "https://bengalurusouth.nic.in/en/divisions/planning-authority/",
        "hosts": ["bengalurusouth.nic.in"],
        "areas": ["kanakapura_planning_authority", "other_karnataka"],
        "types": ["planning_authority_directory", "contact"],
        "queryable_geometry": False,
        "note": "Official directory/contact reference. It does not itself provide a queryable plot-level jurisdiction or zoning polygon.",
    },
    {
        "id": "anekal_lpa_plan_candidate",
        "title": "Anekal LPA Master Plan 2031 — secondary copy; rule candidate only",
        "url": "https://tanksofanekal.in/wp-content/uploads/2025/03/Master-Plan-for-Anekal-Local-Planning-Area-2031-Complete-document.pdf",
        "hosts": ["tanksofanekal.in"],
        "areas": ["anekal_planning_authority", "other_karnataka"],
        "types": ["secondary_master_plan_copy", "zoning_regulations_candidate"],
        "queryable_geometry": False,
        "note": "Secondary copy used to seed candidate tables. Verify authority-issued operative plan and amendments before reliance; group-housing FAR path is not auto-calculated because secondary copies conflict.",
    },
    {
        "id": "kanakapura_lpa_plan_candidate",
        "title": "Kanakapura LPA Master Plan 2031 — secondary / tribunal-hosted copies",
        "url": "https://www.scribd.com/document/403292547/Kanakapura-LPA-Final-Report-pdf",
        "hosts": ["scribd.com"],
        "areas": ["kanakapura_planning_authority", "other_karnataka"],
        "types": ["secondary_master_plan_copy", "zoning_regulations_candidate"],
        "queryable_geometry": False,
        "note": "Source lead for candidate table transcriptions, not proof of the currently operative text or jurisdiction boundary.",
    },
    {
        "id": "nelamangala_lpa_plan_candidate",
        "title": "Nelamangala LPA Master Plan 2031 — secondary copy",
        "url": "https://www.scribd.com/document/293839941/Npa-Zoning-Regulation-2031",
        "hosts": ["scribd.com"],
        "areas": ["nelamangala_planning_authority", "other_karnataka"],
        "types": ["secondary_master_plan_copy", "zoning_regulations_candidate"],
        "queryable_geometry": False,
        "note": "Source lead for candidate table transcriptions, not proof of the currently operative text or jurisdiction boundary.",
    },
    {
        "id": "hoskote_district_directory",
        "title": "Hoskote — Bengaluru Rural District official directory",
        "url": "https://bangalorerural.nic.in/en/hoskote/",
        "hosts": ["bangalorerural.nic.in"],
        "areas": ["hoskote_planning_authority", "other_karnataka"],
        "types": ["district_directory", "planning_contact_reference"],
        "queryable_geometry": False,
        "note": "Official district directory with Hoskote taluk contacts. It is a contact/source lead, not proof of the parcel's notified planning boundary or a queryable zoning layer.",
    },
    {
        "id": "gba_gis_viewer",
        "title": "Greater Bengaluru Authority GIS Viewer",
        "url": "https://bbmp.gov.in/gisviewer/",
        "hosts": ["bbmp.gov.in"],
        "areas": ["bengaluru_rmp2015", "bda_lpa", "bmrda"],
        "types": ["interactive_gis_viewer", "corporation_ward_context"],
        "queryable_geometry": False,
        "note": "Official interactive viewer for city corporation/ward context. It is not treated by SiteIQ as a verified planning-authority or land-use API.",
    },
    {
        "id": "gba_portal",
        "title": "Greater Bengaluru Authority — official portal",
        "url": "https://gba.karnataka.gov.in/",
        "hosts": ["gba.karnataka.gov.in"],
        "areas": ["bengaluru_rmp2015", "bda_lpa", "bmrda"],
        "types": ["official_authority_portal"],
        "queryable_geometry": False,
        "note": "Use for current notifications and corporate/jurisdiction information; verify the parcel against the notified planning boundary.",
    },
    {
        "id": "bda_rmp2015",
        "title": "Bangalore Development Authority — RMP 2015 maps and zoning regulations",
        "url": "https://eng.bdabangalore.org/masterplan.html",
        "hosts": ["eng.bdabangalore.org"],
        "areas": ["bengaluru_rmp2015", "bda_lpa", "bmrda"],
        "types": ["official_land_use_map_catalogue", "regulations"],
        "queryable_geometry": False,
        "note": "Contains published RMP map sheets and regulations. A PDF map sheet is a reference, not automatically a georeferenced zoning polygon.",
    },
    {
        "id": "karnataka_urban_development",
        "title": "Government of Karnataka portal",
        "url": "https://karnataka.gov.in/",
        "hosts": ["karnataka.gov.in"],
        "areas": ["other_karnataka", "mysuru_development_authority", "hubballi_dharwad_udau", "bmrda"],
        "types": ["government_notifications", "rules"],
        "queryable_geometry": False,
        "note": "General state portal. SiteIQ has not identified a verified queryable planning-zone service for this location; confirm the responsible authority and its current master plan.",
    },
    {
        "id": "mysuru_authority",
        "title": "Mysuru Development Authority — official portal",
        "url": "https://www.mudamysore.gov.in/",
        "hosts": ["mudamysore.gov.in"],
        "areas": ["mysuru_development_authority", "other_karnataka"],
        "types": ["authority_portal", "master_plan_reference"],
        "queryable_geometry": False,
        "note": "Authority reference link only; no SiteIQ-compatible current zoning layer is assumed.",
    },
    {
        "id": "tumakuru_tuda_portal",
        "title": "Tumakuru Urban Development Authority (TUDA) — official portal",
        "url": "https://tuda.karnataka.gov.in/",
        "hosts": ["tuda.karnataka.gov.in"],
        "areas": ["tumakuru_uda", "other_karnataka"],
        "types": ["authority_portal", "master_plan_reference"],
        "queryable_geometry": False,
        "note": "Official TUDA portal and master plan reference. Confirm parcel inclusion and operative zoning regulations.",
    },
]


def official_sources_for_context(authority_key: str | None, locality_text: str = "") -> list[dict]:
    """Return a concise, location-relevant set of official source links.

    The function doesn't label any link as an available GIS API. It is a source
    discovery/navigation helper to remove the need for an architect to find GIS files.
    """
    text = (locality_text or "").casefold()
    key = authority_key or "other_karnataka"
    ids: list[str] = []

    if key == "kanakapura_planning_authority" or "kanakapura" in text:
        ids.extend(["kanakapura_authority_directory", "kanakapura_lpa_plan_candidate", "karnataka_urban_development"])
    elif key == "hoskote_planning_authority" or "hoskote" in text or "hosakote" in text:
        ids.extend(["hoskote_district_directory", "karnataka_urban_development"])
    elif key == "anekal_planning_authority" or "anekal" in text:
        ids.extend(["anekal_lpa_plan_candidate", "karnataka_urban_development"])
    elif key == "nelamangala_planning_authority" or "nelamangala" in text:
        ids.extend(["nelamangala_lpa_plan_candidate", "karnataka_urban_development"])
    elif key == "bengaluru_rmp2015" or any(t in text for t in ("bengaluru", "bangalore")):
        ids.extend(["gba_gis_viewer", "gba_portal", "bda_rmp2015"])
    elif key == "bda_lpa":
        ids.extend(["bda_rmp2015", "gba_gis_viewer", "karnataka_urban_development"])
    elif key == "bmrda":
        ids.extend(["karnataka_urban_development", "bda_rmp2015"])
    elif key == "mysuru_development_authority" or any(t in text for t in ("mysuru", "mysore")):
        ids.extend(["mysuru_authority", "karnataka_urban_development"])
    elif key == "tumakuru_uda" or "tumakuru" in text or "tumkur" in text:
        ids.extend(["tumakuru_tuda_portal", "karnataka_urban_development"])
    else:
        ids.extend(["karnataka_urban_development"])

    # Keep unique, stable order and return data for UI rendering/report notes.
    by_id = {source["id"]: source for source in SOURCE_CATALOG}
    out = []
    for sid in ids:
        source = by_id[sid]
        out.append({**source, "status": "official_reference_available_not_a_queryable_zone_layer"})
    return out
