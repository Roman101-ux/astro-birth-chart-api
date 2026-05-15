
from fastapi import FastAPI, Response
from pydantic import BaseModel
from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from html import escape
import pytz
import swisseph as swe
import math
import random
import cairosvg

app = FastAPI(title="Astralytica Premium API", version="4.0.0")

geolocator = Nominatim(user_agent="astralytica-premium")
tf = TimezoneFinder()

# ============================================================
# KONSTANTEN
# ============================================================

ZODIAC = [
    ("Widder", "♈︎", "Feuer", "Kardinal", "#E74C3C"),
    ("Stier", "♉︎", "Erde", "Fix", "#5B8A4B"),
    ("Zwillinge", "♊︎", "Luft", "Veränderlich", "#C99A36"),
    ("Krebs", "♋︎", "Wasser", "Kardinal", "#4477BB"),
    ("Löwe", "♌︎", "Feuer", "Fix", "#E74C3C"),
    ("Jungfrau", "♍︎", "Erde", "Veränderlich", "#5B8A4B"),
    ("Waage", "♎︎", "Luft", "Kardinal", "#C99A36"),
    ("Skorpion", "♏︎", "Wasser", "Fix", "#4477BB"),
    ("Schütze", "♐︎", "Feuer", "Veränderlich", "#E74C3C"),
    ("Steinbock", "♑︎", "Erde", "Kardinal", "#5B8A4B"),
    ("Wassermann", "♒︎", "Luft", "Fix", "#C99A36"),
    ("Fische", "♓︎", "Wasser", "Veränderlich", "#4477BB"),
]

PLANETS = {
    "Sonne": (swe.SUN, "☉", 1.20),
    "Mond": (swe.MOON, "☽", 1.15),
    "Merkur": (swe.MERCURY, "☿", 1.00),
    "Venus": (swe.VENUS, "♀", 1.00),
    "Mars": (swe.MARS, "♂", 1.00),
    "Jupiter": (swe.JUPITER, "♃", 0.95),
    "Saturn": (swe.SATURN, "♄", 0.95),
    "Uranus": (swe.URANUS, "♅", 0.90),
    "Neptun": (swe.NEPTUNE, "♆", 0.90),
    "Pluto": (swe.PLUTO, "♇", 0.90),
    "Nordknoten": (swe.MEAN_NODE, "☊", 0.85),
}

# Name, Winkel, Orb, Farbe, Layer, Stärke, Opacity
ASPECTS = [
    ("Konjunktion", 0, 8, "#777777", 0, 0.80, 0.38),
    ("Sextil", 60, 5, "#6FA8FF", 3, 0.95, 0.72),
    ("Quadrat", 90, 6, "#E27D7D", 2, 1.05, 0.78),
    ("Trigon", 120, 6, "#6FA8FF", 4, 0.95, 0.72),
    ("Opposition", 180, 8, "#D66A6A", 1, 1.10, 0.78),
]

AMBIGUOUS_PLACES = {
    "tschuj", "chuy", "chui", "chuy region", "chuy oblast",
    "tschuj region", "tschuj oblast"
}


class BirthData(BaseModel):
    birth_date: str
    birth_time: str
    birth_place: str
    country: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    timezone: Optional[str] = None


# ============================================================
# MATHE / ASTRO BASIS
# ============================================================

def norm_deg(x: float) -> float:
    return x % 360.0


def deg_to_dms(deg: float) -> str:
    d = int(deg)
    m = int(round((deg - d) * 60))
    if m == 60:
        d += 1
        m = 0
    return f"{d}°{m:02d}'"


