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

app = FastAPI(title="Astralytica Professional API", version="2.1.0")
geolocator = Nominatim(user_agent="astralytica-professional")
tf = TimezoneFinder()

ZODIAC = [
    ("Widder", "♈", "Feuer", "Kardinal", "#D94A42"),
    ("Stier", "♉", "Erde", "Fix", "#5A8F43"),
    ("Zwillinge", "♊", "Luft", "Veränderlich", "#C99532"),
    ("Krebs", "♋", "Wasser", "Kardinal", "#3E75B8"),
    ("Löwe", "♌", "Feuer", "Fix", "#D94A42"),
    ("Jungfrau", "♍", "Erde", "Veränderlich", "#5A8F43"),
    ("Waage", "♎", "Luft", "Kardinal", "#C99532"),
    ("Skorpion", "♏", "Wasser", "Fix", "#3E75B8"),
    ("Schütze", "♐", "Feuer", "Veränderlich", "#D94A42"),
    ("Steinbock", "♑", "Erde", "Kardinal", "#5A8F43"),
    ("Wassermann", "♒", "Luft", "Fix", "#C99532"),
    ("Fische", "♓", "Wasser", "Veränderlich", "#3E75B8"),
]

PLANETS = {
    "Sonne": (swe.SUN, "☉"),
    "Mond": (swe.MOON, "☽"),
    "Merkur": (swe.MERCURY, "☿"),
    "Venus": (swe.VENUS, "♀"),
    "Mars": (swe.MARS, "♂"),
    "Jupiter": (swe.JUPITER, "♃"),
    "Saturn": (swe.SATURN, "♄"),
    "Uranus": (swe.URANUS, "♅"),
    "Neptun": (swe.NEPTUNE, "♆"),
    "Pluto": (swe.PLUTO, "♇"),
    "Nordknoten": (swe.MEAN_NODE, "☊"),
}

ASPECTS = [
    ("Konjunktion", 0, 8, "#777777", 0, 0.0),
    ("Sextil", 60, 5, "#4F8FE8", 1, 0.95),
    ("Quadrat", 90, 6, "#D85C5C", 3, 1.05),
    ("Trigon", 120, 6, "#4F8FE8", 1, 0.95),
    ("Opposition", 180, 8, "#C74747", 4, 1.10),
]

AMBIGUOUS_PLACES = {"tschuj", "chuy", "chui", "chuy region", "chuy oblast", "tschuj region", "tschuj oblast"}

class BirthData(BaseModel):
    birth_date: str
    birth_time: str
    birth_place: str
    country: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    timezone: Optional[str] = None

class PlanetNode:
    def __init__(self, item: dict, base_radius: float):
        self.item = item
        self.name = item["planet"]
        self.true_lon = item["longitude"]
        self.angle = angle_for_longitude(self.true_lon)
        self.radius = base_radius
        self.target_radius = base_radius
        self.x = 0.0
        self.y = 0.0
        self.vx = 0.0
        self.vy = 0.0
        self.label_w = 34.0
        self.label_h = 30.0

def norm_deg(x: float) -> float:
    return x % 360

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
    return math.radians(180 - longitude)

def longitude_from_angle(angle: float) -> float:
    return norm_deg(180 - math.degrees(angle))

def polar(cx: float, cy: float, r: float, angle: float) -> Tuple[float, float]:
    return cx + r * math.cos(angle), cy + r * math.sin(angle)

def angular_diff(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return min(d, 360 - d)

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

def calculate_aspects(points: Dict[str, float]) -> List[dict]:
    aspects = []
    names = list(points.keys())
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            diff = angular_diff(points[names[i]], points[names[j]])
            for aspect_name, exact, orb_limit, color, layer, strength in ASPECTS:
                orb = abs(diff - exact)
                if orb <= orb_limit:
                    aspects.append({
                        "p1": names[i], "p2": names[j], "aspect": aspect_name,
                        "angle": round(diff, 2), "orb": round(orb, 2),
                        "color": color, "layer": layer, "strength": strength,
                    })
                    break
    return sorted(aspects, key=lambda x: (x["layer"], x["orb"]))

def safe_text(x) -> str:
    return escape(str(x))

def svg_text(x, y, text, size=9, anchor="start", weight="400", fill="#222"):
    return f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="{anchor}" font-family="Inter, Segoe UI, Arial, Helvetica, sans-serif" font-weight="{weight}" fill="{fill}">{safe_text(text)}</text>'

def svg_symbol(x, y, text, size=18, anchor="middle", fill="#111"):
    return f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="{anchor}" font-family="DejaVu Serif, Noto Sans Symbols, Symbola, Arial Unicode MS, serif" font-weight="500" fill="{fill}">{safe_text(text)}</text>'

def svg_line(x1, y1, x2, y2, color="#222", width=1, opacity=1, extra=""):
    return f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" stroke="{color}" stroke-width="{width}" opacity="{opacity}" {extra}/>'

def svg_circle(cx, cy, r, fill="none", stroke="#222", width=1, opacity=1, extra=""):
    return f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}" fill="{fill}" stroke="{stroke}" stroke-width="{width}" opacity="{opacity}" {extra}/>'

