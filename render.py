"""Render an A3 landscape road map of DKI Jakarta from extract.py output.

Usage: python -I render.py <jakarta.json> <out_prefix>
                           [--transjakarta transjakarta.json] [--mrt mrt.json]
                           [--stations stations.json]
Writes <out_prefix>.pdf (vector) and <out_prefix>.png (300 dpi preview).
--transjakarta (from extract_transjakarta.py) highlights the BRT corridors and
halte; --mrt (from extract_mrt.py) adds the MRT Jakarta line and stations;
--stations (from extract_stations.py) adds KRL / KAI railway stations.
"""
import argparse
import json
import math
from collections import defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
from matplotlib.transforms import offset_copy
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D
from matplotlib.patches import Polygon as MplPolygon, Rectangle
from shapely.geometry import LineString, Point, box
from shapely.ops import linemerge, polygonize, split, unary_union

ap = argparse.ArgumentParser()
ap.add_argument("src")
ap.add_argument("prefix")
ap.add_argument("--transjakarta")
ap.add_argument("--mrt")
ap.add_argument("--stations")
args = ap.parse_args()
PREFIX = args.prefix
data = json.load(open(args.src))
tj = json.load(open(args.transjakarta)) if args.transjakarta else None
mrt = json.load(open(args.mrt)) if args.mrt else None
krl = json.load(open(args.stations))["stations"] if args.stations else None
KRL_COLOUR = "#3b3b3b"
TJ_BLUE = "#1f3b70"

# Map extent (mainland Jakarta + small margin). The latitude span is chosen so
# the 277 mm map height prints at exactly 1:SCALE on A3.
SCALE = 125_000
M_PER_DEG_LAT = 110_574
MAP_H_MM = 297 - 20
LAT_C, LAT_SPAN = -6.23, MAP_H_MM / 1000 * SCALE / M_PER_DEG_LAT
W, E = 106.675, 106.985
S, N = LAT_C - LAT_SPAN / 2, LAT_C + LAT_SPAN / 2
LAT0 = math.radians(LAT_C)
ASPECT = 1 / math.cos(LAT0)

MM = 1 / 25.4
FIG_W, FIG_H = 420 * MM, 297 * MM

C = {
    "bg": "#ecebe6",
    "sea": "#bcd6e6",
    "coast": "#7aa6c2",
    "river": "#8cb8d6",
    "border": "#6d6a75",
    "text": "#2b2a2e",
    "muted": "#6b6a70",
}
KOTA_FILL = {
    "Jakarta Pusat": "#f6e3d3",
    "Jakarta Utara": "#dbe8f1",
    "Jakarta Barat": "#e5eedb",
    "Jakarta Selatan": "#f1e2ec",
    "Jakarta Timur": "#f3efd6",
}
# (casing colour, fill colour, casing width, fill width, zorder)
ROAD = {
    "tertiary":       ("#c9c6bd", "#ffffff", 0.75, 0.45, 3),
    "secondary_link": ("#b9a86a", "#fff6c4", 0.9, 0.55, 4),
    "secondary":      ("#b9a86a", "#fff6c4", 1.35, 0.95, 4),
    "primary_link":   ("#c79a3e", "#fde08a", 1.0, 0.65, 5),
    "primary":        ("#c79a3e", "#fde08a", 1.8, 1.3, 5),
    "trunk_link":     ("#c4703a", "#f7b26d", 1.1, 0.7, 6),
    "trunk":          ("#c4703a", "#f7b26d", 2.2, 1.6, 6),
    "motorway_link":  ("#a83a32", "#e8786b", 1.2, 0.8, 7),
    "motorway":       ("#a83a32", "#e8786b", 2.8, 2.0, 7),
}


def rings_to_polys(lines):
    merged = linemerge([LineString(l) for l in lines if len(l) > 1])
    return list(polygonize(merged))


