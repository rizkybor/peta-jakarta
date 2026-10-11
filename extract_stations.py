"""Extract railway stations (KRL Commuter Line / KAI, not MRT or LRT) around
Jakarta from a Java OSM extract into a compact JSON file.

Usage: python -I extract_stations.py <java.osm.pbf> <out.json>
"""
import json
import re
import sys

import osmium

PBF, OUT = sys.argv[1], sys.argv[2]

W, S, E, N = 106.66, -6.40, 107.00, -6.06
NOT_TRAIN = {"subway", "light_rail", "monorail", "tram", "funicular"}
# Long-distance terminals / major interchanges, drawn larger
MAJOR = {"Gambir", "Pasar Senen", "Jakarta Kota", "Manggarai", "Tanah Abang", "Jatinegara",
         "Sudirman", "Duri", "Kampung Bandan", "Tanjung Priuk", "BNI City", "Halim"}


def is_train_station(t):
    if t.get("railway") not in ("station", "halt"):
        return False
    if t.get("station") in NOT_TRAIN or t.get("subway") == "yes" or t.get("light_rail") == "yes":
        return False
    name = t.get("name", "")
    return bool(name) and not re.search(r"\b(MRT|LRT)\b", name)


def clean(name):
    return re.sub(r"^Stasiun\s+", "", name.strip(), flags=re.I)


found = []
for n in osmium.FileProcessor(PBF, osmium.osm.NODE):
    if is_train_station(n.tags):
        lon, lat = n.location.lon, n.location.lat
        if W <= lon <= E and S <= lat <= N:
            found.append((clean(n.tags["name"]), lon, lat))

# Stations mapped as areas: collect their node ids, then a second node pass
area_ways = {}
for w in osmium.FileProcessor(PBF, osmium.osm.WAY):
    if is_train_station(w.tags):
        area_ways[w.id] = (clean(w.tags["name"]), [n.ref for n in w.nodes])
if area_ways:
    needed = {n for _, ns in area_ways.values() for n in ns}
    loc = {}
    for n in osmium.FileProcessor(PBF, osmium.osm.NODE):
        if n.id in needed:
            loc[n.id] = (n.location.lon, n.location.lat)
    for name, ns in area_ways.values():
        pts = [loc[n] for n in ns if n in loc]
        if pts:
            lon = sum(p[0] for p in pts) / len(pts)
            lat = sum(p[1] for p in pts) / len(pts)
            if W <= lon <= E and S <= lat <= N:
                found.append((name, lon, lat))

# Merge duplicates: same name within ~500 m
stations = []
for name, lon, lat in found:
    for st in stations:
        if st["n"] == name and abs(st["c"][0] - lon) < 0.005 and abs(st["c"][1] - lat) < 0.005:
            break
    else:
        stations.append({"n": name, "c": [round(lon, 6), round(lat, 6)], "major": name in MAJOR})

with open(OUT, "w") as f:
    json.dump({"stations": stations}, f, ensure_ascii=False)
print("wrote", OUT, "stations:", len(stations))
print(sorted(s["n"] for s in stations))
