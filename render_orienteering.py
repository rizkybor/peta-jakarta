"""Render an A3 landscape orienteering-style map of DKI Jakarta, using ISOM 2017
colours and symbols the way OCAD / OpenOrienteering Mapper draw them.

Usage: python -I render_orienteering.py <jakarta.json> <out_prefix>
                                        [--landcover landcover.json]
                                        [--stations stations.json]
                                        [--transjakarta transjakarta.json] [--mrt mrt.json]
                                        [--scale 100000] [--rail-symbol]
Writes <out_prefix>.pdf (vector) and <out_prefix>.png (300 dpi preview).
--landcover (from extract_landcover.py) adds open land, vegetation, water and
restricted areas; --stations (from extract_stations.py) adds KRL / KAI railway stations.
--transjakarta / --mrt highlight the busway corridors and MRT line on top of the
orienteering base, drawn bold like render.py --style transit (rail too).
--scale (default 125000) sets the print scale on A3; at larger scales such as
1:100.000 the map frame widens to 296 mm and the edges of Jakarta are cropped.
--rail-symbol keeps the railway track symbol (line with cross ticks) when the
transit layers are on, drawn bold with a white casing.
"""
import argparse
import json
import math
from collections import defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection, PatchCollection
from matplotlib.lines import Line2D
from matplotlib.patches import Polygon as MplPolygon, Rectangle
from matplotlib.transforms import Bbox, offset_copy
from shapely.geometry import LineString, Point, box
from shapely.ops import linemerge, polygonize, split, unary_union

ap = argparse.ArgumentParser()
ap.add_argument("src")
ap.add_argument("prefix")
ap.add_argument("--landcover")
ap.add_argument("--stations")
ap.add_argument("--transjakarta")
ap.add_argument("--mrt")
ap.add_argument("--scale", type=int, default=125_000)
ap.add_argument("--rail-symbol", action="store_true")
args = ap.parse_args()
PREFIX = args.prefix
data = json.load(open(args.src))
lc = json.load(open(args.landcover))["areas"] if args.landcover else []
krl = json.load(open(args.stations))["stations"] if args.stations else None
tj = json.load(open(args.transjakarta)) if args.transjakarta else None
mrt = json.load(open(args.mrt)) if args.mrt else None
TRANSIT = bool(tj or mrt)
KRL_COLOUR = "#3b3b3b"
AUTHOR = "Rizky A Kurniawan, Oktober 2026"
DRAWN_WITH = "Python (matplotlib, Shapely, pyosmium)"
TJ_BLUE = "#1f3b70"

plt.rcParams["font.family"] = ["Arial", "Helvetica", "DejaVu Sans"]

# At 1:125.000 this is the same extent as render.py. At larger scales the
# frame is capped at MAX_W_MM wide and kept south of N_MAX so the bay stays in.
SCALE = args.scale
M_PER_DEG_LAT = 110_574
MAP_H_MM = 297 - 20
MAX_W_MM, N_MAX, LON_C = 296, -6.09, 106.83
KY = 1000 * M_PER_DEG_LAT / SCALE   # map mm per degree of latitude
LAT_SPAN = MAP_H_MM / KY
LAT_C = max(-6.23, N_MAX - LAT_SPAN / 2)
S, N = LAT_C - LAT_SPAN / 2, LAT_C + LAT_SPAN / 2
LAT0 = math.radians(LAT_C)
ASPECT = 1 / math.cos(LAT0)
KX = KY / ASPECT                    # map mm per degree of longitude
W = max(106.675, LON_C - MAX_W_MM / 2 / KX)
E = min(106.985, LON_C + MAX_W_MM / 2 / KX)

MM = 1 / 25.4
FIG_W, FIG_H = 420 * MM, 297 * MM

