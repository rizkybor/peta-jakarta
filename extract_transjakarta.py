"""Extract TransJakarta BRT corridors (Koridor 1-14) and their halte from a
Java OSM extract into a compact JSON file.

Usage: python -I extract_transjakarta.py <java.osm.pbf> <out.json>
"""
import json
import re
import sys
from collections import defaultdict

import osmium

PBF, OUT = sys.argv[1], sys.argv[2]

CORRIDORS = {str(i) for i in range(1, 15)}

# Pass 1: route relations of the main corridors
routes = defaultdict(lambda: {"name": "", "colour": "", "ways": set(), "stops": []})
for r in osmium.FileProcessor(PBF, osmium.osm.RELATION):
    t = r.tags
    if t.get("type") != "route" or t.get("route") != "bus":
        continue
    if "transjakarta" not in t.get("name", "").lower() + t.get("network", "").lower():
        continue
    ref = t.get("ref", "")
    if ref not in CORRIDORS:
        continue
    rt = routes[ref]
    rt["colour"] = rt["colour"] or t.get("colour", "")
    if not rt["name"]:
        # "Transjakarta BRT 1: Blok M → Kali Besar" -> "Blok M – Kali Besar"
        rt["name"] = re.sub(r"\s*→\s*", " – ", t.get("name", "").split(":", 1)[-1].strip())
    for m in r.members:
        if m.type == "w" and not m.role.startswith(("platform", "stop")):
            rt["ways"].add(m.ref)
        elif m.role.startswith(("platform", "stop")):
            rt["stops"].append((m.type, m.ref))
print("corridors:", sorted(routes, key=int), flush=True)

stop_nodes = {ref for rt in routes.values() for typ, ref in rt["stops"] if typ == "n"}
stop_ways = {ref for rt in routes.values() for typ, ref in rt["stops"] if typ == "w"}
route_ways = {w for rt in routes.values() for w in rt["ways"]}

# Pass 2: way node lists (route geometry + platform ways)
way_nodes = {}
way_names = {}
for w in osmium.FileProcessor(PBF, osmium.osm.WAY):
    if w.id in route_ways or w.id in stop_ways:
        way_nodes[w.id] = [n.ref for n in w.nodes]
        if w.id in stop_ways:
            way_names[w.id] = w.tags.get("name", "")
needed = {n for ns in way_nodes.values() for n in ns} | stop_nodes

# Pass 3: node locations + stop names
loc, node_names = {}, {}
for n in osmium.FileProcessor(PBF, osmium.osm.NODE):
    if n.id in needed:
        loc[n.id] = (round(n.location.lon, 6), round(n.location.lat, 6))
        if n.id in stop_nodes:
            node_names[n.id] = n.tags.get("name", "")


def clean_halte(name):
    name = re.sub(r"^(Halte|Halte Transjakarta|Halte TJ|Shelter)\s+", "", name.strip(), flags=re.I)
    name = re.sub(r"\s*\((arah|ke|menuju)\b[^)]*\)$", "", name, flags=re.I)
    return re.sub(r"\s+Arah\s+\w+$", "", name, flags=re.I).strip()


out_routes = []
halte = {}  # cleaned name -> {"pts": [...], "refs": set()}
for ref in sorted(routes, key=int):
    rt = routes[ref]
    lines = []
    for wid in rt["ways"]:
        coords = [loc[n] for n in way_nodes.get(wid, []) if n in loc]
        if len(coords) > 1:
            lines.append(coords)
    out_routes.append({"ref": ref, "name": rt["name"], "colour": rt["colour"] or "#c0392b",
                       "lines": lines})
    for typ, sid in rt["stops"]:
        if typ == "n" and sid in loc:
            name, pt = node_names.get(sid, ""), loc[sid]
        elif typ == "w" and sid in way_nodes:
            pts = [loc[n] for n in way_nodes[sid] if n in loc]
            if not pts:
                continue
            name = way_names.get(sid, "")
            pt = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
        else:
            continue
        name = clean_halte(name) or f"?{sid}"
        h = halte.setdefault(name, {"pts": [], "refs": set()})
        h["pts"].append(pt)
        h["refs"].add(ref)

out_halte = []
for name, h in halte.items():
    xs, ys = zip(*h["pts"])
    out_halte.append({
        "n": "" if name.startswith("?") else name,
        "c": [round(sum(xs) / len(xs), 6), round(sum(ys) / len(ys), 6)],
        "refs": sorted(h["refs"], key=int),
    })

with open(OUT, "w") as f:
    json.dump({"routes": out_routes, "halte": out_halte}, f, ensure_ascii=False)
print("wrote", OUT, "routes:", len(out_routes), "halte:", len(out_halte))
for r in out_routes:
    print(f"  {r['ref']:>2} {r['colour']} {r['name']} ({len(r['lines'])} ways)")