def sign_data(longitude: float):
    lon = norm_deg(longitude)
    idx = int(lon // 30)
    degree = lon % 30
    name, glyph, element, modality, color = ZODIAC[idx]
    return idx, name, glyph, element, modality, color, degree


def angle_for_longitude(longitude: float) -> float:
    # Aries starts left, zodiac progresses counterclockwise in this projection.
    return math.radians(180.0 - longitude)


def polar(cx: float, cy: float, r: float, angle: float) -> Tuple[float, float]:
    return cx + r * math.cos(angle), cy + r * math.sin(angle)


def angular_diff(a: float, b: float) -> float:
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


def signed_angle_diff(a: float, b: float) -> float:
    return ((a - b + 180.0) % 360.0) - 180.0


def point_on_arc(start: float, end: float, value: float) -> bool:
    start, end, value = norm_deg(start), norm_deg(end), norm_deg(value)
    if end < start:
        end += 360
    if value < start:
        value += 360
    return start <= value < end


def find_house(longitude: float, houses: List[float]) -> Optional[int]:
    for i in range(12):
        if point_on_arc(houses[i], houses[(i + 1) % 12], longitude):
            return i + 1
    return None


def calculate_planet_position(julian_day: float, planet_id: int):
    try:
        data = swe.calc_ut(julian_day, planet_id, swe.FLG_SWIEPH | swe.FLG_SPEED)[0]
        return data, "swiss_ephemeris"
    except Exception:
        data = swe.calc_ut(julian_day, planet_id, swe.FLG_MOSEPH | swe.FLG_SPEED)[0]
        return data, "moshier_fallback"


def calculate_aspects(points: Dict[str, float]):
    aspects = []
    names = list(points.keys())

    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            p1, p2 = names[i], names[j]
            diff = angular_diff(points[p1], points[p2])

            for aspect_name, exact, orb_limit, color, layer, stroke, opacity in ASPECTS:
                orb = abs(diff - exact)
                if orb <= orb_limit:
                    aspects.append({
                        "p1": p1,
                        "p2": p2,
                        "aspect": aspect_name,
                        "angle": round(diff, 3),
                        "orb": round(orb, 3),
                        "exact": exact,
                        "color": color,
                        "layer": layer,
                        "stroke": stroke,
                        "opacity": opacity,
                    })
                    break

    # Erst weite/ruhige Aspekte, dann enge Aspekte obenauf
    return sorted(aspects, key=lambda x: (x["layer"], -x["orb"]))


# ============================================================
# SVG HELPERS
# ============================================================

def safe_text(x) -> str:
    return escape(str(x))


def svg_text(x, y, text, size=9, anchor="start", weight="400", fill="#222", extra=""):
    return (
        f'<text x="{x}" y="{y}" font-size="{size}" '
        f'text-anchor="{anchor}" '
        f'font-family="Inter, Segoe UI, Arial, Helvetica, DejaVu Sans, sans-serif" '
        f'font-weight="{weight}" fill="{fill}" {extra}>{safe_text(text)}</text>'
    )


def svg_symbol(x, y, text, size=18, anchor="middle", fill="#111", extra=""):
    return (
        f'<text x="{x}" y="{y}" font-size="{size}" '
        f'text-anchor="{anchor}" '
        f'font-family="DejaVu Serif, Noto Sans Symbols, Arial Unicode MS, serif" '
        f'font-weight="500" fill="{fill}" {extra}>{safe_text(text)}</text>'
    )


def svg_line(x1, y1, x2, y2, color="#222", width=1, opacity=1, extra=""):
    return (
        f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
        f'stroke="{color}" stroke-width="{width}" opacity="{opacity}" {extra}/>'
    )


def svg_circle(cx, cy, r, fill="none", stroke="#222", width=1, opacity=1, extra=""):
    return (
        f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="{width}" opacity="{opacity}" {extra}/>'
    )


def svg_rect(x, y, w, h, fill="#fffdf8", stroke="#c9b994", rx=8, extra=""):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" stroke="{stroke}" rx="{rx}" {extra}/>'


def svg_pie(cx, cy, r, values, colors):
    total = sum(values.values())
    if total <= 0:
        return ""

    out = []
    start = -90.0

    for key, value in values.items():
        if value <= 0:
            continue

        sweep = 360.0 * value / total
        end = start + sweep
        a1, a2 = math.radians(start), math.radians(end)

        x1, y1 = cx + r * math.cos(a1), cy + r * math.sin(a1)
        x2, y2 = cx + r * math.cos(a2), cy + r * math.sin(a2)
        large = 1 if sweep > 180 else 0

        out.append(
            f'<path d="M {cx} {cy} L {x1:.2f} {y1:.2f} '
            f'A {r} {r} 0 {large} 1 {x2:.2f} {y2:.2f} Z" '
            f'fill="{colors.get(key, "#999")}" opacity="0.95"/>'
        )
        start = end

    out.append(svg_circle(cx, cy, r, stroke="#ddd", width=0.6))
    return "".join(out)


# ============================================================
# PREMIUM PLANET PLACEMENT
# ============================================================

class PlanetNode:
    def __init__(self, planet: dict, base_radius: float, cx: float, cy: float):
        self.planet = planet
        self.name = planet["planet"]
        self.true_lon = planet["longitude"]
        self.display_lon = planet["longitude"]
        self.base_radius = base_radius
        self.radius_offset = 0.0
        self.r = base_radius
        self.angle = angle_for_longitude(self.display_lon)
        self.x, self.y = polar(cx, cy, self.r, self.angle)
        self.v_lon = 0.0
        self.v_r = 0.0
        self.locked = False


def cluster_planets(planets: List[dict], gap_deg: float = 10.0) -> List[List[dict]]:
    ordered = sorted(planets, key=lambda p: p["longitude"])
    if not ordered:
        return []

    clusters = []
    cur = [ordered[0]]

    for p in ordered[1:]:
        if angular_diff(p["longitude"], cur[-1]["longitude"]) <= gap_deg:
            cur.append(p)
        else:
            clusters.append(cur)
            cur = [p]
    clusters.append(cur)

    # Wrap-around cluster at 0 Aries
    if len(clusters) > 1 and angular_diff(clusters[0][0]["longitude"], clusters[-1][-1]["longitude"]) <= gap_deg:
        merged = clusters[-1] + clusters[0]
        clusters = [merged] + clusters[1:-1]

    return clusters


def seed_multi_ring_positions(nodes: List[PlanetNode]):
    clusters = cluster_planets([n.planet for n in nodes], gap_deg=10.0)
    node_by_name = {n.name: n for n in nodes}

    for cluster in clusters:
        n = len(cluster)
        if n == 1:
            node = node_by_name[cluster[0]["planet"]]
            node.display_lon = node.true_lon
            node.radius_offset = 0.0
            continue

        # Robust center on circle using vector mean
        sx = sum(math.cos(math.radians(p["longitude"])) for p in cluster)
        sy = sum(math.sin(math.radians(p["longitude"])) for p in cluster)
        center = norm_deg(math.degrees(math.atan2(sy, sx)))

        spread = min(48.0, max(18.0, n * 9.0))
        start = center - spread / 2.0
        ring_pattern = [0, 14, 28, 14, 0, 28, 42, 14, 0, 28, 42]

        sorted_cluster = sorted(cluster, key=lambda p: p["longitude"])
        for i, p in enumerate(sorted_cluster):
            node = node_by_name[p["planet"]]
            node.display_lon = norm_deg(start + i * (spread / max(n - 1, 1)))
            node.radius_offset = ring_pattern[i % len(ring_pattern)]


def apply_axis_avoidance(nodes: List[PlanetNode], axes: List[float], avoid_deg: float = 7.0):
    for node in nodes:
        for axis in axes:
            d = signed_angle_diff(node.display_lon, axis)
            if abs(d) < avoid_deg:
                node.display_lon = norm_deg(node.display_lon + (avoid_deg - abs(d) + 1.5) * (1 if d >= 0 else -1))


def force_directed_planet_layout(planets: List[dict], cx: float, cy: float, base_radius: float, axes: List[float]):
    random.seed(7)

    nodes = [PlanetNode(p, base_radius, cx, cy) for p in planets]
    seed_multi_ring_positions(nodes)
    apply_axis_avoidance(nodes, axes, avoid_deg=7.0)

    min_dist = 22.0
    min_radial_gap = 11.0
    angular_strength = 0.025
    collision_strength = 0.62
    axis_strength = 0.05
    target_strength = 0.020
    damping = 0.78
    max_radius_offset = 48.0

    for _ in range(180):
        for n in nodes:
            n.v_lon *= damping
            n.v_r *= damping

            # Pull back to true longitude, but weakly.
            n.v_lon += signed_angle_diff(n.true_lon, n.display_lon) * target_strength

            # Prefer existing seeded ring.
            preferred_offset = n.radius_offset
            n.v_r += (preferred_offset - n.radius_offset) * 0.04

            # Avoid major axes.
            for axis in axes:
                d = signed_angle_diff(n.display_lon, axis)
                if abs(d) < 8.0:
                    push = (8.0 - abs(d)) * axis_strength
                    n.v_lon += push * (1 if d >= 0 else -1)

        # Planet collision resolution.
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                a, b = nodes[i], nodes[j]

                ang_gap = abs(signed_angle_diff(a.display_lon, b.display_lon))
                radial_gap = abs(a.radius_offset - b.radius_offset)

                # Combined approximate screen distance.
                ax, ay = polar(cx, cy, base_radius - a.radius_offset, angle_for_longitude(a.display_lon))
                bx, by = polar(cx, cy, base_radius - b.radius_offset, angle_for_longitude(b.display_lon))
                dist = math.hypot(ax - bx, ay - by)

                if dist < min_dist:
                    push = (min_dist - dist) * collision_strength
                    direction = 1 if signed_angle_diff(a.display_lon, b.display_lon) >= 0 else -1

                    a.v_lon += direction * push * angular_strength
                    b.v_lon -= direction * push * angular_strength

                    # If angular spread is too small, also push onto different rings.
                    if ang_gap < 7.0 and radial_gap < min_radial_gap:
                        if a.radius_offset <= b.radius_offset:
                            a.v_r += min_radial_gap * 0.10
                            b.v_r -= min_radial_gap * 0.06
                        else:
                            b.v_r += min_radial_gap * 0.10
                            a.v_r -= min_radial_gap * 0.06

        # Integrate.
        for n in nodes:
            n.display_lon = norm_deg(n.display_lon + n.v_lon)
            n.radius_offset = max(0.0, min(max_radius_offset, n.radius_offset + n.v_r))
            apply_axis_avoidance([n], axes, avoid_deg=6.0)

    # Final post-pass: still too close -> deterministic radial stacking.
    nodes_sorted = sorted(nodes, key=lambda n: n.display_lon)
    for i in range(len(nodes_sorted)):
        for j in range(i + 1, len(nodes_sorted)):
            a, b = nodes_sorted[i], nodes_sorted[j]
            if angular_diff(a.display_lon, b.display_lon) < 5.0 and abs(a.radius_offset - b.radius_offset) < 12:
                b.radius_offset = min(max_radius_offset, b.radius_offset + 14)

    return nodes


# ============================================================
# PREMIUM ASPECT LAYERING
# ============================================================

def aspect_layer_radius(aspect: dict, base_radius: float, index: int, density: int) -> float:
    layer = aspect["layer"]
    base_offsets = {
        1: 0,    # Opposition
        2: 9,    # Quadrat
        3: 17,   # Sextil
        4: 25,   # Trigon
        0: 32,   # Konjunktion, normally skipped
    }
    density_adjust = min(12, max(0, density - 8)) * 0.8
    jitter = (index % 4) * 2.2
    return base_radius - base_offsets.get(layer, 12) - density_adjust - jitter


# ============================================================
# RENDERER
# ============================================================

def generate_professional_cosmogram_svg(chart, width: int = 1080, height: int = 760):
    # Responsive scaling: design coordinates remain 1080x760.
    view_w, view_h = 1080, 760

    cx, cy = 705, 298
    outer = 238
    zodiac_inner = 214
    house_ring = 183
    planet_ring = 168
    aspect_ring = 132

    bg = "#f7f4ed"
    ink = "#171717"
    grid = "#b9b2a6"
    border = "#c9b994"

    element_colors = {
        "Feuer": "#D24A43",
        "Erde": "#5B8A4B",
        "Luft": "#C99A36",
        "Wasser": "#4477BB",
    }

    modality_colors = {
        "Kardinal": "#D24A43",
        "Fix": "#4477BB",
        "Veränderlich": "#5B8A4B",
    }

    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {view_w} {view_h}" preserveAspectRatio="xMidYMid meet">',
        f'<rect width="100%" height="100%" fill="{bg}"/>',
        """
<defs>
    <radialGradient id="paperGlow" cx="58%" cy="38%" r="70%">
        <stop offset="0%" stop-color="#fffdf7" stop-opacity="0.95"/>
        <stop offset="70%" stop-color="#f7f4ed" stop-opacity="1"/>
        <stop offset="100%" stop-color="#efe8d9" stop-opacity="1"/>
    </radialGradient>
    <filter id="softShadow" x="-30%" y="-30%" width="160%" height="160%">
        <feDropShadow dx="0" dy="2" stdDeviation="2.5" flood-color="#7a6b52" flood-opacity="0.18"/>
    </filter>
    <filter id="tinyGlow" x="-50%" y="-50%" width="200%" height="200%">
        <feDropShadow dx="0" dy="0" stdDeviation="1.2" flood-color="#ffffff" flood-opacity="0.9"/>
    </filter>
    <filter id="lineGlow" x="-20%" y="-20%" width="140%" height="140%">
        <feGaussianBlur stdDeviation="0.15" result="blur"/>
        <feMerge>
            <feMergeNode in="blur"/>
            <feMergeNode in="SourceGraphic"/>
        </feMerge>
    </filter>
</defs>
""",
        '<rect width="100%" height="100%" fill="url(#paperGlow)" opacity="0.72"/>'
    ]

    # Header
    svg.append(svg_text(18, 28, "DEIN KOSMOGRAMM", 16, weight="750", fill=ink))
    svg.append(svg_text(18, 47, "Geburtshoroskop", 10, fill=ink))
    svg.append(svg_text(18, 76, chart["display_birth"], 8.2))
    svg.append(svg_text(18, 91, chart["display_place"], 8.2))
    svg.append(svg_text(18, 106, f'{chart["coordinates"]["latitude"]:.5f}° N / {chart["coordinates"]["longitude"]:.5f}° E', 8.0))

    # Wheel base with shadow.
    svg.append(svg_circle(cx, cy, outer + 0.5, fill="none", stroke="#b8aa91", width=0.9, opacity=0.55, extra='filter="url(#softShadow)"'))
    svg.append(svg_circle(cx, cy, outer, stroke="#343434", width=1.35))
    svg.append(svg_circle(cx, cy, zodiac_inner, stroke=grid, width=0.75))
    svg.append(svg_circle(cx, cy, house_ring, stroke=grid, width=0.75))
    svg.append(svg_circle(cx, cy, aspect_ring, stroke="#ddd5c7", width=0.65))

    # Zodiac ring
    for i, (_, glyph, element, _, color) in enumerate(ZODIAC):
        lon = i * 30
        angle = angle_for_longitude(lon)

        x1, y1 = polar(cx, cy, zodiac_inner, angle)
        x2, y2 = polar(cx, cy, outer, angle)
        svg.append(svg_line(x1, y1, x2, y2, grid, 0.75))

        mid = angle_for_longitude(lon + 15)
        tx, ty = polar(cx, cy, 226, mid)
        svg.append(svg_symbol(tx, ty + 8, glyph, 22, fill=color, extra='filter="url(#tinyGlow)"'))

    # Degree ticks
    for d in range(360):
        angle = angle_for_longitude(d)
        r2 = outer - (7 if d % 10 == 0 else 3)
        x1, y1 = polar(cx, cy, outer, angle)
        x2, y2 = polar(cx, cy, r2, angle)
        svg.append(svg_line(x1, y1, x2, y2, "#c8c0b1", 0.34, 0.95))

    # Houses and numbers
    houses = chart["houses_raw"]
    for i, cusp in enumerate(houses):
        angle = angle_for_longitude(cusp)
        x1, y1 = polar(cx, cy, aspect_ring, angle)
        x2, y2 = polar(cx, cy, outer, angle)

        is_axis = i in [0, 3, 6, 9]
        svg.append(svg_line(x1, y1, x2, y2, "#222" if is_axis else grid, 1.15 if is_axis else 0.65, 1 if is_axis else 0.88))

        next_cusp = houses[(i + 1) % 12]
        mid = cusp + ((next_cusp - cusp) % 360) / 2
        tx, ty = polar(cx, cy, 150, angle_for_longitude(mid))
        svg.append(svg_text(tx, ty + 3, str(i + 1), 9.0, anchor="middle", fill="#666"))

    # Axes
    asc = chart["ascendant"]["longitude"]
    mc = chart["mc"]["longitude"]
    axes = [
        ("AC", asc),
        ("DC", norm_deg(asc + 180)),
        ("MC", mc),
        ("IC", norm_deg(mc + 180)),
    ]

    for label, lon in axes:
        angle = angle_for_longitude(lon)

        x1, y1 = polar(cx, cy, aspect_ring, angle)
        x2, y2 = polar(cx, cy, outer + 4, angle)
        tx, ty = polar(cx, cy, outer + 16, angle)

        svg.append(svg_line(x1, y1, x2, y2, "#111", 1.35))
        # White underprint for readability.
        svg.append(svg_text(tx, ty + 4, label, 10.5, anchor="middle", weight="800", fill="#fff", extra='stroke="#fff" stroke-width="3"'))
        svg.append(svg_text(tx, ty + 4, label, 9.5, anchor="middle", weight="800", fill="#111", extra='filter="url(#tinyGlow)"'))

    # Aspect lines with intelligent layer radii and density adaptation.
    planet_positions = {p["planet"]: p["longitude"] for p in chart["planets"]}
    drawable_aspects = [a for a in chart["aspects"] if a["aspect"] != "Konjunktion"]
    density = len(drawable_aspects)

    # Draw weaker/outer aspects first; exact/tight ones last.
    sorted_aspects = sorted(drawable_aspects, key=lambda a: (a["layer"], -a["orb"]))

    for idx, asp in enumerate(sorted_aspects):
        lon1 = planet_positions[asp["p1"]]
        lon2 = planet_positions[asp["p2"]]

        radius = aspect_layer_radius(asp, aspect_ring, idx, density)
        radius = max(88, min(aspect_ring + 4, radius))

        a1 = angle_for_longitude(lon1)
        a2 = angle_for_longitude(lon2)

        x1, y1 = polar(cx, cy, radius, a1)
        x2, y2 = polar(cx, cy, radius, a2)

        # Tight aspects slightly stronger.
        exactness_boost = max(0.0, 1.0 - (asp["orb"] / 6.0))
        stroke = asp["stroke"] + exactness_boost * 0.25
        opacity = min(0.86, asp["opacity"] + exactness_boost * 0.08)

        svg.append(svg_line(
            x1, y1, x2, y2,
            asp["color"],
            round(stroke, 2),
            round(opacity, 2),
            extra='filter="url(#lineGlow)" stroke-linecap="round"'
        ))

    # Premium planet layout
    axis_lons = [asc, norm_deg(asc + 180), mc, norm_deg(mc + 180)]
    nodes = force_directed_planet_layout(chart["planets"], cx, cy, planet_ring, axis_lons)

    for node in nodes:
        p = node.planet
        true_lon = node.true_lon
        display_lon = node.display_lon
        r = planet_ring - node.radius_offset
        angle = angle_for_longitude(display_lon)

        px, py = polar(cx, cy, r, angle)
        _, _, _, _, _, _, deg = sign_data(true_lon)

        glyph_size = 21 if p["planet"] in ["Sonne", "Mond"] else 20
        svg.append(svg_symbol(px, py, p["glyph"], glyph_size, fill="#111", extra='filter="url(#tinyGlow)"'))
        svg.append(svg_text(px, py + 14, deg_to_dms(deg), 7.6, anchor="middle", fill="#333"))

        # Leader line if displayed position deviates.
        if angular_diff(true_lon, display_lon) > 1.2 or node.radius_offset > 16:
            tx, ty = polar(cx, cy, max(78, r - 18), angle_for_longitude(true_lon))
            svg.append(svg_line(px, py + 3, tx, ty, "#8d8476", 0.42, 0.50, extra='stroke-linecap="round"'))

    # Left column
    x, y = 18, 145
    svg.append(svg_text(x, y, "PLANETEN IM ZEICHEN", 9, weight="750"))
    y += 14

    for p in chart["planets"]:
        retro = " ℞" if p["retrograde"] else ""
        svg.append(svg_text(x, y, f'{p["glyph"]} {p["planet"]}: {p["sign"]} {deg_to_dms(p["degree"])}{retro}', 7.8))
        y += 13.5

    y += 10
    svg.append(svg_text(x, y, "HÄUSER (Placidus)", 9, weight="750"))
    y += 14

    roman = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]

    for i, h in enumerate(chart["houses_raw"]):
        _, sign, _, _, _, _, deg = sign_data(h)
        svg.append(svg_text(x, y, f'{roman[i]}  {sign} {deg_to_dms(deg)}', 7.8))
        y += 13.5

    # Bottom cards
    core_y = 575
    bottom_y = 575

    card_extra = 'filter="url(#softShadow)"'
    svg.append(svg_rect(15, core_y, 210, 130, stroke=border, rx=7, extra=card_extra))
    svg.append(svg_text(28, core_y + 18, "KERNPUNKTE", 9, weight="750"))
    svg.append(svg_text(28, core_y + 38, f'Aszendent: {chart["ascendant"]["sign"]} {deg_to_dms(chart["ascendant"]["degree"])}', 7.5))
    svg.append(svg_text(28, core_y + 54, f'MC: {chart["mc"]["sign"]} {deg_to_dms(chart["mc"]["degree"])}', 7.5))
    svg.append(svg_text(28, core_y + 70, f'UTC: {chart["utc_time"][:16]}', 7.5))
    svg.append(svg_text(28, core_y + 86, f'Zeitzone: {chart["timezone"]}', 7.5))
    svg.append(svg_text(28, core_y + 102, f'Quelle Ort: {chart["location_source"]}', 7.5))
    svg.append(svg_text(28, core_y + 118, f'Ephemeride: {chart["ephemeris_engine"]}', 7.5))

    asp_x = 250
    svg.append(svg_rect(asp_x, bottom_y, 310, 145, stroke=border, rx=7, extra=card_extra))
    svg.append(svg_text(asp_x + 14, bottom_y + 18, "WICHTIGE ASPEKTE", 9, weight="750"))

    yy = bottom_y + 36
    # Show exact aspects first in box.
    box_aspects = sorted(chart["aspects"], key=lambda a: a["orb"])[:9]
    for asp in box_aspects:
        svg.append(svg_text(asp_x + 14, yy, f'{asp["p1"]} {asp["aspect"]} {asp["p2"]} — Orb {asp["orb"]}°', 7.4))
        yy += 12

    stat_x = 585
    svg.append(svg_rect(stat_x, bottom_y, 170, 145, stroke=border, rx=7, extra=card_extra))
    svg.append(svg_text(stat_x + 14, bottom_y + 18, "ELEMENTE", 9, weight="750"))
    svg.append(svg_pie(stat_x + 42, bottom_y + 60, 22, chart["elements"], element_colors))

    yy = bottom_y + 38
    for key, val in chart["elements"].items():
        svg.append(svg_text(stat_x + 78, yy, f"{key}: {val}", 7.5))
        yy += 14

    yy = bottom_y + 98
    svg.append(svg_text(stat_x + 14, yy, "MODALITÄTEN", 9, weight="750"))
    svg.append(svg_pie(stat_x + 42, bottom_y + 125, 20, chart["modalities"], modality_colors))

    yy += 18
    for key, val in chart["modalities"].items():
        svg.append(svg_text(stat_x + 78, yy, f"{key}: {val}", 7.5))
        yy += 14

    interp_x = 780
    svg.append(svg_rect(interp_x, bottom_y, 270, 145, stroke=border, rx=7, extra=card_extra))
    svg.append(svg_text(interp_x + 14, bottom_y + 18, "KURZINTERPRETATION", 9, weight="750"))

    sun = chart["planets"][0]
    svg.append(svg_text(interp_x + 14, bottom_y + 42, f'Sonne in {sun["sign"]}', 7.5))
    svg.append(svg_text(interp_x + 14, bottom_y + 58, f'Aszendent in {chart["ascendant"]["sign"]}', 7.5))
    svg.append(svg_text(interp_x + 14, bottom_y + 74, f'MC in {chart["mc"]["sign"]}', 7.5))
    svg.append(svg_text(interp_x + 14, bottom_y + 104, "Deutung nur auf Basis", 7.5))
    svg.append(svg_text(interp_x + 14, bottom_y + 118, "der berechneten Daten.", 7.5))

    svg.append(svg_rect(245, 735, 610, 20, stroke=border, rx=5))
    svg.append(svg_text(550, 748, "Berechnung: tropischer Tierkreis, Placidus-Häuser. Genauigkeit abhängig von Zeit, Ort, Zeitzone und Ephemeriden.", 7.0, anchor="middle"))

    svg.append("</svg>")
    return "".join(svg)