# ISOM 2017 colour set (RGB approximations of the OCAD / OOM defaults)
I = {
    "black": "#000000",
    "brown": "#d47f2a",
    "brown50": "#eab27b",
    "yellow": "#ffba35",
    "yellow50": "#ffdd9a",
    "green20": "#c5ffb9",
    "green50": "#8bff74",
    "olive": "#a8a83a",
    "blue": "#00a0e2",
    "blue50": "#80d4f5",
}
# land cover category -> (ISOM code, fill, label, draw order)
LC = {
    "rough":  ("403", I["yellow50"], "Lahan terbuka kasar (sawah, padang, bandara)", 1.30),
    "open":   ("401", I["yellow"], "Lahan terbuka (taman, lapangan, makam, golf)", 1.31),
    "scrub":  ("406", I["green20"], "Vegetasi, lari lambat (semak, kebun)", 1.32),
    "forest": ("408", I["green50"], "Vegetasi, jalan kaki (hutan kota)", 1.33),
    "oob":    ("520", I["olive"], "Area terlarang (industri, militer, pelabuhan)", 1.34),
    "water":  ("301", I["blue50"], "Badan air (danau, waduk, situ)", 1.35),
}
# road class -> (black edge width, brown fill width or 0, zorder); widths in pt
ROAD = {
    "tertiary":       (0.45, 0, 3),
    "secondary_link": (0.7, 0, 4),
    "secondary":      (0.95, 0, 4),
    "primary_link":   (1.2, 0.6, 5),
    "primary":        (1.7, 1.0, 5),
    "trunk_link":     (1.4, 0.8, 6),
    "trunk":          (2.3, 1.5, 6),
    "motorway_link":  (1.5, 0.9, 7),
    "motorway":       (2.8, 1.9, 7),
}

fig = plt.figure(figsize=(FIG_W, FIG_H), dpi=100)
fig.patch.set_facecolor("white")
margin = 10 * MM / FIG_W
map_h = MAP_H_MM / 297
map_w_mm = MAP_H_MM * (E - W) / ((N - S) * ASPECT)
ax = fig.add_axes([margin, 10 / 297, map_w_mm / 420, map_h])
ax.set_xlim(W, E)
ax.set_ylim(S, N)
ax.set_aspect(ASPECT)
ax.set_facecolor("white")   # ISOM 405: runnable forest / open urban ground
ax.set_xticks([])
ax.set_yticks([])
for sp in ax.spines.values():
    sp.set_color(I["black"])
    sp.set_linewidth(0.8)
frame = box(W, S, E, N)

# --- Sea: split the frame by the coastline (same approach as render.py)
coast = [w["c"] for w in data["ways"] if w["k"] == "coast"]
if coast:
    cl = unary_union([LineString(c) for c in coast]).intersection(frame.buffer(0.02))
    try:
        for g in split(frame, cl).geoms:
            if g.contains(Point(LON_C, N - 0.003)):
                ax.add_patch(MplPolygon(list(g.exterior.coords), closed=True,
                                        fc=I["blue50"], ec="none", zorder=0.5))
    except Exception as e:
        print("sea split failed:", e)
    ax.add_collection(LineCollection(coast, colors=I["blue"], linewidths=0.9, zorder=1.4))

# --- Land cover areas
by_cat = defaultdict(list)
for a in lc:
    by_cat[a["k"]].append(MplPolygon(a["c"], closed=True))
for k, (_, fc, _, z) in LC.items():
    if by_cat[k]:
        ax.add_collection(PatchCollection(by_cat[k], fc=fc, ec="none", zorder=z))
if by_cat["water"]:
    ax.add_collection(PatchCollection(by_cat["water"], fc="none", ec=I["blue"], lw=0.35,
                                      zorder=1.36))

# --- Boundaries (black dash / dash-dot)
kota_polys = {}
for a in data["admin"]:
    if a["level"] == "5" and a["name"].startswith("Jakarta "):
        polys = list(polygonize(linemerge([LineString(l) for l in a["lines"] if len(l) > 1])))
        if polys:
            kota_polys[a["name"]] = unary_union(polys)
        ax.add_collection(LineCollection(a["lines"], colors=I["black"], linewidths=0.4,
                                         linestyles=(0, (5, 2.5)), alpha=0.7, zorder=2))
    if a["level"] == "4":
        ax.add_collection(LineCollection(a["lines"], colors=I["black"], linewidths=1.1,
                                         linestyles=(0, (7, 2, 1.5, 2)), zorder=2.1))

