"""Extract the operating MRT Jakarta line and its stations
from a Java OSM extract into a compact JSON file.

Usage: python -I extract_mrt.py <java.osm.pbf> <out.json>
"""
import json
import re
import sys

import osmium

PBF, OUT = sys.argv[1], sys.argv[2]

# Pass 1: operating MRT route relations
line = {"name": "", "colour": "", "ways": set(), "stops": []}
for r in osmium.FileProcessor(PBF, osmium.osm.RELATION):
    t = r.tags
    if t.get("type") != "route" or t.get("route") != "subway":
        continue
    if t.get("network") != "MRT Jakarta" or t.get("proposed:railway"):
        continue
    line["colour"] = line["colour"] or t.get("colour", "#CE0037")
    line["name"] = line["name"] or "Lin Utara–Selatan"
    for m in r.members:
        if m.role.startswith(("platform", "stop")):
            line["stops"].append((m.type, m.ref))
        elif m.type == "w":
            line["ways"].add(m.ref)
print("route ways:", len(line["ways"]), "stops:", len(line["stops"]), flush=True)

stop_nodes = {ref for typ, ref in line["stops"] if typ == "n"}
stop_ways = {ref for typ, ref in line["stops"] if typ == "w"}

# Pass 2: way node lists (route + platforms)
way_nodes, way_names = {}, {}
for w in osmium.FileProcessor(PBF, osmium.osm.WAY):
    if w.id in line["ways"] or w.id in stop_ways:
        way_nodes[w.id] = [n.ref for n in w.nodes]
        way_names[w.id] = w.tags.get("name", "")
needed = {n for ns in way_nodes.values() for n in ns} | stop_nodes

# Pass 3: node locations + station names
loc, node_names = {}, {}
for n in osmium.FileProcessor(PBF, osmium.osm.NODE):
    if n.id in needed:
        loc[n.id] = (round(n.location.lon, 6), round(n.location.lat, 6))
        if n.id in stop_nodes:
            node_names[n.id] = n.tags.get("name", "")


def coords(wid):
    return [loc[n] for n in way_nodes.get(wid, []) if n in loc]


def clean_station(name):
    name = re.sub(r"^(Stasiun|Station)\s+(MRT\s+)?", "", name.strip(), flags=re.I)
    return re.sub(r"\s+MRT$", "", name).strip()


stations = {}
for typ, sid in line["stops"]:
    if typ == "n" and sid in loc:
        name, pt = node_names.get(sid, ""), loc[sid]
    elif typ == "w" and coords(sid):
        pts = coords(sid)
        name = way_names.get(sid, "")
        pt = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
    else:
        continue
    name = clean_station(name)
    if name:
        stations.setdefault(name, []).append(pt)

out = {
    "name": line["name"],
    "colour": line["colour"],
    "lines": [c for w in line["ways"] if len(c := coords(w)) > 1],
    "stations": [
        {"n": name, "c": [round(sum(p[0] for p in pts) / len(pts), 6),
                          round(sum(p[1] for p in pts) / len(pts), 6)]}
        for name, pts in stations.items()
    ],
}
with open(OUT, "w") as f:
    json.dump(out, f, ensure_ascii=False)
print("wrote", OUT, "lines:", len(out["lines"]), "stations:", [s["n"] for s in out["stations"]])