fig = plt.figure(figsize=(FIG_W, FIG_H), dpi=100)
fig.patch.set_facecolor("white")

# Map frame: left part of the sheet, sidebar on the right
margin = 10 * MM / FIG_W
map_h = (297 - 20) / 297
map_w_mm = (297 - 20) * (E - W) / ((N - S) * ASPECT)
ax = fig.add_axes([margin, 10 / 297, map_w_mm / 420, map_h])
ax.set_xlim(W, E)
ax.set_ylim(S, N)
ax.set_aspect(ASPECT)
ax.set_facecolor(C["bg"])
ax.set_xticks([])
ax.set_yticks([])
for sp in ax.spines.values():
    sp.set_color(C["text"])
    sp.set_linewidth(1.0)
frame = box(W, S, E, N)

# --- Sea (split frame by coastline, keep the piece containing a sea point)
coast = [w["c"] for w in data["ways"] if w["k"] == "coast"]
if coast:
    cl = unary_union([LineString(c) for c in coast]).intersection(frame.buffer(0.02))
    try:
        pieces = split(frame, cl)
        sea_pt = Point(106.83, -6.08)
        for g in pieces.geoms:
            if g.contains(sea_pt):
                ax.add_patch(MplPolygon(list(g.exterior.coords), closed=True,
                                        fc=C["sea"], ec="none", zorder=0.5))
    except Exception as e:
        print("sea split failed:", e)
    ax.add_collection(LineCollection(coast, colors=C["coast"], linewidths=0.8, zorder=1.2))

# --- Kota fills + borders
kota_polys = {}
for a in data["admin"]:
    if a["level"] == "5" and a["name"] in KOTA_FILL:
        polys = rings_to_polys(a["lines"])
        if polys:
            kota_polys[a["name"]] = unary_union(polys)
for name, geom in kota_polys.items():
    for p in getattr(geom, "geoms", [geom]):
        ax.add_patch(MplPolygon(list(p.exterior.coords), closed=True,
                                fc=KOTA_FILL[name], ec="none", zorder=1))
for a in data["admin"]:
    if a["level"] == "5" and a["name"] in KOTA_FILL:
        ax.add_collection(LineCollection(a["lines"], colors=C["border"], linewidths=0.6,
                                         linestyles=(0, (4, 2)), zorder=2))
    if a["level"] == "4":
        ax.add_collection(LineCollection(a["lines"], colors=C["border"], linewidths=1.6,
                                         linestyles=(0, (6, 2, 1.5, 2)), zorder=2.1))

# --- Rivers
rivers = [w["c"] for w in data["ways"] if w["k"] == "river"]
ax.add_collection(LineCollection(rivers, colors=C["river"], linewidths=0.6, zorder=2.2))

# --- Railways (black/white dashed)
rail = [w["c"] for w in data["ways"] if w["k"] == "rail"]
ax.add_collection(LineCollection(rail, colors="#555555", linewidths=1.2, zorder=8))
ax.add_collection(LineCollection(rail, colors="white", linewidths=0.6,
                                 linestyles=(0, (3, 3)), zorder=8.1))

# --- Roads: casing pass then fill pass, by class
by_kind = defaultdict(list)
for w in data["ways"]:
    if w["k"] in ROAD:
        by_kind[w["k"]].append(w["c"])
for k, (case, fill, cw, fw, z) in ROAD.items():
    ax.add_collection(LineCollection(by_kind[k], colors=case, linewidths=cw,
                                     capstyle="round", joinstyle="round", zorder=z))
for k, (case, fill, cw, fw, z) in ROAD.items():
    ax.add_collection(LineCollection(by_kind[k], colors=fill, linewidths=fw,
                                     capstyle="round", joinstyle="round", zorder=z + 0.5))

