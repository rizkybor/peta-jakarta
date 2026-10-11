"""Extract land cover areas (parks, open land, vegetation, water bodies,
industrial / restricted land) around Jakarta from a Java OSM extract into a
compact JSON file, for the orienteering-style map.

Usage: python -I extract_landcover.py <java.osm.pbf> <out.json>
"""
import json
import sys
from array import array

import numpy as np
import osmium
from shapely.geometry import LineString, Polygon, box
from shapely.ops import linemerge, polygonize, unary_union

PBF, OUT = sys.argv[1], sys.argv[2]

W, S, E, N = 106.66, -6.40, 107.00, -6.06
MIN_AREA = 1.5e-6   # deg² (~ 1.8 ha); smaller areas are invisible at 1:125.000
SIMPLIFY = 0.00012  # deg (~ 13 m)


def category(t):
    lu, nat, lei = t.get("landuse"), t.get("natural"), t.get("leisure")
    if nat == "water" or lu in ("reservoir", "basin") or t.get("waterway") == "riverbank":
        return "water"
    if lu == "forest" or nat == "wood":
        return "forest"
    if nat == "scrub" or lu in ("orchard", "plant_nursery"):
        return "scrub"
    if lei in ("park", "golf_course", "garden", "recreation_ground") or lu in (
            "grass", "recreation_ground", "village_green", "cemetery") or t.get("amenity") == "grave_yard":
        return "open"
    if lu in ("farmland", "meadow", "farmyard") or nat in ("grassland", "wetland") \
            or t.get("aeroway") == "aerodrome":
        return "rough"
    if lu in ("industrial", "military", "port", "railway"):
        return "oob"
    return None


# Pass 1: node ids inside the bbox (sorted numpy array for fast lookups)
ids = array("q")
for n in osmium.FileProcessor(PBF, osmium.osm.NODE):
    lon, lat = n.location.lon, n.location.lat
    if W <= lon <= E and S <= lat <= N:
        ids.append(n.id)
bbox_ids = np.sort(np.frombuffer(ids, dtype=np.int64))
del ids
print("nodes in bbox:", len(bbox_ids), flush=True)


def touches_bbox(node_ids):
    a = np.fromiter(node_ids, dtype=np.int64)
    pos = np.searchsorted(bbox_ids, a).clip(0, len(bbox_ids) - 1)
    return bool((bbox_ids[pos] == a).any())


# Pass 2: multipolygon relations (outer members only)
rels = {}
for r in osmium.FileProcessor(PBF, osmium.osm.RELATION):
    if r.tags.get("type") != "multipolygon":
        continue
    cat = category(r.tags)
    if cat:
        rels[r.id] = (cat, [m.ref for m in r.members if m.type == "w" and m.role in ("outer", "")])
member_ids = {w for _, ws in rels.values() for w in ws}
print("multipolygon relations:", len(rels), flush=True)

# Pass 3: closed tagged ways + relation member ways that touch the bbox
ways = {}
for w in osmium.FileProcessor(PBF, osmium.osm.WAY):
    nodes = [n.ref for n in w.nodes]
    if len(nodes) < 2:
        continue
    cat = category(w.tags) if nodes[0] == nodes[-1] else None
    if (cat or w.id in member_ids) and touches_bbox(nodes):
        ways[w.id] = (cat, nodes)
needed = {n for _, ns in ways.values() for n in ns}
print("candidate ways:", len(ways), "nodes needed:", len(needed), flush=True)

# Pass 4: node locations
loc = {}
for n in osmium.FileProcessor(PBF, osmium.osm.NODE):
    if n.id in needed:
        loc[n.id] = (n.location.lon, n.location.lat)

frame = box(W, S, E, N)
areas = []


def add(cat, geom):
    geom = geom.buffer(0).intersection(frame)
    for p in getattr(geom, "geoms", [geom]):
        if p.geom_type == "Polygon" and p.area >= MIN_AREA:
            p = p.simplify(SIMPLIFY)
            areas.append({"k": cat, "c": [[round(x, 5), round(y, 5)] for x, y in p.exterior.coords]})


for wid, (cat, nodes) in ways.items():
    coords = [loc[n] for n in nodes if n in loc]
    if cat and len(coords) >= 4:
        add(cat, Polygon(coords))
for cat, members in rels.values():
    lines = [LineString([loc[n] for n in ways[w][1] if n in loc]) for w in members
             if w in ways and len(ways[w][1]) > 1]
    if lines:
        polys = list(polygonize(linemerge(lines)))
        if polys:
            add(cat, unary_union(polys))

with open(OUT, "w") as f:
    json.dump({"areas": areas}, f)
counts = {}
for a in areas:
    counts[a["k"]] = counts.get(a["k"], 0) + 1
print("wrote", OUT, "areas:", counts)
