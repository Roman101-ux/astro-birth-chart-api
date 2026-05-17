from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from uuid import uuid4
from html import escape
from typing import Dict, List, Optional, Tuple

import math
import pytz
import swisseph as swe
from fastapi import FastAPI, Response
from fastapi.staticfiles import StaticFiles
from geopy.geocoders import Nominatim
from pydantic import BaseModel
from timezonefinder import TimezoneFinder
from fastapi.responses import HTMLResponse

try:
    import cairosvg
except Exception:
    cairosvg = None

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
except Exception:
    A4 = None
    getSampleStyleSheet = None
    ParagraphStyle = None
    cm = None
    SimpleDocTemplate = None
    Paragraph = None
    Spacer = None
    Image = None


BASE_URL = "https://astro-birth-chart-api.onrender.com"
REPORT_DIR = Path("reports")
REPORT_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Astralytica Birth Chart API", version="2.0.0")
app.mount("/reports", StaticFiles(directory=str(REPORT_DIR)), name="reports")

geolocator = Nominatim(user_agent="astralytica_birth_chart_api")
timezone_finder = TimezoneFinder()


ZODIAC = [
    ("Widder", "♈", "Feuer", "Kardinal"),
    ("Stier", "♉", "Erde", "Fix"),
    ("Zwillinge", "♊", "Luft", "Veränderlich"),
    ("Krebs", "♋", "Wasser", "Kardinal"),
    ("Löwe", "♌", "Feuer", "Fix"),
    ("Jungfrau", "♍", "Erde", "Veränderlich"),
    ("Waage", "♎", "Luft", "Kardinal"),
    ("Skorpion", "♏", "Wasser", "Fix"),
    ("Schütze", "♐", "Feuer", "Veränderlich"),
    ("Steinbock", "♑", "Erde", "Kardinal"),
    ("Wassermann", "♒", "Luft", "Fix"),
    ("Fische", "♓", "Wasser", "Veränderlich"),
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
    ("Konjunktion", 0, 8, "#777777", 0),
    ("Sextil", 60, 5, "#4F8FE8", 6),
    ("Quadrat", 90, 6, "#D85C5C", 12),
    ("Trigon", 120, 6, "#4F8FE8", 18),
    ("Opposition", 180, 8, "#C74747", 24),
]

ELEMENT_COLORS = {
    "Feuer": "#D24A43",
    "Erde": "#5B8A4B",
    "Luft": "#C99A36",
    "Wasser": "#4477BB",
}

MODALITY_COLORS = {
    "Kardinal": "#D24A43",
    "Fix": "#4477BB",
    "Veränderlich": "#5B8A4B",
}


class BirthData(BaseModel):
    birth_date: str
    birth_time: str
    birth_place: str
    country: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    timezone: Optional[str] = None


def norm_deg(value: float) -> float:
    return value % 360.0


def deg_to_dms(degree_value: float) -> str:
    degrees = int(degree_value)
    minutes = int(round((degree_value - degrees) * 60))

    if minutes == 60:
        degrees += 1
        minutes = 0

    return f"{degrees}°{minutes:02d}'"