# --- TransJakarta BRT corridors (white casing, then corridor colour) and halte
if tj:
    for r in reversed(tj["routes"]):
        ax.add_collection(LineCollection(r["lines"], colors="white", linewidths=3.4,
                                         capstyle="round", joinstyle="round", zorder=9))
    for r in reversed(tj["routes"]):
        ax.add_collection(LineCollection(r["lines"], colors=r["colour"], linewidths=2.1,
                                         capstyle="round", joinstyle="round", zorder=9.5))
    single = [h["c"] for h in tj["halte"] if len(h["refs"]) == 1]
    multi = [h["c"] for h in tj["halte"] if len(h["refs"]) > 1]
    if single:
        ax.scatter(*zip(*single), s=7, c="white", edgecolors=TJ_BLUE, linewidths=0.6, zorder=12)
    if multi:
        ax.scatter(*zip(*multi), s=16, c="white", edgecolors="black", linewidths=1.0, zorder=12.1)

# --- MRT Jakarta: line (white casing + line colour) and stations
if mrt:
    ax.add_collection(LineCollection(mrt["lines"], colors="white", linewidths=5.2,
                                     capstyle="round", joinstyle="round", zorder=10.4))
    ax.add_collection(LineCollection(mrt["lines"], colors=mrt["colour"], linewidths=3.4,
                                     capstyle="round", joinstyle="round", zorder=10.5))
    ax.scatter(*zip(*[st["c"] for st in mrt["stations"]]), marker="s", s=24, c="white",
               edgecolors=mrt["colour"], linewidths=1.5, zorder=13)

# --- Railway stations (KRL / KAI): dark disc with white ring, larger for terminals
if krl:
    for major, size in ((False, 20), (True, 42)):
        pts = [st["c"] for st in krl if st["major"] == major]
        if pts:
            ax.scatter(*zip(*pts), s=size, c=KRL_COLOUR, edgecolors="white",
                       linewidths=1.0, zorder=12.5)

# --- Labels with simple greedy collision avoidance (in display space)
fig.canvas.draw()
renderer = fig.canvas.get_renderer()
placed = []


def try_label(x, y, text, rot=0, size=5, color=C["text"], weight="normal",
              halo=1.6, z=20, style="normal", pad=2, ha="center", va="center",
              dx=0, dy=0, bbox=None):
    if not (W < x < E and S < y < N):
        return False
    tr = offset_copy(ax.transData, fig=fig, x=dx, y=dy, units="points")
    t = ax.text(x, y, text, fontsize=size, color=color, weight=weight, style=style,
                rotation=rot, rotation_mode="anchor", ha=ha, va=va, transform=tr, bbox=bbox,
                zorder=z, path_effects=[pe.withStroke(linewidth=halo, foreground="white")])
    bb = t.get_window_extent(renderer).expanded(1, 1).padded(pad)
    ab = ax.get_window_extent(renderer)
    if (bb.x0 < ab.x0 or bb.x1 > ab.x1 or bb.y0 < ab.y0 or bb.y1 > ab.y1
            or any(bb.overlaps(o) for o in placed)):
        t.remove()
        return False
    placed.append(bb)
    return True


# Kota names first (biggest)
for name, geom in kota_polys.items():
    p = geom.representative_point()
    try_label(p.x, p.y, name.upper(), size=11, color="#8a8790", weight="bold",
              halo=2.5, z=19, pad=0)

# Road names: merge segments by (class, name), label longest pieces
def short_name(name):
    for full, short in (("Jalan Tol ", "Tol "), ("Jalan Raya ", "Jl. Raya "), ("Jalan ", "Jl. ")):
        if name.startswith(full):
            return short + name[len(full):]
    return name


PRIORITY = ["motorway", "trunk", "primary", "secondary"]
groups = defaultdict(list)
for w in data["ways"]:
    if w["k"] in PRIORITY and w["n"]:
        groups[(w["k"], w["n"])].append(LineString(w["c"]))
font = {"motorway": 5.6, "trunk": 5.3, "primary": 5.0, "secondary": 4.4}
min_len = {"motorway": 0.012, "trunk": 0.010, "primary": 0.009, "secondary": 0.010}
seen_names = defaultdict(list)