# ============================================================
# LOCATION + CHART BUILDING
# ============================================================

def resolve_location(data: BirthData):
    normalized_place = data.birth_place.strip().lower()

    if data.latitude is not None and data.longitude is not None:
        timezone_name = data.timezone or tf.timezone_at(lat=data.latitude, lng=data.longitude)

        if not timezone_name:
            return {"success": False, "error": "Timezone not found for provided coordinates."}

        return {
            "success": True,
            "latitude": data.latitude,
            "longitude": data.longitude,
            "timezone": timezone_name,
            "source": "user_coordinates",
            "precision": "exact_if_birthplace_coordinates_are_exact",
        }

    if normalized_place in AMBIGUOUS_PLACES:
        return {
            "success": False,
            "error": "Geburtsort ist mehrdeutig. Bitte exakte Koordinaten übergeben: latitude, longitude und optional timezone."
        }

    try:
        location = geolocator.geocode(f"{data.birth_place}, {data.country}", timeout=10, exactly_one=True)
    except Exception:
        location = None

    if not location:
        return {"success": False, "error": "Location lookup failed. Please provide exact coordinates."}

    timezone_name = tf.timezone_at(lat=location.latitude, lng=location.longitude)

    if not timezone_name:
        return {"success": False, "error": "Timezone not found. Please provide timezone manually."}

    return {
        "success": True,
        "latitude": location.latitude,
        "longitude": location.longitude,
        "timezone": timezone_name,
        "source": "geopy_nominatim",
        "precision": "geocoder_result_review_recommended",
    }