def sign_data(longitude: float):
    longitude = norm_deg(longitude)
    sign_index = int(longitude // 30)
    degree = longitude % 30
    name, glyph, element, modality = ZODIAC[sign_index]
    return sign_index, name, glyph, element, modality, degree


def angle_for_longitude(longitude: float) -> float:
    return math.radians(180 - longitude)


def polar(cx: float, cy: float, radius: float, angle: float) -> Tuple[float, float]:
    return cx + radius * math.cos(angle), cy + radius * math.sin(angle)


def angular_diff(a: float, b: float) -> float:
    diff = abs(a - b) % 360
    return min(diff, 360 - diff)


def point_on_arc(start: float, end: float, value: float) -> bool:
    start = norm_deg(start)
    end = norm_deg(end)
    value = norm_deg(value)

    if end < start:
        end += 360
    if value < start:
        value += 360

    return start <= value < end


def find_house(longitude: float, houses: List[float]) -> Optional[int]:
    for index in range(12):
        if point_on_arc(houses[index], houses[(index + 1) % 12], longitude):
            return index + 1
    return None


def safe_text(value) -> str:
    return escape(str(value))


def svg_text(
    x,
    y,
    text,
    size=9,
    anchor="start",
    weight="400",
    fill="#222",
    opacity=1,
) -> str:
    return (
        f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="{anchor}" '
        f'font-family="Inter, Arial, Helvetica, DejaVu Sans, sans-serif" '
        f'font-weight="{weight}" fill="{fill}" opacity="{opacity}">'
        f"{safe_text(text)}</text>"
    )


def svg_symbol(
    x,
    y,
    text,
    size=18,
    anchor="middle",
    fill="#111",
    opacity=1,
) -> str:
    return (
        f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="{anchor}" '
        f'font-family="DejaVu Serif, Noto Sans Symbols, Arial Unicode MS, serif" '
        f'font-weight="500" fill="{fill}" opacity="{opacity}">'
        f"{safe_text(text)}</text>"
    )


def svg_line(x1, y1, x2, y2, color="#222", width=1, opacity=1) -> str:
    return (
        f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
        f'stroke="{color}" stroke-width="{width}" opacity="{opacity}" '
        f'stroke-linecap="round"/>'
    )


def svg_circle(cx, cy, radius, fill="none", stroke="#222", width=1, opacity=1) -> str:
    return (
        f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{radius:.2f}" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="{width}" opacity="{opacity}"/>'
    )


def svg_pie(cx, cy, radius, values: Dict[str, int], colors: Dict[str, str]) -> str:
    total = sum(values.values())
    if total <= 0:
        return ""

    output = []
    start_angle = -90

    for key, value in values.items():
        if value <= 0:
            continue

        sweep = 360 * value / total
        end_angle = start_angle + sweep

        a1 = math.radians(start_angle)
        a2 = math.radians(end_angle)

        x1 = cx + radius * math.cos(a1)
        y1 = cy + radius * math.sin(a1)
        x2 = cx + radius * math.cos(a2)
        y2 = cy + radius * math.sin(a2)

        large_arc = 1 if sweep > 180 else 0

        output.append(
            f'<path d="M {cx} {cy} L {x1:.2f} {y1:.2f} '
            f'A {radius} {radius} 0 {large_arc} 1 {x2:.2f} {y2:.2f} Z" '
            f'fill="{colors.get(key, "#999")}" opacity="0.92"/>'
        )

        start_angle = end_angle

    output.append(svg_circle(cx, cy, radius, stroke="#ddd", width=0.6))
    return "".join(output)


def calculate_planet_position(julian_day: float, planet_id: int):
    try:
        planet_data = swe.calc_ut(
            julian_day,
            planet_id,
            swe.FLG_SWIEPH | swe.FLG_SPEED,
        )[0]
        return planet_data, "swiss_ephemeris"
    except Exception:
        planet_data = swe.calc_ut(
            julian_day,
            planet_id,
            swe.FLG_MOSEPH | swe.FLG_SPEED,
        )[0]
        return planet_data, "moshier_fallback"


def calculate_aspects(points: Dict[str, float]):
    aspects = []
    names = list(points.keys())

    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            p1 = names[i]
            p2 = names[j]
            angle = angular_diff(points[p1], points[p2])

            for aspect_name, exact, orb_limit, color, layer_offset in ASPECTS:
                orb = abs(angle - exact)

                if orb <= orb_limit:
                    aspects.append(
                        {
                            "p1": p1,
                            "p2": p2,
                            "aspect": aspect_name,
                            "angle": round(angle, 2),
                            "orb": round(orb, 2),
                            "color": color,
                            "layer_offset": layer_offset,
                        }
                    )
                    break

    return sorted(aspects, key=lambda item: (item["aspect"] != "Konjunktion", item["orb"]))


def resolve_location(data: BirthData):
    if data.latitude is not None and data.longitude is not None:
        timezone_name = data.timezone or timezone_finder.timezone_at(
            lat=data.latitude,
            lng=data.longitude,
        )

        if not timezone_name:
            return {
                "success": False,
                "error": "Timezone not found for provided coordinates.",
            }

        return {
            "success": True,
            "latitude": float(data.latitude),
            "longitude": float(data.longitude),
            "timezone": timezone_name,
            "source": "user_coordinates",
            "precision": "exact_if_birthplace_coordinates_are_exact",
            "display_name": f"{data.birth_place}, {data.country}",
        }

    query = f"{data.birth_place}, {data.country}"

    try:
        location = geolocator.geocode(
            query,
            timeout=10,
            exactly_one=True,
            addressdetails=False,
        )
    except Exception as error:
        return {
            "success": False,
            "error": f"Location lookup failed: {str(error)}",
        }

    if not location:
        return {
            "success": False,
            "error": f"Location not found for: {query}. Please provide coordinates.",
        }

    timezone_name = timezone_finder.timezone_at(
        lat=location.latitude,
        lng=location.longitude,
    )

    if not timezone_name:
        return {
            "success": False,
            "error": "Timezone not found. Please provide timezone manually.",
        }

    return {
        "success": True,
        "latitude": float(location.latitude),
        "longitude": float(location.longitude),
        "timezone": timezone_name,
        "source": "geopy_nominatim",
        "precision": "automatic_geocoding_review_recommended",
        "display_name": getattr(location, "address", query),
    }


def spread_planets_force(
    planets,
    base_radius,
    cx,
    cy,
    axes_lons=None,
    min_gap_px=26,
    iterations=120,
):
    axes_lons = axes_lons or []
    items = []

    for planet in sorted(planets, key=lambda item: item["longitude"]):
        placed = planet.copy()
        placed["display_longitude"] = planet["longitude"]
        placed["display_radius"] = base_radius
        items.append(placed)

    cluster = []
    clusters = []

    def flush_cluster(values):
        if values:
            clusters.append(values[:])

    for planet in items:
        if not cluster:
            cluster = [planet]
        elif angular_diff(cluster[-1]["longitude"], planet["longitude"]) < 9:
            cluster.append(planet)
        else:
            flush_cluster(cluster)
            cluster = [planet]

    flush_cluster(cluster)

    for cluster_items in clusters:
        count = len(cluster_items)
        if count <= 1:
            continue

        center = sum(item["longitude"] for item in cluster_items) / count
        spread = min(46, max(22, count * 9.0))
        start = center - spread / 2

        for index, planet in enumerate(cluster_items):
            planet["display_longitude"] = norm_deg(
                start + index * (spread / max(count - 1, 1))
            )
            planet["display_radius"] = base_radius - (index % 3) * 13

    for _ in range(iterations):
        moved = False

        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                angle_i = angle_for_longitude(items[i]["display_longitude"])
                angle_j = angle_for_longitude(items[j]["display_longitude"])

                xi, yi = polar(cx, cy, items[i]["display_radius"], angle_i)
                xj, yj = polar(cx, cy, items[j]["display_radius"], angle_j)

                distance = max(0.001, math.hypot(xi - xj, yi - yj))

                if distance < min_gap_px:
                    push = (min_gap_px - distance) / min_gap_px
                    direction = (
                        1
                        if items[i]["display_longitude"] - items[j]["display_longitude"] >= 0
                        else -1
                    )

                    items[i]["display_longitude"] = norm_deg(
                        items[i]["display_longitude"] + direction * push * 0.55
                    )
                    items[j]["display_longitude"] = norm_deg(
                        items[j]["display_longitude"] - direction * push * 0.55
                    )

                    items[i]["display_radius"] = max(
                        base_radius - 44,
                        items[i]["display_radius"] - push * 2.5,
                    )
                    items[j]["display_radius"] = max(
                        base_radius - 44,
                        items[j]["display_radius"] - push * 2.5,
                    )

                    moved = True

        for planet in items:
            for axis_longitude in axes_lons:
                diff = ((planet["display_longitude"] - axis_longitude + 180) % 360) - 180

                if abs(diff) < 5.5:
                    planet["display_longitude"] = norm_deg(
                        planet["display_longitude"] + (1 if diff >= 0 else -1) * 0.75
                    )
                    moved = True

        if not moved:
            break

    return items


def generate_professional_cosmogram_svg(chart, width: int = 1080, height: int = 760) -> str:
    sx = width / 1080.0
    sy = height / 760.0
    scale = min(sx, sy)

    def x_scale(value):
        return value * sx

    def y_scale(value):
        return value * sy

    def size_scale(value):
        return value * scale

    cx = x_scale(705)
    cy = y_scale(298)

    outer = size_scale(238)
    zodiac_inner = size_scale(214)
    house_ring = size_scale(183)
    planet_ring = size_scale(166)
    aspect_ring = size_scale(120)

    grid = "#b9b2a6"
    border = "#c9b994"

    svg = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" preserveAspectRatio="xMidYMid meet">'
        ),
        """
<defs>
  <radialGradient id="paperGlow" cx="50%" cy="40%" r="70%">
    <stop offset="0%" stop-color="#fffdf8"/>
    <stop offset="100%" stop-color="#f2eadb"/>
  </radialGradient>
  <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
    <feDropShadow dx="0" dy="1.4" stdDeviation="1.9" flood-opacity="0.13"/>
  </filter>
</defs>
""",
        '<rect width="100%" height="100%" fill="url(#paperGlow)"/>',
    ]

    svg.append(svg_text(x_scale(18), y_scale(28), "DEIN KOSMOGRAMM", size_scale(16), weight="700", fill="#171717"))
    svg.append(svg_text(x_scale(18), y_scale(46), "Geburtshoroskop", size_scale(10)))
    svg.append(svg_text(x_scale(18), y_scale(76), chart["display_birth"], size_scale(8)))
    svg.append(svg_text(x_scale(18), y_scale(90), chart["display_place"], size_scale(8)))
    svg.append(
        svg_text(
            x_scale(18),
            y_scale(104),
            f'{chart["coordinates"]["latitude"]:.5f}° / {chart["coordinates"]["longitude"]:.5f}°',
            size_scale(8),
        )
    )

    for radius, color, stroke_width in [
        (outer, "#3d3d3d", 1.45),
        (zodiac_inner, grid, 0.8),
        (house_ring, grid, 0.8),
        (aspect_ring, "#ddd5c7", 0.65),
    ]:
        svg.append(svg_circle(cx, cy, radius, stroke=color, width=size_scale(stroke_width)))

    for index, (_, glyph, element, _) in enumerate(ZODIAC):
        longitude = index * 30
        angle = angle_for_longitude(longitude)

        x1, y1 = polar(cx, cy, zodiac_inner, angle)
        x2, y2 = polar(cx, cy, outer, angle)
        svg.append(svg_line(x1, y1, x2, y2, grid, size_scale(0.8)))

        tx, ty = polar(cx, cy, size_scale(228), angle_for_longitude(longitude + 15))
        svg.append(
            svg_symbol(
                tx,
                ty + size_scale(8),
                glyph,
                size_scale(23),
                fill=ELEMENT_COLORS[element],
            )
        )

    for degree in range(360):
        angle = angle_for_longitude(degree)
        tick_radius = outer - size_scale(7 if degree % 10 == 0 else 3)
        x1, y1 = polar(cx, cy, outer, angle)
        x2, y2 = polar(cx, cy, tick_radius, angle)
        svg.append(svg_line(x1, y1, x2, y2, "#c8c0b1", size_scale(0.35)))

    houses = chart["houses_raw"]

    for index, cusp in enumerate(houses):
        angle = angle_for_longitude(cusp)
        x1, y1 = polar(cx, cy, aspect_ring, angle)
        x2, y2 = polar(cx, cy, outer, angle)

        is_axis = index in [0, 3, 6, 9]
        svg.append(
            svg_line(
                x1,
                y1,
                x2,
                y2,
                "#222" if is_axis else grid,
                size_scale(1.2 if is_axis else 0.7),
            )
        )

        next_cusp = houses[(index + 1) % 12]
        midpoint = cusp + ((next_cusp - cusp) % 360) / 2
        tx, ty = polar(cx, cy, size_scale(150), angle_for_longitude(midpoint))

        svg.append(
            svg_text(
                tx,
                ty + size_scale(3),
                str(index + 1),
                size_scale(9.5),
                anchor="middle",
                fill="#666",
                opacity=0.72,
            )
        )

    asc = chart["ascendant"]["longitude"]
    mc = chart["mc"]["longitude"]

    axes = [
        ("AC", asc),
        ("DC", norm_deg(asc + 180)),
        ("MC", mc),
        ("IC", norm_deg(mc + 180)),
    ]

    for label, longitude in axes:
        angle = angle_for_longitude(longitude)
        x1, y1 = polar(cx, cy, aspect_ring, angle)
        x2, y2 = polar(cx, cy, outer + size_scale(4), angle)
        tx, ty = polar(cx, cy, outer + size_scale(16), angle)

        svg.append(svg_line(x1, y1, x2, y2, "#111", size_scale(1.25)))
        svg.append(
            svg_text(
                tx,
                ty + size_scale(4),
                label,
                size_scale(9.5),
                anchor="middle",
                weight="700",
                fill="#111",
            )
        )

    planet_positions = {planet["planet"]: planet["longitude"] for planet in chart["planets"]}
    visible_aspects = [
        aspect for aspect in chart["aspects"] if aspect["aspect"] != "Konjunktion"
    ]

    density = min(0.18, max(0, (len(visible_aspects) - 8) * 0.015))

    for index, aspect in enumerate(visible_aspects):
        angle_1 = angle_for_longitude(planet_positions[aspect["p1"]])
        angle_2 = angle_for_longitude(planet_positions[aspect["p2"]])

        offset = (index % 4) * size_scale(1.4) + size_scale(aspect.get("layer_offset", 0) * 0.18)
        radius = aspect_ring - offset

        x1, y1 = polar(cx, cy, radius, angle_1)
        x2, y2 = polar(cx, cy, radius, angle_2)

        svg.append(
            svg_line(
                x1,
                y1,
                x2,
                y2,
                aspect["color"],
                size_scale(0.95 if aspect["aspect"] in ["Sextil", "Trigon"] else 1.05),
                max(0.42, 0.66 - density),
            )
        )

    display_planets = spread_planets_force(
        chart["planets"],
        planet_ring,
        cx,
        cy,
        [longitude for _, longitude in axes],
        min_gap_px=size_scale(27),
    )

    for planet in display_planets:
        true_longitude = planet["longitude"]
        display_longitude = planet["display_longitude"]
        display_radius = planet.get("display_radius", planet_ring)

        angle = angle_for_longitude(display_longitude)
        px, py = polar(cx, cy, display_radius, angle)
        _, _, _, _, _, degree = sign_data(true_longitude)

        svg.append(svg_symbol(px, py, planet["glyph"], size_scale(21), fill="#111"))
        svg.append(
            svg_text(
                px,
                py + size_scale(14),
                deg_to_dms(degree),
                size_scale(7.7),
                anchor="middle",
                fill="#333",
            )
        )

        if angular_diff(true_longitude, display_longitude) > 1.4:
            tx, ty = polar(
                cx,
                cy,
                display_radius - size_scale(18),
                angle_for_longitude(true_longitude),
            )
            svg.append(
                svg_line(px, py + size_scale(3), tx, ty, "#888", size_scale(0.45), 0.52)
            )

    left_x = x_scale(18)
    current_y = y_scale(145)

    svg.append(
        svg_text(left_x, current_y, "PLANETEN IM ZEICHEN", size_scale(9), weight="700")
    )
    current_y += size_scale(14)

    for planet in chart["planets"]:
        retrograde = " ℞" if planet["retrograde"] else ""
        svg.append(
            svg_text(
                left_x,
                current_y,
                f'{planet["glyph"]} {planet["planet"]}: {planet["sign"]} '
                f'{deg_to_dms(planet["degree"])}{retrograde}',
                size_scale(7.9),
            )
        )
        current_y += size_scale(14)

    current_y += size_scale(10)
    svg.append(svg_text(left_x, current_y, "HÄUSER (Placidus)", size_scale(9), weight="700"))
    current_y += size_scale(14)

    roman = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]

    for index, house_longitude in enumerate(chart["houses_raw"]):
        _, sign, _, _, _, degree = sign_data(house_longitude)
        svg.append(
            svg_text(
                left_x,
                current_y,
                f"{roman[index]}  {sign} {deg_to_dms(degree)}",
                size_scale(7.9),
            )
        )
        current_y += size_scale(14)

    card_y = y_scale(575)

    def card_rect(x, y, w, h):
        return (
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" '
            f'fill="#fffdf8" stroke="{border}" rx="{size_scale(6)}" '
            f'filter="url(#shadow)"/>'
        )

    svg.append(card_rect(x_scale(15), card_y, size_scale(210), size_scale(130)))
    svg.append(svg_text(x_scale(28), card_y + size_scale(18), "KERNPUNKTE", size_scale(9), weight="700"))

    core_rows = [
        (38, f'Aszendent: {chart["ascendant"]["sign"]} {deg_to_dms(chart["ascendant"]["degree"])}'),
        (54, f'MC: {chart["mc"]["sign"]} {deg_to_dms(chart["mc"]["degree"])}'),
        (70, f'UTC: {chart["utc_time"][:16]}'),
        (86, f'Zeitzone: {chart["timezone"]}'),
        (102, f'Quelle Ort: {chart["location_source"]}'),
        (118, f'Ephemeride: {chart["ephemeris_engine"]}'),
    ]

    for offset_y, text in core_rows:
        svg.append(svg_text(x_scale(28), card_y + size_scale(offset_y), text, size_scale(7.5)))

    aspect_x = x_scale(250)

    svg.append(card_rect(aspect_x, card_y, size_scale(310), size_scale(145)))
    svg.append(svg_text(aspect_x + size_scale(14), card_y + size_scale(18), "WICHTIGE ASPEKTE", size_scale(9), weight="700"))

    aspect_y = card_y + size_scale(36)

    for aspect in chart["aspects"][:9]:
        svg.append(
            svg_text(
                aspect_x + size_scale(14),
                aspect_y,
                f'{aspect["p1"]} {aspect["aspect"]} {aspect["p2"]} — Orb {aspect["orb"]}°',
                size_scale(7.45),
            )
        )
        aspect_y += size_scale(12)

    stats_x = x_scale(585)

    svg.append(card_rect(stats_x, card_y, size_scale(170), size_scale(145)))
    svg.append(svg_text(stats_x + size_scale(14), card_y + size_scale(18), "ELEMENTE", size_scale(9), weight="700"))
    svg.append(
        svg_pie(
            stats_x + size_scale(42),
            card_y + size_scale(60),
            size_scale(22),
            chart["elements"],
            ELEMENT_COLORS,
        )
    )

    row_y = card_y + size_scale(38)

    for key, value in chart["elements"].items():
        svg.append(svg_text(stats_x + size_scale(78), row_y, f"{key}: {value}", size_scale(7.5)))
        row_y += size_scale(14)

    row_y = card_y + size_scale(98)
    svg.append(svg_text(stats_x + size_scale(14), row_y, "MODALITÄTEN", size_scale(9), weight="700"))
    svg.append(
        svg_pie(
            stats_x + size_scale(42),
            card_y + size_scale(125),
            size_scale(20),
            chart["modalities"],
            MODALITY_COLORS,
        )
    )

    row_y += size_scale(18)

    for key, value in chart["modalities"].items():
        svg.append(svg_text(stats_x + size_scale(78), row_y, f"{key}: {value}", size_scale(7.5)))
        row_y += size_scale(14)

    interpretation_x = x_scale(780)

    svg.append(card_rect(interpretation_x, card_y, size_scale(270), size_scale(145)))
    svg.append(
        svg_text(
            interpretation_x + size_scale(14),
            card_y + size_scale(18),
            "KURZINTERPRETATION",
            size_scale(9),
            weight="700",
        )
    )

    sun = chart["planets"][0]

    interpretation_rows = [
        (42, f'Sonne in {sun["sign"]}'),
        (58, f'Aszendent in {chart["ascendant"]["sign"]}'),
        (74, f'MC in {chart["mc"]["sign"]}'),
        (104, "Deutung nur auf Basis"),
        (118, "der berechneten Daten."),
    ]

    for offset_y, text in interpretation_rows:
        svg.append(
            svg_text(
                interpretation_x + size_scale(14),
                card_y + size_scale(offset_y),
                text,
                size_scale(7.5),
            )
        )

    svg.append(
        f'<rect x="{x_scale(245)}" y="{y_scale(735)}" width="{size_scale(610)}" '
        f'height="{size_scale(20)}" fill="#fffdf8" stroke="{border}" '
        f'rx="{size_scale(5)}"/>'
    )
    svg.append(
        svg_text(
            x_scale(550),
            y_scale(748),
            "Berechnung: tropischer Tierkreis, Placidus-Häuser. Genauigkeit abhängig von Zeit, Ort, Zeitzone und Ephemeriden.",
            size_scale(7.2),
            anchor="middle",
        )
    )

    svg.append("</svg>")
    return "".join(svg)