def label_roads(classes):
    for k in classes:
        items = []
        for (kk, name), segs in groups.items():
            if kk != k:
                continue
            m = linemerge(segs)
            for ln in getattr(m, "geoms", [m]):
                if ln.length >= min_len[k]:
                    items.append((ln.length, name, ln))
        items.sort(reverse=True)
        for length, name, ln in items:
            # keep the same name from repeating too close together
            mid = ln.interpolate(0.5, normalized=True)
            if any(mid.distance(p) < 0.04 for p in seen_names[name]):
                continue
            for frac in (0.5, 0.35, 0.65, 0.2, 0.8):
                pt = ln.interpolate(frac, normalized=True)
                a = ln.interpolate(max(frac - 0.02, 0), normalized=True)
                b = ln.interpolate(min(frac + 0.02, 1), normalized=True)
                ang = math.degrees(math.atan2((b.y - a.y) * ASPECT, b.x - a.x))
                if ang > 90:
                    ang -= 180
                elif ang < -90:
                    ang += 180
                label = short_name(name)
                if try_label(pt.x, pt.y, label, rot=ang, size=font[k],
                             weight="bold" if k in ("motorway", "trunk") else "normal",
                             color="#7a2620" if k == "motorway" else C["text"]):
                    seen_names[name].append(pt)
                    break


# Halte dots are obstacles for every label placed after this point
def reserve_points(pts, radius_px):
    from matplotlib.transforms import Bbox
    for x, y in pts:
        px, py = ax.transData.transform((x, y))
        placed.append(Bbox([[px - radius_px, py - radius_px], [px + radius_px, py + radius_px]]))


# Scale panel (bottom-left) is drawn later; keep labels out of it
PANEL = (W + 0.004, S + 0.004, W + 0.068, S + 0.027)
from matplotlib.transforms import Bbox as _Bbox
placed.append(_Bbox([ax.transData.transform(PANEL[:2]), ax.transData.transform(PANEL[2:])]))

POSITIONS = (("left", "center", 4.5, 0), ("right", "center", -4.5, 0),
             ("center", "bottom", 0, 4), ("center", "top", 0, -4),
             ("left", "bottom", 3.5, 3), ("left", "top", 3.5, -3),
             ("right", "bottom", -3.5, 3), ("right", "top", -3.5, -3))
if mrt:
    reserve_points([st["c"] for st in mrt["stations"]], 4)
    for st in mrt["stations"]:
        for ha, va, dx, dy in POSITIONS:
            if try_label(st["c"][0], st["c"][1], st["n"], size=4.8, color=mrt["colour"],
                         weight="bold", halo=1.6, z=23, pad=0.5, ha=ha, va=va, dx=dx, dy=dy):
                break
if krl:
    reserve_points([st["c"] for st in krl], 4)
    for st in sorted(krl, key=lambda st: not st["major"]):
        for ha, va, dx, dy in POSITIONS:
            if try_label(st["c"][0], st["c"][1], "St. " + st["n"],
                         size=5.0 if st["major"] else 4.3, color=KRL_COLOUR, weight="bold",
                         halo=1.5, z=22.5, pad=0.5, ha=ha, va=va, dx=dx, dy=dy):
                break
        else:
            if W < st["c"][0] < E and S < st["c"][1] < N:
                print("station label skipped:", st["n"])