def svg_pie(cx, cy, r, values, colors):
    total = sum(values.values())
    if total <= 0:
        return ""
    out = []
    start = -90
    for key, value in values.items():
        if value <= 0:
            continue
        sweep = 360 * value / total
        end = start + sweep
        a1, a2 = math.radians(start), math.radians(end)
        x1, y1 = cx + r * math.cos(a1), cy + r * math.sin(a1)
        x2, y2 = cx + r * math.cos(a2), cy + r * math.sin(a2)
        large = 1 if sweep > 180 else 0
        out.append(f'<path d="M {cx} {cy} L {x1:.2f} {y1:.2f} A {r} {r} 0 {large} 1 {x2:.2f} {y2:.2f} Z" fill="{colors.get(key, "#999")}" opacity="0.94"/>')
        start = end
    out.append(svg_circle(cx, cy, r, stroke="#ddd", width=0.6))
    return "".join(out)

def boxes_overlap(a: PlanetNode, b: PlanetNode) -> Tuple[float, float, float]:
    dx = a.x - b.x
    dy = a.y - b.y
    ox = (a.label_w + b.label_w) / 2 - abs(dx)
    oy = (a.label_h + b.label_h) / 2 - abs(dy)
    if ox > 0 and oy > 0:
        if ox < oy:
            return ox, math.copysign(1.0, dx if dx != 0 else 1.0), 0.0
        return oy, 0.0, math.copysign(1.0, dy if dy != 0 else 1.0)
    return 0.0, 0.0, 0.0

def force_directed_planet_placement(planets: List[dict], cx: float, cy: float, base_radius: float, min_radius: float, max_radius: float, iterations: int = 220) -> Dict[str, dict]:
    nodes = [PlanetNode(p, base_radius) for p in planets]
    for n in nodes:
        n.x, n.y = polar(cx, cy, n.radius, n.angle)

    sorted_nodes = sorted(nodes, key=lambda n: n.true_lon)
    clusters, current = [], []
    for node in sorted_nodes:
        if not current:
            current = [node]
        elif angular_diff(current[-1].true_lon, node.true_lon) < 10:
            current.append(node)
        else:
            clusters.append(current)
            current = [node]
    if current:
        clusters.append(current)

    for cluster in clusters:
        if len(cluster) <= 1:
            continue
        center_lon = sum(n.true_lon for n in cluster) / len(cluster)
        spread = min(46, max(18, len(cluster) * 9.0))
        start_lon = center_lon - spread / 2
        for idx, n in enumerate(cluster):
            display_lon = start_lon + idx * (spread / max(len(cluster) - 1, 1))
            n.angle = angle_for_longitude(display_lon)
            n.radius = base_radius - (idx % 3) * 13
            n.x, n.y = polar(cx, cy, n.radius, n.angle)

    for _ in range(iterations):
        forces = {n.name: [0.0, 0.0] for n in nodes}
        for n in nodes:
            target_x, target_y = polar(cx, cy, n.target_radius, angle_for_longitude(n.true_lon))
            forces[n.name][0] += (target_x - n.x) * 0.018
            forces[n.name][1] += (target_y - n.y) * 0.018
            dx, dy = n.x - cx, n.y - cy
            dist = max(1e-6, math.hypot(dx, dy))
            if dist < min_radius:
                forces[n.name][0] += (dx / dist) * (min_radius - dist) * 0.22
                forces[n.name][1] += (dy / dist) * (min_radius - dist) * 0.22
            elif dist > max_radius:
                forces[n.name][0] -= (dx / dist) * (dist - max_radius) * 0.22
                forces[n.name][1] -= (dy / dist) * (dist - max_radius) * 0.22

        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                a, b = nodes[i], nodes[j]
                overlap, sxn, syn = boxes_overlap(a, b)
                if overlap > 0:
                    push = overlap * 0.38
                    forces[a.name][0] += sxn * push
                    forces[a.name][1] += syn * push
                    forces[b.name][0] -= sxn * push
                    forces[b.name][1] -= syn * push
                ad = angular_diff(a.true_lon, b.true_lon)
                if ad < 12:
                    dx, dy = a.x - b.x, a.y - b.y
                    dist = max(1e-6, math.hypot(dx, dy))
                    push = (12 - ad) * 0.08
                    forces[a.name][0] += dx / dist * push
                    forces[a.name][1] += dy / dist * push
                    forces[b.name][0] -= dx / dist * push
                    forces[b.name][1] -= dy / dist * push

        for n in nodes:
            fx, fy = forces[n.name]
            n.vx = (n.vx + fx) * 0.72
            n.vy = (n.vy + fy) * 0.72
            speed = math.hypot(n.vx, n.vy)
            if speed > 3.0:
                n.vx = n.vx / speed * 3.0
                n.vy = n.vy / speed * 3.0
            n.x += n.vx
            n.y += n.vy
            dx, dy = n.x - cx, n.y - cy
            dist = max(1e-6, math.hypot(dx, dy))
            clamped = min(max(dist, min_radius), max_radius)
            n.x = cx + dx / dist * clamped
            n.y = cy + dy / dist * clamped

    result = {}
    for n in nodes:
        angle = math.atan2(n.y - cy, n.x - cx)
        result[n.name] = {
            "x": n.x,
            "y": n.y,
            "display_longitude": longitude_from_angle(angle),
            "display_radius": math.hypot(n.x - cx, n.y - cy),
            "true_longitude": n.true_lon,
        }
    return result