def build_chart(data: BirthData):
    location = resolve_location(data)

    if not location["success"]:
        return location

    latitude = location["latitude"]
    longitude = location["longitude"]
    timezone_name = location["timezone"]

    try:
        local_timezone = pytz.timezone(timezone_name)
    except Exception:
        return {
            "success": False,
            "error": f"Invalid timezone: {timezone_name}",
        }

    try:
        naive_datetime = datetime.strptime(
            f"{data.birth_date} {data.birth_time}",
            "%Y-%m-%d %H:%M",
        )
        local_datetime = local_timezone.localize(naive_datetime, is_dst=None)
    except Exception as error:
        return {
            "success": False,
            "error": f"Invalid or ambiguous local birth time: {str(error)}",
        }

    utc_datetime = local_datetime.astimezone(pytz.utc)

    julian_day = swe.julday(
        utc_datetime.year,
        utc_datetime.month,
        utc_datetime.day,
        utc_datetime.hour + utc_datetime.minute / 60 + utc_datetime.second / 3600,
    )

    try:
        houses, ascmc = swe.houses(julian_day, latitude, longitude, b"P")
    except Exception as error:
        return {
            "success": False,
            "error": f"House calculation failed: {str(error)}",
        }

    houses_raw = [norm_deg(value) for value in houses]

    planet_results = []
    points = {}
    engines = set()

    for planet_name, (planet_id, glyph) in PLANETS.items():
        try:
            planet_data, engine = calculate_planet_position(julian_day, planet_id)
        except Exception as error:
            return {
                "success": False,
                "error": f"Planet calculation failed for {planet_name}: {str(error)}",
            }

        engines.add(engine)

        planet_longitude = norm_deg(planet_data[0])
        retrograde = planet_data[3] < 0

        _, sign, sign_glyph, element, modality, degree = sign_data(planet_longitude)
        house = find_house(planet_longitude, houses_raw)

        planet_results.append(
            {
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
            }
        )

        points[planet_name] = planet_longitude

    ascendant = norm_deg(ascmc[0])
    mc = norm_deg(ascmc[1])

    _, asc_sign, asc_glyph, _, _, asc_degree = sign_data(ascendant)
    _, mc_sign, mc_glyph, _, _, mc_degree = sign_data(mc)

    element_counts = {"Feuer": 0, "Erde": 0, "Luft": 0, "Wasser": 0}
    modality_counts = {"Kardinal": 0, "Fix": 0, "Veränderlich": 0}

    for planet in planet_results[:10]:
        element_counts[planet["element"]] += 1
        modality_counts[planet["modality"]] += 1

    chart = {
        "success": True,
        "input": data.model_dump(),
        "display_birth": f"{data.birth_date} um {data.birth_time} Uhr",
        "display_place": f"{data.birth_place}, {data.country}",
        "coordinates": {
            "latitude": latitude,
            "longitude": longitude,
        },
        "resolved_location_name": location.get("display_name"),
        "location_source": location["source"],
        "location_precision": location["precision"],
        "timezone": timezone_name,
        "utc_time": utc_datetime.isoformat(),
        "julian_day": julian_day,
        "zodiac": "tropical",
        "house_system": "Placidus",
        "ephemeris_engine": ", ".join(sorted(engines)),
        "accuracy_note": (
            "Accuracy depends on exact birth time, exact coordinates, "
            "timezone database and ephemeris availability."
        ),
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
                "house": index + 1,
                "longitude": round(house_longitude, 4),
                "sign": sign_data(house_longitude)[1],
                "degree": round(sign_data(house_longitude)[5], 4),
            }
            for index, house_longitude in enumerate(houses_raw)
        ],
        "houses_raw": houses_raw,
        "aspects": calculate_aspects(points),
        "elements": element_counts,
        "modalities": modality_counts,
    }

    chart["cosmogram_svg"] = generate_professional_cosmogram_svg(chart)
    return chart