# --- Watercourses (ISOM 304/305: blue line)
rivers = [w["c"] for w in data["ways"] if w["k"] == "river"]
ax.add_collection(LineCollection(rivers, colors=I["blue"], linewidths=0.8, zorder=2.2))

# --- Roads: ISOM 502 wide road (black edges + brown fill) / 503-504 black line
by_kind = defaultdict(list)
for w in data["ways"]:
    if w["k"] in ROAD:
        by_kind[w["k"]].append(w["c"])
for k, (bw, fw, z) in ROAD.items():
    ax.add_collection(LineCollection(by_kind[k], colors=I["black"], linewidths=bw,
                                     capstyle="butt", joinstyle="round", zorder=z))
for k, (bw, fw, z) in ROAD.items():
    if fw:
        ax.add_collection(LineCollection(by_kind[k], colors=I["brown50"], linewidths=fw,
                                         capstyle="round", joinstyle="round", zorder=z + 0.5))

# --- Railway (ISOM 515: black line with cross ticks; with transit layers the
# line is drawn bold with a white casing, as in render.py --style transit)
rail = [w["c"] for w in data["ways"] if w["k"] == "rail"]
RAIL_TRACK = (1.4, 5.2, (0, (0.45, 3.6)))   # line width, tick length, tick dashes (pt)


def single_track(lines, tol=0.00025):
    """Drop rail ways that run alongside an already kept one (double / parallel
    tracks), so the cross ticks of neighbouring tracks don't merge into blobs."""
    kept, cover = [], None
    for ls in sorted((LineString(l) for l in lines), key=lambda g: -g.length):
        if cover is not None and ls.intersection(cover).length > 0.6 * ls.length:
            continue
        kept.append(list(ls.coords))
        cover = ls.buffer(tol) if cover is None else cover.union(ls.buffer(tol))
    return kept


if TRANSIT and args.rail_symbol:
    lw, tick, dashes = RAIL_TRACK
    rail = single_track(rail)
    ax.add_collection(LineCollection(rail, colors="white", linewidths=tick + 1.6,
                                     capstyle="round", joinstyle="round", zorder=8))
    ax.add_collection(LineCollection(rail, colors=I["black"], linewidths=lw, zorder=8.1))
    ax.add_collection(LineCollection(rail, colors=I["black"], linewidths=tick,
                                     linestyles=dashes, zorder=8.1))
elif TRANSIT:
    ax.add_collection(LineCollection(rail, colors="white", linewidths=4.2, capstyle="round",
                                     joinstyle="round", zorder=8))
    ax.add_collection(LineCollection(rail, colors=KRL_COLOUR, linewidths=2.6, capstyle="round",
                                     joinstyle="round", zorder=8.1))
else:
    ax.add_collection(LineCollection(rail, colors=I["black"], linewidths=0.9, zorder=8))
    ax.add_collection(LineCollection(rail, colors=I["black"], linewidths=2.8,
                                     linestyles=(0, (0.35, 4)), zorder=8))

# --- TransJakarta corridors (white casing + corridor colour) and halte
if tj:
    for r in reversed(tj["routes"]):
        ax.add_collection(LineCollection(r["lines"], colors="white", linewidths=5.2,
                                         capstyle="round", joinstyle="round", zorder=9))
    for r in reversed(tj["routes"]):
        ax.add_collection(LineCollection(r["lines"], colors=r["colour"], linewidths=3.4,
                                         capstyle="round", joinstyle="round", zorder=9.5))
    single = [h["c"] for h in tj["halte"] if len(h["refs"]) == 1]
    multi = [h["c"] for h in tj["halte"] if len(h["refs"]) > 1]
    if single:
        ax.scatter(*zip(*single), s=11, c="white", edgecolors=TJ_BLUE, linewidths=0.6, zorder=12)
    if multi:
        ax.scatter(*zip(*multi), s=26, c="white", edgecolors="black", linewidths=1.0, zorder=12.1)