def build_chart(data: BirthData):
    location = resolve_location(data)

    if not location["success"]:
        return location

    latitude = location["latitude"]
    longitude = location["longitude"]
    timezone_name = location["timezone"]

    local_tz = pytz.timezone(timezone_name)

    try:
        local_datetime = local_tz.localize(
            datetime.strptime(f"{data.birth_date} {data.birth_time}", "%Y-%m-%d %H:%M"),
            is_dst=None,
        )
    except Exception:
        return {"success": False, "error": "Invalid or ambiguous local birth time."}

    utc_datetime = local_datetime.astimezone(pytz.utc)

    julian_day = swe.julday(
        utc_datetime.year,
        utc_datetime.month,
        utc_datetime.day,
        utc_datetime.hour + utc_datetime.minute / 60.0 + utc_datetime.second / 3600.0,
    )

    try:
        houses, ascmc = swe.houses(julian_day, latitude, longitude, b"P")
    except Exception as exc:
        return {"success": False, "error": f"House calculation failed: {exc}"}

    houses_raw = [norm_deg(x) for x in houses]

    planet_results = []
    points = {}
    ephemeris_engines = set()

    for planet_name, (planet_id, glyph, _priority) in PLANETS.items():
        planet_data, engine = calculate_planet_position(julian_day, planet_id)
        ephemeris_engines.add(engine)

        planet_longitude = norm_deg(planet_data[0])
        retrograde = planet_data[3] < 0

        _, sign, sign_glyph, element, modality, _color, degree = sign_data(planet_longitude)
        house = find_house(planet_longitude, houses_raw)

        planet_results.append({
            "planet": planet_name,
            "glyph": glyph,
            "sign": sign,
            "sign_glyph": sign_glyph,
            "degree": round(degree, 4),
            "longitude": round(planet_longitude, 4),
            "house": house,
            "retrograde": retrograde,
            "element": element,
            "modality": modality,
            "ephemeris_engine": engine,
        })

        points[planet_name] = planet_longitude

    ascendant = norm_deg(ascmc[0])
    mc = norm_deg(ascmc[1])

    _, asc_sign, asc_glyph, _, _, _, asc_degree = sign_data(ascendant)
    _, mc_sign, mc_glyph, _, _, _, mc_degree = sign_data(mc)

    element_counts = {"Feuer": 0, "Erde": 0, "Luft": 0, "Wasser": 0}
    modality_counts = {"Kardinal": 0, "Fix": 0, "Veränderlich": 0}

    # Classical balance usually counts 10 planets, not node.
    for p in planet_results[:10]:
        element_counts[p["element"]] += 1
        modality_counts[p["modality"]] += 1

    chart = {
        "success": True,
        "input": data.model_dump(),
        "display_birth": f"{data.birth_date} um {data.birth_time} Uhr",
        "display_place": f"{data.birth_place}, {data.country}",
        "coordinates": {"latitude": latitude, "longitude": longitude},
        "location_source": location["source"],
        "location_precision": location["precision"],
        "timezone": timezone_name,
        "utc_time": utc_datetime.isoformat(),
        "julian_day": julian_day,
        "zodiac": "tropical",
        "house_system": "Placidus",
        "ephemeris_engine": ", ".join(sorted(ephemeris_engines)),
        "accuracy_note": "Accuracy depends on exact birth time, coordinates, timezone database and ephemeris availability.",
        "ascendant": {
            "sign": asc_sign,
            "glyph": asc_glyph,
            "degree": round(asc_degree, 4),
            "longitude": round(ascendant, 4),
        },
        "mc": {
            "sign": mc_sign,
            "glyph": mc_glyph,
            "degree": round(mc_degree, 4),
            "longitude": round(mc, 4),
        },
        "planets": planet_results,
        "houses": [
            {
                "house": i + 1,
                "longitude": round(h, 4),
                "sign": sign_data(h)[1],
                "degree": round(sign_data(h)[6], 4),
            }
            for i, h in enumerate(houses_raw)
        ],
        "houses_raw": houses_raw,
        "aspects": calculate_aspects(points),
        "elements": element_counts,
        "modalities": modality_counts,
    }

    chart["cosmogram_svg"] = generate_professional_cosmogram_svg(chart)
    return chart


