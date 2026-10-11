"""Extract Jakarta roads, rail, coastline, admin boundaries and place labels
from a Java OSM extract into a compact JSON file.

Usage: python -I extract.py <java.osm.pbf> <out.json>
"""
import json
import sys

import osmium

PBF, OUT = sys.argv[1], sys.argv[2]

# Generous bbox around mainland DKI Jakarta (lon/lat)
W, S, E, N = 106.66, -6.40, 107.00, -6.06

ROAD_CLASSES = {
    "motorway", "motorway_link", "trunk", "trunk_link",
    "primary", "primary_link", "secondary", "secondary_link", "tertiary",
}
PLACE_TYPES = {"city", "town", "suburb", "city_district", "quarter"}


def in_bbox(lon, lat):
    return W <= lon <= E and S <= lat <= N


# Pass 1: admin relations (DKI province + its kota/kabupaten)
admin = {}
for r in osmium.FileProcessor(PBF, osmium.osm.RELATION):
    t = r.tags
    if t.get("boundary") != "administrative" or t.get("admin_level") not in ("4", "5"):
        continue
    name = t.get("name", "")
    if t.get("ISO3166-2") == "ID-JK" or "Jakarta" in name or name == "Kepulauan Seribu":
        admin[r.id] = {
            "name": name,
            "level": t.get("admin_level"),
            "ways": [m.ref for m in r.members if m.type == "w" and m.role in ("outer", "")],
        }
print("admin relations:", [(a["name"], a["level"]) for a in admin.values()], flush=True)
admin_way_ids = {w for a in admin.values() for w in a["ways"]}

# Pass 2: ways
ways = {}
for w in osmium.FileProcessor(PBF, osmium.osm.WAY):
    t = w.tags
    hw = t.get("highway")
    kind = None
    if hw in ROAD_CLASSES:
        kind = hw
    elif t.get("railway") == "rail" and t.get("service") is None:
        kind = "rail"
    elif t.get("natural") == "coastline":
        kind = "coast"
    elif t.get("waterway") in ("river", "canal") and t.get("name"):
        kind = "river"
    if kind is None and w.id not in admin_way_ids:
        continue
    ways[w.id] = {
        "k": kind or "admin",
        "n": t.get("name", ""),
        "ref": t.get("ref", ""),
        "nodes": [n.ref for n in w.nodes],
    }
print("candidate ways:", len(ways), flush=True)
needed = {n for w in ways.values() for n in w["nodes"]}

# Pass 3: node locations + place labels
loc = {}
places = []
for n in osmium.FileProcessor(PBF, osmium.osm.NODE):
    if n.id in needed:
        loc[n.id] = (round(n.location.lon, 6), round(n.location.lat, 6))
    pt = n.tags.get("place")
    if pt in PLACE_TYPES and n.tags.get("name"):
        lon, lat = n.location.lon, n.location.lat
        if in_bbox(lon, lat):
            places.append({"t": pt, "n": n.tags["name"], "c": [round(lon, 5), round(lat, 5)]})
print("node locations:", len(loc), "places:", len(places), flush=True)

out_ways = []
admin_geom = {}
for wid, w in ways.items():
    coords = [loc[n] for n in w["nodes"] if n in loc]
    if len(coords) < 2:
        continue
    if wid in admin_way_ids:
        admin_geom[wid] = coords
    if w["k"] != "admin" and any(in_bbox(*c) for c in coords):
        out_ways.append({"k": w["k"], "n": w["n"], "ref": w["ref"], "c": coords})

out_admin = []
for a in admin.values():
    out_admin.append({
        "name": a["name"],
        "level": a["level"],
        "lines": [admin_geom[w] for w in a["ways"] if w in admin_geom],
    })

with open(OUT, "w") as f:
    json.dump({"ways": out_ways, "admin": out_admin, "places": places}, f)
print("wrote", OUT, "ways:", len(out_ways))