label_roads(["motorway"])
if tj:
    reserve_points([h["c"] for h in tj["halte"]], 3)
    # Corridor number badges along each corridor
    for r in tj["routes"]:
        m = linemerge([LineString(l) for l in r["lines"]])
        parts = sorted(getattr(m, "geoms", [m]), key=lambda g: -g.length)
        done = 0
        for ln in parts[:4]:
            for frac in (0.5, 0.3, 0.7, 0.15, 0.85):
                pt = ln.interpolate(frac, normalized=True)
                if try_label(pt.x, pt.y, r["ref"], size=5.5, color="white", weight="bold",
                             halo=0, z=22, pad=3,
                             bbox=dict(boxstyle="round,pad=0.25", fc=r["colour"], ec="white", lw=0.6)):
                    done += 1
                    break
            if done >= 2:
                break
    # Halte names: interchanges first, then the rest
    for h in sorted(tj["halte"], key=lambda h: -len(h["refs"])):
        if not h["n"]:
            continue
        big = len(h["refs"]) > 1
        for ha, va, dx, dy in (("left", "center", 3.5, 0), ("right", "center", -3.5, 0),
                               ("center", "bottom", 0, 3), ("center", "top", 0, -3)):
            if try_label(h["c"][0], h["c"][1], h["n"], size=4.3 if big else 3.7,
                         color=TJ_BLUE, weight="bold" if big else "normal", halo=1.3,
                         z=21, pad=0.5, ha=ha, va=va, dx=dx, dy=dy):
                break
label_roads(["trunk", "primary", "secondary"])

# Place names (districts / neighbourhoods)
for t, size in (("city_district", 6.2), ("suburb", 4.8), ("quarter", 4.2)):
    for p in data["places"]:
        if p["t"] == t:
            try_label(p["c"][0], p["c"][1], p["n"], size=size, color=C["muted"],
                      style="italic", z=18)

# --- Grid references along the frame
ncol, nrow = 8, 8
for i in range(ncol + 1):
    x = W + (E - W) * i / ncol
    ax.axvline(x, color="#00000014", lw=0.4, zorder=30)
for j in range(nrow + 1):
    y = S + (N - S) * j / nrow
    ax.axhline(y, color="#00000014", lw=0.4, zorder=30)
for i in range(ncol):
    x = W + (E - W) * (i + 0.5) / ncol
    for yy, va in ((N, "bottom"), (S, "top")):
        ax.text(x, yy + (0.0012 if va == "bottom" else -0.0012), chr(65 + i),
                ha="center", va=va, fontsize=7, color=C["text"], zorder=31, clip_on=False)
for j in range(nrow):
    y = N - (N - S) * (j + 0.5) / nrow
    for xx, ha in ((W, "right"), (E, "left")):
        ax.text(xx + (-0.0012 if ha == "right" else 0.0012), y, str(j + 1),
                ha=ha, va="center", fontsize=7, color=C["text"], zorder=31, clip_on=False)

# --- Scale panel (numeric scale + 5 km bar) and north arrow
scale_txt = f"{SCALE:,}".replace(",", ".")
km_per_cm = f"{SCALE / 100_000:g}".replace(".", ",")
px0, py0, px1, py1 = PANEL
ax.add_patch(Rectangle((px0, py0), px1 - px0, py1 - py0, fc="white", ec=C["text"],
                       lw=0.6, alpha=0.95, zorder=32))
ax.text(px0 + 0.003, py1 - 0.0028, f"SKALA 1 : {scale_txt}", ha="left", va="top",
        fontsize=8, weight="bold", color=C["text"], zorder=33)
km_per_deg_lon = 111.32 * math.cos(LAT0)
seg = 1 / km_per_deg_lon
bx, by = px0 + 0.004, py0 + 0.0085
for i in range(5):
    ax.add_patch(Rectangle((bx + i * seg, by), seg, 0.0013,
                           fc=C["text"] if i % 2 == 0 else "white", ec=C["text"], lw=0.5, zorder=33))
for i in range(6):
    ax.text(bx + i * seg, by + 0.0021, str(i), ha="center", va="bottom", fontsize=6,
            color=C["text"], zorder=33)
ax.text(bx + 5 * seg + 0.0018, by + 0.00065, "km", ha="left", va="center", fontsize=6,
        color=C["text"], zorder=33)