def calculate_planet_position(julian_day, planet_id):
    try:
        data = swe.calc_ut(julian_day, planet_id, swe.FLG_SWIEPH | swe.FLG_SPEED)[0]
        return data, "swiss_ephemeris"
    except Exception:
        data = swe.calc_ut(julian_day, planet_id, swe.FLG_MOSEPH | swe.FLG_SPEED)[0]
        return data, "moshier_fallback"

def adaptive_aspect_style(aspects: List[dict], asp: dict) -> Tuple[float, float]:
    total = len([a for a in aspects if a["aspect"] != "Konjunktion"])
    if total >= 12:
        base_w, base_opacity = 0.82, 0.48
    elif total >= 8:
        base_w, base_opacity = 0.92, 0.56
    else:
        base_w, base_opacity = 1.05, 0.64
    if asp["aspect"] in ("Quadrat", "Opposition"):
        return base_w + 0.08, min(0.72, base_opacity + 0.06)
    return base_w, base_opacity

def generate_professional_cosmogram_svg(chart, width: int = 1080, height: int = 760):
    scale_x = width / 1080
    scale_y = height / 760
    scale = min(scale_x, scale_y)
    def sx(v): return v * scale_x
    def sy(v): return v * scale_y
    def sr(v): return v * scale

    cx, cy = sx(705), sy(298)
    outer = sr(238)
    zodiac_inner = sr(214)
    house_ring = sr(183)
    planet_ring = sr(166)
    aspect_ring = sr(124)
    planet_min_r = sr(144)
    planet_max_r = sr(184)
    bg, ink, grid, border = "#F7F3EA", "#171717", "#B8B0A1", "#C9B994"
    element_colors = {"Feuer": "#D94A42", "Erde": "#5A8F43", "Luft": "#C99532", "Wasser": "#3E75B8"}
    modality_colors = {"Kardinal": "#D94A42", "Fix": "#3E75B8", "Veränderlich": "#5A8F43"}

    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" preserveAspectRatio="xMidYMid meet">',
        f'<rect width="100%" height="100%" fill="{bg}"/>',
        '''<defs>
<filter id="softShadow" x="-25%" y="-25%" width="150%" height="150%"><feDropShadow dx="0" dy="1.4" stdDeviation="2.2" flood-color="#000" flood-opacity="0.14"/></filter>
<filter id="planetGlow" x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="1.1" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
</defs>'''
    ]

    svg.append(svg_text(sx(18), sy(28), "DEIN KOSMOGRAMM", sr(16), weight="700", fill=ink))
    svg.append(svg_text(sx(18), sy(46), "Geburtshoroskop", sr(10), fill=ink))
    svg.append(svg_text(sx(18), sy(76), chart["display_birth"], sr(8)))
    svg.append(svg_text(sx(18), sy(90), chart["display_place"], sr(8)))
    svg.append(svg_text(sx(18), sy(104), f'{chart["coordinates"]["latitude"]:.5f}° N / {chart["coordinates"]["longitude"]:.5f}° E', sr(8)))

    svg.append(svg_circle(cx, cy, outer, stroke="#333", width=sr(1.45)))
    svg.append(svg_circle(cx, cy, zodiac_inner, stroke=grid, width=sr(0.8)))
    svg.append(svg_circle(cx, cy, house_ring, stroke=grid, width=sr(0.8)))
    svg.append(svg_circle(cx, cy, aspect_ring, stroke="#DDD4C4", width=sr(0.65)))

    for i, (_, glyph, element, _, color) in enumerate(ZODIAC):
        lon = i * 30
        angle = angle_for_longitude(lon)
        x1, y1 = polar(cx, cy, zodiac_inner, angle)
        x2, y2 = polar(cx, cy, outer, angle)
        svg.append(svg_line(x1, y1, x2, y2, grid, sr(0.8)))
        tx, ty = polar(cx, cy, sr(228), angle_for_longitude(lon + 15))
        svg.append(svg_symbol(tx, ty + sr(8), glyph, sr(23), fill=color))

    for d in range(360):
        angle = angle_for_longitude(d)
        r2 = outer - (sr(7) if d % 10 == 0 else sr(3))
        x1, y1 = polar(cx, cy, outer, angle)
        x2, y2 = polar(cx, cy, r2, angle)
        svg.append(svg_line(x1, y1, x2, y2, "#C8C0B1", sr(0.35), 0.9))

    houses = chart["houses_raw"]
    for i, cusp in enumerate(houses):
        angle = angle_for_longitude(cusp)
        x1, y1 = polar(cx, cy, aspect_ring, angle)
        x2, y2 = polar(cx, cy, outer, angle)
        is_axis = i in [0, 3, 6, 9]
        svg.append(svg_line(x1, y1, x2, y2, "#1F1F1F" if is_axis else grid, sr(1.2 if is_axis else 0.7), 1.0 if is_axis else 0.75))
        next_cusp = houses[(i + 1) % 12]
        mid = cusp + ((next_cusp - cusp) % 360) / 2
        tx, ty = polar(cx, cy, sr(150), angle_for_longitude(mid))
        svg.append(svg_text(tx, ty + sr(3), str(i + 1), sr(9.5), anchor="middle", fill="#666"))

    asc, mc = chart["ascendant"]["longitude"], chart["mc"]["longitude"]
    for label, lon in [("AC", asc), ("DC", norm_deg(asc + 180)), ("MC", mc), ("IC", norm_deg(mc + 180))]:
        angle = angle_for_longitude(lon)
        x1, y1 = polar(cx, cy, aspect_ring, angle)
        x2, y2 = polar(cx, cy, outer + sr(4), angle)
        tx, ty = polar(cx, cy, outer + sr(15), angle)
        tx = min(max(tx, sx(390)), sx(1035))
        ty = min(max(ty, sy(38)), sy(555))
        svg.append(svg_line(x1, y1, x2, y2, "#111", sr(1.25)))
        svg.append(svg_text(tx, ty + sr(4), label, sr(9.5), anchor="middle", weight="700", fill="#111"))

    planet_positions = {p["planet"]: p["longitude"] for p in chart["planets"]}
    aspects_to_draw = [a for a in chart["aspects"] if a["aspect"] != "Konjunktion"]
    aspects_to_draw = sorted(aspects_to_draw, key=lambda a: (a["layer"], -a["orb"]))
    for idx, asp in enumerate(aspects_to_draw):
        lon1, lon2 = planet_positions[asp["p1"]], planet_positions[asp["p2"]]
        layer_shift = {"Sextil": 0, "Trigon": 2.0, "Quadrat": 4.0, "Opposition": 6.0}.get(asp["aspect"], 0)
        r = aspect_ring - sr((idx % 4) * 1.25 + layer_shift)
        x1, y1 = polar(cx, cy, r, angle_for_longitude(lon1))
        x2, y2 = polar(cx, cy, r, angle_for_longitude(lon2))
        width_line, opacity = adaptive_aspect_style(aspects_to_draw, asp)
        svg.append(svg_line(x1, y1, x2, y2, asp["color"], sr(width_line), opacity))

    placements = force_directed_planet_placement(chart["planets"], cx, cy, planet_ring, planet_min_r, planet_max_r, iterations=260)
    for p in chart["planets"]:
        placement = placements[p["planet"]]
        px, py = placement["x"], placement["y"]
        _, _, _, _, _, _, deg = sign_data(p["longitude"])
        svg.append(svg_symbol(px, py, p["glyph"], sr(21), fill="#111"))
        svg.append(svg_text(px, py + sr(14), deg_to_dms(deg), sr(7.7), anchor="middle", fill="#333"))
        if angular_diff(p["longitude"], placement["display_longitude"]) > 1.6:
            tx, ty = polar(cx, cy, placement["display_radius"] - sr(18), angle_for_longitude(p["longitude"]))
            svg.append(svg_line(px, py + sr(3), tx, ty, "#888", sr(0.45), 0.55))

    x, y = sx(18), sy(145)
    svg.append(svg_text(x, y, "PLANETEN IM ZEICHEN", sr(9), weight="700")); y += sy(14)
    for p in chart["planets"]:
        retro = " ℞" if p["retrograde"] else ""
        svg.append(svg_text(x, y, f'{p["glyph"]} {p["planet"]}: {p["sign"]} {deg_to_dms(p["degree"])}{retro}', sr(7.9)))
        y += sy(14)
    y += sy(10)
    svg.append(svg_text(x, y, "HÄUSER (Placidus)", sr(9), weight="700")); y += sy(14)
    roman = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]
    for i, h in enumerate(chart["houses_raw"]):
        _, sign, _, _, _, _, deg = sign_data(h)
        svg.append(svg_text(x, y, f'{roman[i]}  {sign} {deg_to_dms(deg)}', sr(7.9)))
        y += sy(14)

    core_y = sy(575); bottom_y = sy(575)
    svg.append(f'<rect x="{sx(15)}" y="{core_y}" width="{sx(210)}" height="{sy(130)}" fill="#FFFDF8" stroke="{border}" rx="{sr(6)}" filter="url(#softShadow)"/>')
    svg.append(svg_text(sx(28), core_y + sy(18), "KERNPUNKTE", sr(9), weight="700"))
    svg.append(svg_text(sx(28), core_y + sy(38), f'Aszendent: {chart["ascendant"]["sign"]} {deg_to_dms(chart["ascendant"]["degree"])}', sr(7.5)))
    svg.append(svg_text(sx(28), core_y + sy(54), f'MC: {chart["mc"]["sign"]} {deg_to_dms(chart["mc"]["degree"])}', sr(7.5)))
    svg.append(svg_text(sx(28), core_y + sy(70), f'UTC: {chart["utc_time"][:16]}', sr(7.5)))
    svg.append(svg_text(sx(28), core_y + sy(86), f'Zeitzone: {chart["timezone"]}', sr(7.5)))
    svg.append(svg_text(sx(28), core_y + sy(102), f'Quelle Ort: {chart["location_source"]}', sr(7.5)))
    svg.append(svg_text(sx(28), core_y + sy(118), f'Ephemeride: {chart["ephemeris_engine"]}', sr(7.5)))

    asp_x = sx(250)
    svg.append(f'<rect x="{asp_x}" y="{bottom_y}" width="{sx(310)}" height="{sy(145)}" fill="#FFFDF8" stroke="{border}" rx="{sr(6)}" filter="url(#softShadow)"/>')
    svg.append(svg_text(asp_x + sx(14), bottom_y + sy(18), "WICHTIGE ASPEKTE", sr(9), weight="700"))
    yy = bottom_y + sy(36)
    for asp in chart["aspects"][:9]:
        svg.append(svg_text(asp_x + sx(14), yy, f'{asp["p1"]} {asp["aspect"]} {asp["p2"]} — Orb {asp["orb"]}°', sr(7.6)))
        yy += sy(12)

    stat_x = sx(585)
    svg.append(f'<rect x="{stat_x}" y="{bottom_y}" width="{sx(170)}" height="{sy(145)}" fill="#FFFDF8" stroke="{border}" rx="{sr(6)}" filter="url(#softShadow)"/>')
    svg.append(svg_text(stat_x + sx(14), bottom_y + sy(18), "ELEMENTE", sr(9), weight="700"))
    svg.append(svg_pie(stat_x + sx(42), bottom_y + sy(60), sr(22), chart["elements"], element_colors))
    yy = bottom_y + sy(38)
    for key, val in chart["elements"].items():
        svg.append(svg_text(stat_x + sx(78), yy, f"{key}: {val}", sr(7.5))); yy += sy(14)
    yy = bottom_y + sy(98)
    svg.append(svg_text(stat_x + sx(14), yy, "MODALITÄTEN", sr(9), weight="700"))
    svg.append(svg_pie(stat_x + sx(42), bottom_y + sy(125), sr(20), chart["modalities"], modality_colors))
    yy += sy(18)
    for key, val in chart["modalities"].items():
        svg.append(svg_text(stat_x + sx(78), yy, f"{key}: {val}", sr(7.5))); yy += sy(14)

    interp_x = sx(780)
    svg.append(f'<rect x="{interp_x}" y="{bottom_y}" width="{sx(270)}" height="{sy(145)}" fill="#FFFDF8" stroke="{border}" rx="{sr(6)}" filter="url(#softShadow)"/>')
    svg.append(svg_text(interp_x + sx(14), bottom_y + sy(18), "KURZINTERPRETATION", sr(9), weight="700"))
    sun = chart["planets"][0]
    svg.append(svg_text(interp_x + sx(14), bottom_y + sy(42), f'Sonne in {sun["sign"]}', sr(7.5)))
    svg.append(svg_text(interp_x + sx(14), bottom_y + sy(58), f'Aszendent in {chart["ascendant"]["sign"]}', sr(7.5)))
    svg.append(svg_text(interp_x + sx(14), bottom_y + sy(74), f'MC in {chart["mc"]["sign"]}', sr(7.5)))
    svg.append(svg_text(interp_x + sx(14), bottom_y + sy(104), "Deutung nur auf Basis", sr(7.5)))
    svg.append(svg_text(interp_x + sx(14), bottom_y + sy(118), "der berechneten Daten.", sr(7.5)))

    svg.append(f'<rect x="{sx(245)}" y="{sy(735)}" width="{sx(610)}" height="{sy(20)}" fill="#FFFDF8" stroke="{border}" rx="{sr(5)}"/>')
    svg.append(svg_text(sx(550), sy(748), "Berechnung: tropischer Tierkreis, Placidus-Häuser. Genauigkeit abhängig von Zeit, Ort, Zeitzone und Ephemeriden.", sr(7.2), anchor="middle"))
    svg.append("</svg>")
    return "".join(svg)