@app.get("/")
def root():
    return {
        "status": "online",
        "service": "Astralytica Professional API",
        "endpoints": [
            "/calculate-birth-chart",
            "/cosmogram.svg",
            "/cosmogram.png",
            "/generate-chart",
            "/generate-report-pdf",
            "/chart-view",
        ],
    }


@app.post("/calculate-birth-chart")
def calculate_birth_chart(data: BirthData):
    return build_chart(data)


@app.get("/cosmogram.svg")
def get_cosmogram_svg(
    birth_date: str,
    birth_time: str,
    birth_place: str,
    country: str,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    timezone: Optional[str] = None,
    width: int = 1080,
    height: int = 760,
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
        svg = (
            "<svg xmlns='http://www.w3.org/2000/svg' width='900' height='160'>"
            "<rect width='100%' height='100%' fill='#fffdf8'/>"
            f"<text x='20' y='50' font-size='18' fill='#222'>{message}</text>"
            "</svg>"
        )
        return Response(content=svg, media_type="image/svg+xml")

    svg = generate_professional_cosmogram_svg(result, width, height)
    return Response(content=svg, media_type="image/svg+xml")


@app.get("/cosmogram.png")
def get_cosmogram_png(
    birth_date: str,
    birth_time: str,
    birth_place: str,
    country: str,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    timezone: Optional[str] = None,
    width: int = 1080,
    height: int = 760,
):
    if cairosvg is None:
        message = "CairoSVG is not installed. Add CairoSVG to requirements.txt and redeploy."
        svg = (
            "<svg xmlns='http://www.w3.org/2000/svg' width='900' height='160'>"
            "<rect width='100%' height='100%' fill='#fffdf8'/>"
            f"<text x='20' y='50' font-size='18' fill='#222'>{safe_text(message)}</text>"
            "</svg>"
        )
        return Response(content=svg, media_type="image/svg+xml", status_code=500)

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
        svg = (
            "<svg xmlns='http://www.w3.org/2000/svg' width='900' height='160'>"
            "<rect width='100%' height='100%' fill='#fffdf8'/>"
            f"<text x='20' y='50' font-size='18' fill='#222'>{message}</text>"
            "</svg>"
        )
    else:
        svg = generate_professional_cosmogram_svg(result, width, height)

    png_bytes = cairosvg.svg2png(bytestring=svg.encode("utf-8"))
    return Response(content=png_bytes, media_type="image/png")



def chart_image_url(chart, birth_date, birth_time, birth_place, country, width=1080, height=760):
    query = urlencode(
        {
            "birth_date": birth_date,
            "birth_time": birth_time,
            "birth_place": birth_place,
            "country": country,
            "width": width,
            "height": height,
            "latitude": chart["coordinates"]["latitude"],
            "longitude": chart["coordinates"]["longitude"],
            "timezone": chart["timezone"],
        }
    )
    return f"{BASE_URL}/cosmogram.png?{query}"


def make_analysis_text(chart):
    asc = chart["ascendant"]
    mc = chart["mc"]
    planets = {planet["planet"]: planet for planet in chart["planets"]}

    def planet_line(name):
        planet = planets[name]
        house = f", Haus {planet['house']}" if planet.get("house") else ""
        retrograde = " rückläufig" if planet.get("retrograde") else ""
        return f"{name}: {planet['sign']} {deg_to_dms(planet['degree'])}{house}{retrograde}"

    aspect_lines = "\n".join(
        f"- {aspect['p1']} {aspect['aspect']} {aspect['p2']} — Orb {aspect['orb']}°"
        for aspect in chart["aspects"][:10]
    )

    return f"""Eingabedaten
{chart['display_birth']} · {chart['display_place']}

Kurzprofil
- {planet_line('Sonne')}
- {planet_line('Mond')}
- Aszendent: {asc['sign']} {deg_to_dms(asc['degree'])}
- MC: {mc['sign']} {deg_to_dms(mc['degree'])}

Dominante Struktur
- Elemente: Feuer {chart['elements']['Feuer']}, Erde {chart['elements']['Erde']}, Luft {chart['elements']['Luft']}, Wasser {chart['elements']['Wasser']}
- Modalitäten: Kardinal {chart['modalities']['Kardinal']}, Fix {chart['modalities']['Fix']}, Veränderlich {chart['modalities']['Veränderlich']}

Wichtigste Aspekte
{aspect_lines}

Persönlichkeit & Charakter
Die Grundstruktur spricht astrologisch für eine Kombination aus {planets['Sonne']['sign']}-Sonne, {planets['Mond']['sign']}-Mond und {asc['sign']}-Aszendent. Daraus ergibt sich ein Profil aus bewusster Grundenergie, emotionaler Reaktionsweise und äußerer Wirkung. Die Häuserpositionen zeigen, in welchen Lebensbereichen diese Faktoren besonders aktiv werden.

Karriere & Berufung
Der MC in {mc['sign']} beschreibt die berufliche Entwicklungsrichtung. Merkur, Sonne, Saturn und das 10. Haus zeigen, wie Wissen, Verantwortung, Kommunikation, Struktur und langfristige Zielorientierung beruflich umgesetzt werden können. Die Daten sprechen astrologisch für Potenzial in Bereichen, in denen Analyse, Strategie, Kommunikation, Verantwortung und eigenständige Entwicklung verbunden werden.

Geld & Erfolg
Die Element- und Modalitätsverteilung beschreibt, ob Erfolg eher über Stabilität, Initiative, Anpassung oder Ausdauer entsteht. Die vorhandenen Aspekte zeigen zusätzlich, wo Chancen, Reibung und Wachstumsdruck liegen.

Beziehungen & soziale Dynamik
Venus, Mond, Aszendent und relevante Aspekte zeigen den Stil von Nähe, Bindung, Kommunikation und sozialer Wirkung. Die Deutung bleibt datenbasiert und nicht deterministisch.

Herausforderungen
Spannungsaspekte können auf innere Konflikte, Entwicklungsfelder oder wiederkehrende Muster hinweisen. Sie beschreiben keine festen Ereignisse, sondern astrologische Dynamiken.

Zusammenfassung
Das Horoskop zeigt eine individuelle Gesamtstruktur aus Zeichen, Häusern, Aspekten, Elementen und Modalitäten. Die Analyse basiert ausschließlich auf den berechneten API-Daten.
"""


def create_pdf_report(chart, image_png_bytes):
    if SimpleDocTemplate is None:
        return None

    filename = f"astralytica_report_{uuid4().hex}.pdf"
    pdf_path = REPORT_DIR / filename
    png_path = REPORT_DIR / f"{filename}.png"
    png_path.write_bytes(image_png_bytes)

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="AstralyticaSmall", parent=styles["Normal"], fontSize=9, leading=12))

    document = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )

    story = [
        Paragraph("Astralytica AI — Geburtshoroskop", styles["Title"]),
        Spacer(1, 0.4 * cm),
        Image(str(png_path), width=17 * cm, height=11.96 * cm),
        Spacer(1, 0.5 * cm),
    ]

    for line in make_analysis_text(chart).split("\n"):
        if line.strip():
            story.append(Paragraph(escape(line), styles["AstralyticaSmall"]))
            story.append(Spacer(1, 0.12 * cm))

    document.build(story)
    return f"{BASE_URL}/reports/{filename}"