# ============================================================
# ENDPOINTS
# ============================================================

@app.get("/")
def root():
    return {"status": "online", "service": "Astralytica Premium API", "version": "4.0.0"}


@app.post("/calculate-birth-chart")
def calculate_birth_chart(data: BirthData):
    return build_chart(data)


@app.get("/cosmogram.png")
def get_cosmogram_png(
    birth_date: str,
    birth_time: str,
    birth_place: str,
    country: str,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    timezone: Optional[str] = None,
    width: int = 1200,
    height: int = 900,
):
    data = BirthData(
        birth_date=birth_date,
        birth_time=birth_time,
        birth_place=birth_place,
        country=country,
        latitude=latitude,
        longitude=longitude,
        timezone=timezone,
    )

    result = build_chart(data)

    if not result.get("success"):
        message = safe_text(result.get("error", "Calculation failed"))
        error_svg = (
            f"<svg xmlns='http://www.w3.org/2000/svg' width='900' height='160'>"
            f"<text x='20' y='50' font-size='18'>{message}</text></svg>"
        )
        png_bytes = cairosvg.svg2png(bytestring=error_svg.encode("utf-8"))
        return Response(content=png_bytes, media_type="image/png")

    svg = generate_professional_cosmogram_svg(result, width=width, height=height)
    png_bytes = cairosvg.svg2png(bytestring=svg.encode("utf-8"))

    return Response(content=png_bytes, media_type="image/png")