# --- MRT Jakarta line and stations
if mrt:
    ax.add_collection(LineCollection(mrt["lines"], colors="white", linewidths=7.6,
                                     capstyle="round", joinstyle="round", zorder=10.4))
    ax.add_collection(LineCollection(mrt["lines"], colors=mrt["colour"], linewidths=5.2,
                                     capstyle="round", joinstyle="round", zorder=10.5))
    ax.scatter(*zip(*[st["c"] for st in mrt["stations"]]), marker="s", s=40, c="white",
               edgecolors=mrt["colour"], linewidths=1.5, zorder=13)

# --- KRL / KAI stations: black square with white ring (transit: dark disc)
if krl:
    for major, size in ((False, 14), (True, 30)):
        pts = [st["c"] for st in krl if st["major"] == major]
        if pts and TRANSIT:
            ax.scatter(*zip(*pts), s=size * 2.1, c=KRL_COLOUR, edgecolors="white",
                       linewidths=1.0, zorder=12.5)
        elif pts:
            ax.scatter(*zip(*pts), marker="s", s=size, c=I["black"], edgecolors="white",
                       linewidths=0.8, zorder=12.5)

# --- Magnetic north lines (ISOM 601), every 20 mm on the map
NL_STEP = 20 / KX
x = W + NL_STEP / 2
while x < E:
    ax.axvline(x, color=I["blue"], lw=0.5, zorder=2.5 if TRANSIT else 15)
    ax.annotate("", xy=(x, N - 0.002), xytext=(x, N - 0.012), zorder=15.1,
                arrowprops=dict(arrowstyle="-|>,head_width=0.18,head_length=0.5",
                                lw=0.5, color=I["blue"]))
    x += NL_STEP

# --- Labels: greedy collision avoidance in display space (as in render.py)
fig.canvas.draw()
renderer = fig.canvas.get_renderer()
placed = []


def try_label(x, y, text, rot=0, size=5, color=I["black"], weight="normal", halo=1.6,
              z=20, style="normal", pad=2, ha="center", va="center", dx=0, dy=0, bbox=None):
    if not (W < x < E and S < y < N):
        return False
    tr = offset_copy(ax.transData, fig=fig, x=dx, y=dy, units="points")
    t = ax.text(x, y, text, fontsize=size, color=color, weight=weight, style=style,
                rotation=rot, rotation_mode="anchor", ha=ha, va=va, transform=tr, zorder=z, bbox=bbox,
                path_effects=[pe.withStroke(linewidth=halo, foreground="white")] if halo else None)
    bb = t.get_window_extent(renderer).expanded(1, 1).padded(pad)
    ab = ax.get_window_extent(renderer)
    if (bb.x0 < ab.x0 or bb.x1 > ab.x1 or bb.y0 < ab.y0 or bb.y1 > ab.y1
            or any(bb.overlaps(o) for o in placed)):
        t.remove()
        return False
    placed.append(bb)
    return True


def reserve(x0, y0, x1, y1):
    placed.append(Bbox([ax.transData.transform((x0, y0)), ax.transData.transform((x1, y1))]))


# Panels drawn later (scale bottom-left); keep labels out of them
PANEL = (W + 0.004, S + 0.004, W + 0.068, S + 0.027)
reserve(*PANEL)

def reserve_points(pts, radius_px):
    for x, y in pts:
        px, py = ax.transData.transform((x, y))
        placed.append(Bbox([[px - radius_px, py - radius_px], [px + radius_px, py + radius_px]]))