def resolve_location(data: BirthData):
    normalized_place = data.birth_place.strip().lower()
    if data.latitude is not None and data.longitude is not None:
        timezone_name = data.timezone or tf.timezone_at(lat=data.latitude, lng=data.longitude)
        if not timezone_name:
            return {"success": False, "error": "Timezone not found for provided coordinates."}
        return {"success": True, "latitude": data.latitude, "longitude": data.longitude, "timezone": timezone_name, "source": "user_coordinates", "precision": "exact_if_birthplace_coordinates_are_exact"}
    if normalized_place in AMBIGUOUS_PLACES:
        return {"success": False, "error": "Geburtsort ist mehrdeutig. Bitte exakte Koordinaten übergeben: latitude, longitude und optional timezone."}
    try:
        location = geolocator.geocode(f"{data.birth_place}, {data.country}", timeout=10, exactly_one=True)
    except Exception:
        location = None
    if not location:
        return {"success": False, "error": "Location lookup failed. Please provide exact coordinates."}
    timezone_name = tf.timezone_at(lat=location.latitude, lng=location.longitude)
    if not timezone_name:
        return {"success": False, "error": "Timezone not found. Please provide timezone manually."}
    return {"success": True, "latitude": location.latitude, "longitude": location.longitude, "timezone": timezone_name, "source": "geopy_nominatim", "precision": "geocoder_result_review_recommended"}