@app.get("/generate-chart")
def generate_chart(
    birth_date: str,
    birth_time: str,
    birth_place: str,
    country: str,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    timezone: Optional[str] = None,
    width: int = 1080,
    height: int = 760,
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
        return result

    image_url = chart_image_url(result, birth_date, birth_time, birth_place, country, width, height)
    image_markdown = f"![Kosmogramm]({image_url})"

    return {
        "success": True,
        "image_markdown": image_markdown,
        "direct_image_url_for_reference": image_url,
        "birth_date": birth_date,
        "birth_time": birth_time,
        "birth_place": birth_place,
        "country": country,
        "coordinates": result["coordinates"],
        "timezone": result["timezone"],
        "ascendant": result["ascendant"],
        "mc": result["mc"],
        "planets": result["planets"],
        "houses": result["houses"],
        "aspects": result["aspects"],
        "elements": result["elements"],
        "modalities": result["modalities"],
    }


@app.get("/generate-report-pdf")
def generate_report_pdf(
    birth_date: str,
    birth_time: str,
    birth_place: str,
    country: str,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    timezone: Optional[str] = None,
    width: int = 1080,
    height: int = 760,
):
    if cairosvg is None:
        return {"success": False, "error": "CairoSVG is not installed."}
    if SimpleDocTemplate is None:
        return {"success": False, "error": "ReportLab is not installed."}

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
        return result

    svg = generate_professional_cosmogram_svg(result, width, height)
    png_bytes = cairosvg.svg2png(bytestring=svg.encode("utf-8"))

    pdf_url = create_pdf_report(result, png_bytes)

    if not pdf_url:
        return {"success": False, "error": "PDF generation failed."}

    return {
        "success": True,
        "pdf_url": pdf_url,
        "analysis_text": make_analysis_text(result),
    }


@app.get("/chart-view", response_class=HTMLResponse)
def chart_view(
    birth_date: str,
    birth_time: str,
    birth_place: str,
    country: str,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    timezone: Optional[str] = None,
    width: int = 1080,
    height: int = 760,
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
        return (
            "<h2>Die astronomische Berechnung konnte nicht durchgeführt werden.</h2>"
            f"<p>{safe_text(result.get('error'))}</p>"
        )

    image_url = chart_image_url(
        result,
        birth_date,
        birth_time,
        birth_place,
        country,
        width,
        height,
    )

    return f"""
    <!doctype html>
    <html lang="de">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Astralytica Kosmogramm</title>
        <style>
            body {{
                background: #f7f4ed;
                font-family: Arial, sans-serif;
                margin: 0;
                padding: 30px;
                color: #222;
            }}
            .wrap {{
                max-width: 1180px;
                margin: auto;
            }}
            .card {{
                background: #fffdf8;
                padding: 24px;
                border-radius: 16px;
                box-shadow: 0 8px 30px rgba(0,0,0,0.12);
            }}
            img {{
                width: 100%;
                max-width: 1080px;
                border-radius: 12px;
                background: white;
                display: block;
            }}
            h1 {{
                margin-top: 0;
            }}
        </style>
    </head>
    <body>
        <div class="wrap">
            <div class="card">
                <h1>Kosmogramm</h1>
                <p>{safe_text(birth_date)} · {safe_text(birth_time)} · {safe_text(birth_place)}, {safe_text(country)}</p>
                <img src="{image_url}" alt="Kosmogramm">
            </div>
        </div>
    </body>
    </html>
    """