# MRT and KRL station names
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
    reserve_points([st["c"] for st in krl], 4 if TRANSIT else 3)
    for st in sorted(krl, key=lambda st: not st["major"]):
        for ha, va, dx, dy in POSITIONS:
            if try_label(st["c"][0], st["c"][1], "St. " + st["n"],
                         size=4.8 if st["major"] else 4.2, weight="bold", halo=1.4, z=22,
                         color=KRL_COLOUR if TRANSIT else I["black"],
                         pad=0.5, ha=ha, va=va, dx=dx, dy=dy):
                break
if tj:
    reserve_points([h["c"] for h in tj["halte"]], 3)
    # Corridor number badges along each corridor
    for r in tj["routes"]:
        m = linemerge([LineString(l) for l in r["lines"]])
        done = 0
        for ln in sorted(getattr(m, "geoms", [m]), key=lambda g: -g.length)[:4]:
            for frac in (0.5, 0.3, 0.7, 0.15, 0.85):
                pt = ln.interpolate(frac, normalized=True)
                if try_label(pt.x, pt.y, r["ref"], size=5.5, color="white", weight="bold",
                             halo=0, z=22, pad=3,
                             bbox=dict(boxstyle="round,pad=0.25", fc=r["colour"], ec="white",
                                       lw=0.6)):
                    done += 1
                    break
            if done >= 2:
                break
    # Halte names: interchanges first
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

# Kota names
for name, geom in kota_polys.items():
    p = geom.representative_point()
    try_label(p.x, p.y, name.upper(), size=10, color="#00000066", weight="bold",
              halo=0, z=19, pad=0)


def short_name(name):
    for full, short in (("Jalan Tol ", "Tol "), ("Jalan Raya ", "Jl. Raya "), ("Jalan ", "Jl. ")):
        if name.startswith(full):
            return short + name[len(full):]
    return name


# Road names along the longest merged pieces
groups = defaultdict(list)
for w in data["ways"]:
    if w["k"] in ("motorway", "trunk", "primary") and w["n"]:
        groups[(w["k"], w["n"])].append(LineString(w["c"]))
font = {"motorway": 5.2, "trunk": 4.9, "primary": 4.5}
seen = defaultdict(list)
for k in ("motorway", "trunk") if TRANSIT else ("motorway", "trunk", "primary"):
    items = []
    for (kk, name), segs in groups.items():
        if kk == k:
            m = linemerge(segs)
            items += [(ln.length, name, ln) for ln in getattr(m, "geoms", [m]) if ln.length >= 0.01]
    for length, name, ln in sorted(items, reverse=True):
        mid = ln.interpolate(0.5, normalized=True)
        if any(mid.distance(p) < 0.04 for p in seen[name]):
            continue
        for frac in (0.5, 0.35, 0.65, 0.2, 0.8):
            pt = ln.interpolate(frac, normalized=True)
            a = ln.interpolate(max(frac - 0.02, 0), normalized=True)
            b = ln.interpolate(min(frac + 0.02, 1), normalized=True)
            ang = math.degrees(math.atan2((b.y - a.y) * ASPECT, b.x - a.x))
            ang = ang - 180 if ang > 90 else ang + 180 if ang < -90 else ang
            if try_label(pt.x, pt.y, short_name(name), rot=ang, size=font[k],
                         weight="bold" if k == "motorway" else "normal", halo=1.4):
                seen[name].append(pt)
                break

# Place names
for t, size in (("city_district", 6.0), ("suburb", 4.6), ("quarter", 4.0)):
    for p in data["places"]:
        if p["t"] == t:
            try_label(p["c"][0], p["c"][1], p["n"], size=size, style="italic", z=18)

# --- Scale panel
scale_txt = f"{SCALE:,}".replace(",", ".")
px0, py0, px1, py1 = PANEL
ax.add_patch(Rectangle((px0, py0), px1 - px0, py1 - py0, fc="white", ec=I["black"], lw=0.6,
                       zorder=32))
ax.text(px0 + 0.003, py1 - 0.0028, f"1 : {scale_txt}", ha="left", va="top", fontsize=10,
        weight="bold", zorder=33)