def build_chart(data: BirthData):
    location = resolve_location(data)
    if not location["success"]:
        return location
    latitude, longitude, timezone_name = location["latitude"], location["longitude"], location["timezone"]
    local_tz = pytz.timezone(timezone_name)
    try:
        local_datetime = local_tz.localize(datetime.strptime(f"{data.birth_date} {data.birth_time}", "%Y-%m-%d %H:%M"), is_dst=None)
    except Exception:
        return {"success": False, "error": "Invalid or ambiguous local birth time."}
    utc_datetime = local_datetime.astimezone(pytz.utc)
    julian_day = swe.julday(utc_datetime.year, utc_datetime.month, utc_datetime.day, utc_datetime.hour + utc_datetime.minute / 60.0 + utc_datetime.second / 3600.0)
    houses, ascmc = swe.houses(julian_day, latitude, longitude, b"P")
    houses_raw = [norm_deg(x) for x in houses]
    planet_results, points, ephemeris_engines = [], {}, set()
    for planet_name, (planet_id, glyph) in PLANETS.items():
        planet_data, engine = calculate_planet_position(julian_day, planet_id)
        ephemeris_engines.add(engine)
        planet_longitude = norm_deg(planet_data[0])
        retrograde = planet_data[3] < 0
        _, sign, sign_glyph, element, modality, _, degree = sign_data(planet_longitude)
        house = find_house(planet_longitude, houses_raw)
        planet_results.append({"planet": planet_name, "glyph": glyph, "sign": sign, "sign_glyph": sign_glyph, "degree": round(degree, 4), "longitude": round(planet_longitude, 4), "house": house, "retrograde": retrograde, "element": element, "modality": modality, "ephemeris_engine": engine})
        points[planet_name] = planet_longitude
    ascendant, mc = norm_deg(ascmc[0]), norm_deg(ascmc[1])
    _, asc_sign, asc_glyph, _, _, _, asc_degree = sign_data(ascendant)
    _, mc_sign, mc_glyph, _, _, _, mc_degree = sign_data(mc)
    element_counts = {"Feuer": 0, "Erde": 0, "Luft": 0, "Wasser": 0}
    modality_counts = {"Kardinal": 0, "Fix": 0, "Veränderlich": 0}
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
        "accuracy_note": "Accuracy depends on exact birth time, exact coordinates, timezone database and ephemeris availability.",
        "ascendant": {"sign": asc_sign, "glyph": asc_glyph, "degree": round(asc_degree, 4), "longitude": round(ascendant, 4)},
        "mc": {"sign": mc_sign, "glyph": mc_glyph, "degree": round(mc_degree, 4), "longitude": round(mc, 4)},
        "planets": planet_results,
        "houses": [{"house": i + 1, "longitude": round(h, 4), "sign": sign_data(h)[1], "degree": round(sign_data(h)[6], 4)} for i, h in enumerate(houses_raw)],
        "houses_raw": houses_raw,
        "aspects": calculate_aspects(points),
        "elements": element_counts,
        "modalities": modality_counts,
    }
    chart["cosmogram_svg"] = generate_professional_cosmogram_svg(chart)
    return chart

@app.get("/")
def root():
    return {"status": "online", "service": "Astralytica Professional API"}

@app.post("/calculate-birth-chart")
def calculate_birth_chart(data: BirthData):
    return build_chart(data)

@app.get("/cosmogram.svg")
def get_cosmogram_svg(birth_date: str, birth_time: str, birth_place: str, country: str, latitude: Optional[float] = None, longitude: Optional[float] = None, timezone: Optional[str] = None, width: Optional[int] = 1080, height: Optional[int] = 760):
    data = BirthData(birth_date=birth_date, birth_time=birth_time, birth_place=birth_place, country=country, latitude=latitude, longitude=longitude, timezone=timezone)
    result = build_chart(data)
    if not result.get("success"):
        message = safe_text(result.get("error", "Calculation failed"))
        return Response(content=f"<svg xmlns='http://www.w3.org/2000/svg' width='900' height='160'><text x='20' y='50' font-size='18'>{message}</text></svg>", media_type="image/svg+xml")
    safe_width = min(max(width or 1080, 720), 2200)
    safe_height = min(max(height or 760, 520), 1600)
    svg = generate_professional_cosmogram_svg(result, width=safe_width, height=safe_height)
    return Response(content=svg, media_type="image/svg+xml")