ax.text(px0 + 0.003, py0 + 0.0028, f"1 cm di peta = {km_per_cm} km di lapangan",
        ha="left", va="bottom", fontsize=6.3, color=C["muted"], zorder=33)
nx, ny = E - 0.012, N - 0.022
ax.annotate("", xy=(nx, ny + 0.012), xytext=(nx, ny), zorder=32,
            arrowprops=dict(arrowstyle="-|>,head_width=0.35,head_length=0.8", lw=1.2, color=C["text"]))
ax.text(nx, ny + 0.0135, "U", ha="center", va="bottom", fontsize=9, weight="bold", zorder=32,
        path_effects=[pe.withStroke(linewidth=2, foreground="white")])

# --- Sidebar
sx0 = margin + map_w_mm / 420 + 8 / 420
side = fig.add_axes([sx0, 10 / 297, 1 - sx0 - margin, map_h])
side.axis("off")
side.set_xlim(0, 1)
side.set_ylim(0, 1)
title = "PETA JALAN" + (", BUSWAY & MRT" if tj and mrt else " & BUSWAY" if tj
                        else " & MRT" if mrt else " RAYA")
if krl and (tj or mrt):
    title = "PETA JALAN & TRANSPORTASI"
side.text(0, 0.985, title, fontsize=19, weight="bold", color=C["text"], va="top")
side.text(0, 0.935, "DKI JAKARTA", fontsize=26, weight="bold", color="#a83a32", va="top")
subtitle = "Jaringan jalan tol, arteri, kolektor & rel kereta"
if tj or mrt or krl:
    subtitle = ("Jalan, kereta api" + (", busway TransJakarta" if tj else "")
                + (" & MRT Jakarta" if mrt else ""))
side.text(0, 0.872, subtitle, fontsize=8.5, color=C["muted"], va="top")
side.plot([0, 1], [0.85, 0.85], color=C["text"], lw=0.8)

# Tighter legend rows as more transit layers are added
ROW = (0.036, 0.031, 0.027, 0.026)[(tj is not None) + (mrt is not None) + (krl is not None)]
y = 0.815
side.text(0, y, "LEGENDA", fontsize=10, weight="bold", va="top")
y -= 0.042
if mrt:
    side.add_line(Line2D([0, 0.16], [y, y], color=mrt["colour"], lw=5, solid_capstyle="butt"))
    side.scatter([0.08], [y], marker="s", s=40, c="white", edgecolors=mrt["colour"], linewidths=1.6,
                 zorder=5)
    side.text(0.21, y, "Jalur & stasiun MRT Jakarta", fontsize=8.5, va="center")
    y -= ROW
if tj:
    for i, r in enumerate(tj["routes"][:4]):
        x0 = i * 0.04
        side.add_line(Line2D([x0, x0 + 0.04], [y, y], color=r["colour"], lw=4.2, solid_capstyle="butt"))
    side.text(0.21, y, "Koridor busway TransJakarta (BRT)", fontsize=8.5, va="center")
    y -= ROW
    side.scatter([0.08], [y], s=16, c="white", edgecolors=TJ_BLUE, linewidths=0.8)
    side.text(0.21, y, "Halte busway", fontsize=8.5, va="center")
    y -= ROW
    side.scatter([0.08], [y], s=34, c="white", edgecolors="black", linewidths=1.3)
    side.text(0.21, y, "Halte transit (antarkoridor)", fontsize=8.5, va="center")
    y -= ROW
legend_rows = [
    ("motorway", "Jalan tol"),
    ("trunk", "Jalan arteri utama"),
    ("primary", "Jalan arteri / primer"),
    ("secondary", "Jalan kolektor / sekunder"),
    ("tertiary", "Jalan lokal / tersier"),
]
for k, label in legend_rows:
    case, fill, cw, fw, _ = ROAD[k]
    side.add_line(Line2D([0, 0.16], [y, y], color=case, lw=cw * 2.2, solid_capstyle="butt"))
    side.add_line(Line2D([0, 0.16], [y, y], color=fill, lw=fw * 2.2, solid_capstyle="butt"))
    side.text(0.21, y, label, fontsize=8.5, va="center")
    y -= ROW