seg = 1 / (111.32 * math.cos(LAT0))
bx, by = px0 + 0.004, py0 + 0.0085
for i in range(5):
    ax.add_patch(Rectangle((bx + i * seg, by), seg, 0.0013,
                           fc=I["black"] if i % 2 == 0 else "white", ec=I["black"], lw=0.5,
                           zorder=33))
for i in range(6):
    ax.text(bx + i * seg, by + 0.0021, str(i), ha="center", va="bottom", fontsize=6, zorder=33)
ax.text(bx + 5 * seg + 0.0018, by + 0.00065, "km", ha="left", va="center", fontsize=6, zorder=33)
nl_km = f"{20 * SCALE / 1e6:g}".replace(".", ",")
ax.text(px0 + 0.003, py0 + 0.0028, f"Jarak garis utara magnetik: {nl_km} km", ha="left",
        va="bottom", fontsize=6.3, zorder=33)

# --- Sidebar: title, ISOM legend, control descriptions
sx0 = margin + map_w_mm / 420 + 8 / 420
side = fig.add_axes([sx0, 10 / 297, 1 - sx0 - margin, map_h])
side.axis("off")
side.set_xlim(0, 1)
side.set_ylim(0, 1)
scale_txt = f"{SCALE:,}".replace(",", ".")
side.text(0, 0.985, "PETA JAKARTA ORIENTEERING", fontsize=18, weight="bold", va="top")
side.text(0, 0.94, "DKI JAKARTA", fontsize=26, weight="bold", color=I["brown"], va="top")
side.text(0, 0.885, f"Skala 1:{scale_txt}", fontsize=11, weight="bold", va="top")
side.text(0, 0.86, "ISOM 2017, dimodifikasi dan disesuaikan dengan kebutuhan event", fontsize=8.5, color="#555555", va="top")
TOP = 0.838
side.plot([0, 1], [TOP, TOP], color=I["black"], lw=0.8)

ROW = 0.0192 if TRANSIT else 0.026
y = TOP - 0.03
side.text(0, y, "LEGENDA", fontsize=10, weight="bold", va="top")
y -= 0.038


def row(code, label):
    global y
    side.text(0.2, y, code, fontsize=6.5, color="#666666", va="center")
    side.text(0.29, y, label, fontsize=7.8, va="center")
    y -= ROW


def area_sample(fc, ec="none", lw=0):
    side.add_patch(Rectangle((0, y - 0.009), 0.15, 0.018, fc=fc, ec=ec, lw=lw))


def line_sample(**kw):
    side.add_line(Line2D([0, 0.15], [y, y], solid_capstyle="butt", **kw))


if mrt:
    line_sample(color=mrt["colour"], lw=5)
    side.scatter([0.075], [y], marker="s", s=40, c="white", edgecolors=mrt["colour"],
                 linewidths=1.6, zorder=5)
    row("", "Jalur & stasiun MRT Jakarta")
if tj:
    for i, r in enumerate(tj["routes"][:4]):
        side.add_line(Line2D([i * 0.0375, (i + 1) * 0.0375], [y, y], color=r["colour"], lw=4.2,
                             solid_capstyle="butt"))
    row("", "Koridor busway TransJakarta (BRT)")
    side.scatter([0.075], [y], s=16, c="white", edgecolors=TJ_BLUE, linewidths=0.8)
    row("", "Halte busway")
    side.scatter([0.075], [y], s=34, c="white", edgecolors="black", linewidths=1.3)
    row("", "Halte transit (antarkoridor)")
area_sample("white", ec="#999999", lw=0.4); row("405", "Area dapat dilalui (permukiman, lahan umum)")
for k, (code, fc, label, _) in LC.items():
    if k == "water":
        area_sample(fc, ec=I["blue"], lw=0.5)
    else:
        area_sample(fc)
    row(code, label)