side.add_line(Line2D([0, 0.16], [y, y], color="#555555", lw=2.6))
side.add_line(Line2D([0, 0.16], [y, y], color="white", lw=1.3, linestyle=(0, (3, 3))))
side.text(0.21, y, "Rel kereta api (KRL / KA)", fontsize=8.5, va="center")
y -= ROW
if krl:
    side.scatter([0.05], [y], s=22, c=KRL_COLOUR, edgecolors="white", linewidths=1.0, zorder=5)
    side.scatter([0.11], [y], s=46, c=KRL_COLOUR, edgecolors="white", linewidths=1.0, zorder=5)
    side.text(0.21, y, "Stasiun kereta api (kecil: KRL, besar: utama)", fontsize=8.5, va="center")
    y -= ROW
side.add_line(Line2D([0, 0.16], [y, y], color=C["river"], lw=1.4))
side.text(0.21, y, "Sungai / kanal", fontsize=8.5, va="center")
y -= ROW
side.add_line(Line2D([0, 0.16], [y, y], color=C["border"], lw=2.2, linestyle=(0, (6, 2, 1.5, 2))))
side.text(0.21, y, "Batas provinsi", fontsize=8.5, va="center")
y -= ROW
side.add_line(Line2D([0, 0.16], [y, y], color=C["border"], lw=1.0, linestyle=(0, (4, 2))))
side.text(0.21, y, "Batas kota administrasi", fontsize=8.5, va="center")
y -= ROW
side.add_patch(Rectangle((0, y - 0.012), 0.16, 0.024, fc=C["sea"], ec="none"))
side.text(0.21, y, "Laut (Teluk Jakarta)", fontsize=8.5, va="center")

y -= 0.045
side.plot([0, 1], [y + 0.02, y + 0.02], color=C["text"], lw=0.5)
if tj:
    side.text(0, y, "KORIDOR TRANSJAKARTA (BRT)", fontsize=10, weight="bold", va="top")
    y -= 0.04
    half = (len(tj["routes"]) + 1) // 2
    step = min(0.03, ROW)
    for i, r in enumerate(tj["routes"]):
        col, row = divmod(i, half)
        x0, yy = col * 0.52, y - row * step
        side.text(x0 + 0.025, yy, r["ref"], fontsize=6.5, color="white", weight="bold",
                  ha="center", va="center",
                  bbox=dict(boxstyle="round,pad=0.3", fc=r["colour"], ec="none"))
        side.text(x0 + 0.065, yy, r["name"], fontsize=6.6, va="center")
    y -= half * step
else:
    side.text(0, y, "KOTA ADMINISTRASI", fontsize=10, weight="bold", va="top")
    y -= 0.045
    for name, fc in KOTA_FILL.items():
        side.add_patch(Rectangle((0, y - 0.012), 0.16, 0.024, fc=fc, ec=C["border"], lw=0.4))
        side.text(0.21, y, name, fontsize=8.5, va="center")
        y -= ROW

side.text(0, 0.045, f"Skala 1 : {scale_txt} bila dicetak A3 (420 × 297 mm) ukuran asli\n"
                    "Grid A–H / 1–8 · Kep. Seribu di luar cakupan peta",
          fontsize=7, color=C["muted"], va="bottom", linespacing=1.5)
side.text(0, 0.0, "Data peta © kontributor OpenStreetMap (ODbL)\nopenstreetmap.org/copyright",
          fontsize=7, color=C["muted"], va="bottom", linespacing=1.5)

fig.savefig(PREFIX + ".pdf")
fig.savefig(PREFIX + ".png", dpi=300)
print("saved", PREFIX + ".pdf", PREFIX + ".png", "labels:", len(placed))