area_sample(I["blue50"]); row("301", "Laut (Teluk Jakarta)")
line_sample(color=I["blue"], lw=1.4); row("305", "Sungai / kanal")
for k, code, label in (("motorway", "502", "Jalan tol"), ("trunk", "502", "Jalan arteri utama"),
                       ("primary", "502", "Jalan arteri / primer"),
                       ("secondary", "503", "Jalan kolektor / sekunder"),
                       ("tertiary", "504", "Jalan lokal / tersier")):
    bw, fw, _ = ROAD[k]
    line_sample(color=I["black"], lw=bw * 1.6)
    if fw:
        line_sample(color=I["brown50"], lw=fw * 1.6)
    row(code, label)
if TRANSIT and args.rail_symbol:
    lw, tick, dashes = RAIL_TRACK
    line_sample(color=I["black"], lw=lw)
    side.add_line(Line2D([0, 0.15], [y, y], color=I["black"], lw=tick, linestyle=dashes))
    row("515", "Rel kereta api (KRL / KA)")
elif TRANSIT:
    line_sample(color=KRL_COLOUR, lw=3.6)
    row("", "Rel kereta api (KRL / KA)")
else:
    line_sample(color=I["black"], lw=1.2)
    side.add_line(Line2D([0, 0.15], [y, y], color=I["black"], lw=4, linestyle=(0, (0.4, 3))))
    row("515", "Rel kereta api")
if krl and TRANSIT:
    side.scatter([0.045, 0.105], [y, y], s=[22, 46], c=KRL_COLOUR, edgecolors="white",
                 linewidths=1.0, zorder=5)
    row("", "Stasiun kereta api (kecil: KRL, besar: utama)")
elif krl:
    side.scatter([0.05, 0.11], [y, y], marker="s", s=[14, 30], c=I["black"],
                 edgecolors="white", linewidths=0.8, zorder=5)
    row("", "Stasiun KRL / KA (besar: stasiun utama)")
line_sample(color=I["black"], lw=1.6, linestyle=(0, (7, 2, 1.5, 2))); row("", "Batas provinsi")
line_sample(color=I["black"], lw=0.7, linestyle=(0, (5, 2.5)), alpha=0.7)
row("", "Batas kota administrasi")
line_sample(color=I["blue"], lw=0.8); row("601", "Garis utara magnetik")
if tj:
    y -= 0.01
    side.plot([0, 1], [y + 0.012, y + 0.012], color=I["black"], lw=0.5)
    side.text(0, y, "KORIDOR TRANSJAKARTA (BRT)", fontsize=10, weight="bold", va="top")
    y -= 0.035
    half = (len(tj["routes"]) + 1) // 2
    step = 0.024
    for i, r in enumerate(tj["routes"]):
        col, rw = divmod(i, half)
        x0, yy = col * 0.52, y - rw * step
        side.text(x0 + 0.025, yy, r["ref"], fontsize=6.5, color="white", weight="bold",
                  ha="center", va="center",
                  bbox=dict(boxstyle="round,pad=0.3", fc=r["colour"], ec="none"))
        side.text(x0 + 0.065, yy, r["name"], fontsize=6.6, va="center")
side.text(0, 0.0, f"Skala 1 : {scale_txt} bila dicetak A3 (420 × 297 mm) ukuran asli\n"
                  "Data peta © kontributor OpenStreetMap (ODbL) · openstreetmap.org/copyright\n"
                  f"Digambar menggunakan: {DRAWN_WITH}\n"
                  f"Oleh: {AUTHOR}",
          fontsize=6.5, color="#666666", va="bottom", linespacing=1.5)

# Narrower sidebar (larger scales): shrink its text to fit
SIDE_W_MM = (1 - sx0 - margin) * 420
for t in side.texts:
    t.set_fontsize(t.get_fontsize() * min(1, SIDE_W_MM / 116))

fig.savefig(PREFIX + ".pdf")
fig.savefig(PREFIX + ".png", dpi=300)
print("saved", PREFIX + ".pdf", PREFIX + ".png", "labels:", len(placed))
