from fastapi import FastAPI, Response
from pydantic import BaseModel
from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder
from datetime import datetime
from typing import Optional
from html import escape
import pytz
import swisseph as swe
import math

app = FastAPI()

geolocator = Nominatim(user_agent="astralytica")
tf = TimezoneFinder()

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
    "Chiron": (swe.CHIRON, "⚷"),
    "Nordknoten": (swe.MEAN_NODE, "☊"),
}

ASPECTS = [
    ("Konjunktion", 0, 8, "#555555"),
    ("Sextil", 60, 5, "#4A90E2"),
    ("Quadrat", 90, 6, "#D64545"),
    ("Trigon", 120, 6, "#4A90E2"),
    ("Opposition", 180, 8, "#D64545"),
]


class BirthData(BaseModel):
    birth_date: str
    birth_time: str
    birth_place: str
    country: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    timezone: Optional[str] = None


def deg_to_dms(deg):
    d = int(deg)
    m = int(round((deg - d) * 60))
    if m == 60:
        d += 1
        m = 0
    return f"{d}°{m:02d}'"


def norm_deg(x):
    return x % 360


def sign_data(longitude):
    lon = norm_deg(longitude)
    idx = int(lon // 30)
    degree = lon % 30
    name, glyph, element, modality = ZODIAC[idx]
    return idx, name, glyph, element, modality, degree


def angle_for_longitude(longitude):
    return math.radians(180 - longitude)


def polar(cx, cy, r, angle):
    return cx + r * math.cos(angle), cy + r * math.sin(angle)


def angular_diff(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)


def point_on_arc(start, end, value):
    start = norm_deg(start)
    end = norm_deg(end)
    value = norm_deg(value)
    if end < start:
        end += 360
    if value < start:
        value += 360
    return start <= value < end


def find_house(longitude, houses):
    for i in range(12):
        start = houses[i]
        end = houses[(i + 1) % 12]
        if point_on_arc(start, end, longitude):
            return i + 1
    return None


def calculate_aspects(points):
    aspects = []
    names = list(points.keys())

    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a = points[names[i]]
            b = points[names[j]]
            diff = angular_diff(a, b)

            for aspect_name, exact, orb_limit, color in ASPECTS:
                orb = abs(diff - exact)
                if orb <= orb_limit:
                    aspects.append({
                        "p1": names[i],
                        "p2": names[j],
                        "aspect": aspect_name,
                        "angle": round(diff, 2),
                        "orb": round(orb, 2),
                        "color": color,
                    })
                    break

    return aspects


def safe_text(x):
    return escape(str(x))


def svg_text(x, y, text, size=12, anchor="start", weight="normal", fill="#222"):
    return (
        f'<text x="{x}" y="{y}" font-size="{size}" '
        f'text-anchor="{anchor}" font-family="Georgia, DejaVu Serif, serif" '
        f'font-weight="{weight}" fill="{fill}">{safe_text(text)}</text>'
    )


def svg_line(x1, y1, x2, y2, color="#222", width=1, opacity=1):
    return (
        f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
        f'stroke="{color}" stroke-width="{width}" opacity="{opacity}"/>'
    )


def svg_circle(cx, cy, r, fill="none", stroke="#222", width=1, opacity=1):
    return (
        f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="{width}" opacity="{opacity}"/>'
    )


def generate_professional_cosmogram_svg(chart):
    width = 1200
    height = 1200

    cx = 720
    cy = 420

    outer = 355
    zodiac_inner = 315
    house_ring = 285
    planet_ring = 250
    aspect_ring = 200

    svg = []
    svg.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">'
    )
    svg.append('<rect width="100%" height="100%" fill="#fbf7ef"/>')

    svg.append(svg_text(40, 40, "DEIN KOSMOGRAMM", 22, weight="bold"))
    svg.append(svg_text(40, 65, "Geburtshoroskop", 15))
    svg.append(svg_text(40, 100, chart["display_birth"], 13))
    svg.append(svg_text(40, 120, chart["display_place"], 13))
    svg.append(svg_text(40, 140, f'{chart["coordinates"]["latitude"]:.4f}° N / {chart["coordinates"]["longitude"]:.4f}° E', 12))

    # Main rings
    svg.append(svg_circle(cx, cy, outer, stroke="#444", width=2))
    svg.append(svg_circle(cx, cy, zodiac_inner, stroke="#aaa", width=1))
    svg.append(svg_circle(cx, cy, house_ring, stroke="#aaa", width=1))
    svg.append(svg_circle(cx, cy, aspect_ring, stroke="#ddd", width=1))

    # Zodiac signs and zodiac separators
    for i, (name, glyph, element, modality) in enumerate(ZODIAC):
        lon = i * 30
        angle = angle_for_longitude(lon)
        x1, y1 = polar(cx, cy, zodiac_inner, angle)
        x2, y2 = polar(cx, cy, outer, angle)
        svg.append(svg_line(x1, y1, x2, y2, "#999", 1))

        mid_angle = angle_for_longitude(lon + 15)
        tx, ty = polar(cx, cy, 338, mid_angle)

        color = {
            "Feuer": "#D64545",
            "Erde": "#5A8F43",
            "Luft": "#D6A33A",
            "Wasser": "#357ABD",
        }[element]

        svg.append(svg_text(tx, ty + 8, glyph, 32, anchor="middle", fill=color))

    # Degree tick marks
    for d in range(360):
        angle = angle_for_longitude(d)
        r1 = outer
        r2 = outer - (10 if d % 10 == 0 else 5)
        x1, y1 = polar(cx, cy, r1, angle)
        x2, y2 = polar(cx, cy, r2, angle)
        svg.append(svg_line(x1, y1, x2, y2, "#bbb", 0.6))

    # Houses
    houses = chart["houses_raw"]
    for i, cusp in enumerate(houses):
        angle = angle_for_longitude(cusp)
        x1, y1 = polar(cx, cy, aspect_ring, angle)
        x2, y2 = polar(cx, cy, outer, angle)

        width_line = 2 if i in [0, 3, 6, 9] else 1
        color = "#333" if i in [0, 3, 6, 9] else "#aaa"
        svg.append(svg_line(x1, y1, x2, y2, color, width_line))

        next_cusp = houses[(i + 1) % 12]
        mid = cusp + ((next_cusp - cusp) % 360) / 2
        tx, ty = polar(cx, cy, 230, angle_for_longitude(mid))
        svg.append(svg_text(tx, ty + 5, str(i + 1), 13, anchor="middle", fill="#777"))

    # AC/DC/MC/IC
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
        x, y = polar(cx, cy, outer + 18, angle)
        x1, y1 = polar(cx, cy, aspect_ring, angle)
        x2, y2 = polar(cx, cy, outer + 8, angle)
        svg.append(svg_line(x1, y1, x2, y2, "#111", 2))
        svg.append(svg_text(x, y + 5, label, 15, anchor="middle", weight="bold", fill="#111"))

    # Aspects
    planet_positions = {p["planet"]: p["longitude"] for p in chart["planets"]}
    for asp in chart["aspects"]:
        if asp["aspect"] == "Konjunktion":
            continue

        a1 = angle_for_longitude(planet_positions[asp["p1"]])
        a2 = angle_for_longitude(planet_positions[asp["p2"]])
        x1, y1 = polar(cx, cy, aspect_ring, a1)
        x2, y2 = polar(cx, cy, aspect_ring, a2)
        svg.append(svg_line(x1, y1, x2, y2, asp["color"], 1.2, 0.72))

    # Planets with simple collision offset
    placed = []
    glyph_map = {k: v[1] for k, v in PLANETS.items()}

    for p in chart["planets"]:
        angle = angle_for_longitude(p["longitude"])
        base_r = planet_ring

        px, py = polar(cx, cy, base_r, angle)

        offset = 0
        for ox, oy in placed:
            if abs(px - ox) < 34 and abs(py - oy) < 24:
                offset += 22

        px, py = polar(cx, cy, base_r - offset, angle)
        placed.append((px, py))

        glyph = glyph_map.get(p["planet"], p["planet"])
        _, _, _, _, _, deg = sign_data(p["longitude"])

        svg.append(svg_text(px, py, glyph, 25, anchor="middle", fill="#111"))
        svg.append(svg_text(px, py + 18, deg_to_dms(deg), 10, anchor="middle", fill="#333"))

    # Left table: planets
    table_x = 40
    y = 190
    svg.append(svg_text(table_x, y, "PLANETEN IM ZEICHEN", 13, weight="bold"))
    y += 18

    for p in chart["planets"]:
        glyph = glyph_map.get(p["planet"], "")
        retro = " ℞" if p["retrograde"] else ""
        line = f'{glyph} {p["planet"]}: {p["sign"]} {deg_to_dms(p["degree"])}{retro}'
        svg.append(svg_text(table_x, y, line, 11))
        y += 16

    # Houses table
    y += 18
    svg.append(svg_text(table_x, y, "HÄUSER (Placidus)", 13, weight="bold"))
    y += 18

    roman = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]
    for i, h in enumerate(chart["houses_raw"]):
        _, sign, _, _, _, deg = sign_data(h)
        svg.append(svg_text(table_x, y, f'{roman[i]}  {sign} {deg_to_dms(deg)}', 11))
        y += 16

    # Info box
    box_y = 650
    svg.append(f'<rect x="35" y="{box_y}" width="260" height="155" fill="#fffdf8" stroke="#d4c6aa" rx="8"/>')
    svg.append(svg_text(50, box_y + 25, "KERNPUNKTE", 13, weight="bold"))
    svg.append(svg_text(50, box_y + 50, f'Aszendent: {chart["ascendant"]["sign"]} {deg_to_dms(chart["ascendant"]["degree"])}', 11))
    svg.append(svg_text(50, box_y + 70, f'MC: {chart["mc"]["sign"]} {deg_to_dms(chart["mc"]["degree"])}', 11))
    svg.append(svg_text(50, box_y + 90, f'UTC: {chart["utc_time"][:16]}', 11))
    svg.append(svg_text(50, box_y + 110, f'Zeitzone: {chart["timezone"]}', 11))
    svg.append(svg_text(50, box_y + 130, "Tierkreis: tropisch", 11))

    # Aspects box
    asp_x = 330
    asp_y = 845
    svg.append(f'<rect x="{asp_x}" y="{asp_y}" width="310" height="240" fill="#fffdf8" stroke="#d4c6aa" rx="8"/>')
    svg.append(svg_text(asp_x + 15, asp_y + 25, "WICHTIGE ASPEKTE", 13, weight="bold"))

    yy = asp_y + 50
    for asp in chart["aspects"][:11]:
        line = f'{asp["p1"]} {asp["aspect"]} {asp["p2"]} — Orb {asp["orb"]}°'
        svg.append(svg_text(asp_x + 15, yy, line, 10))
        yy += 17

    # Element/modalities boxes
    stat_x = 670
    stat_y = 845
    svg.append(f'<rect x="{stat_x}" y="{stat_y}" width="210" height="240" fill="#fffdf8" stroke="#d4c6aa" rx="8"/>')
    svg.append(svg_text(stat_x + 15, stat_y + 25, "ELEMENTE", 13, weight="bold"))
    yy = stat_y + 52
    for key, val in chart["elements"].items():
        svg.append(svg_text(stat_x + 20, yy, f"{key}: {val}", 11))
        yy += 22

    yy += 15
    svg.append(svg_text(stat_x + 15, yy, "MODALITÄTEN", 13, weight="bold"))
    yy += 25
    for key, val in chart["modalities"].items():
        svg.append(svg_text(stat_x + 20, yy, f"{key}: {val}", 11))
        yy += 22

    # Interpretation placeholder
    interp_x = 910
    interp_y = 845
    svg.append(f'<rect x="{interp_x}" y="{interp_y}" width="250" height="240" fill="#fffdf8" stroke="#d4c6aa" rx="8"/>')
    svg.append(svg_text(interp_x + 15, interp_y + 25, "KURZINTERPRETATION", 13, weight="bold"))
    svg.append(svg_text(interp_x + 15, interp_y + 55, f'Sonne in {chart["planets"][0]["sign"]}', 11))
    svg.append(svg_text(interp_x + 15, interp_y + 75, f'Aszendent in {chart["ascendant"]["sign"]}', 11))
    svg.append(svg_text(interp_x + 15, interp_y + 95, f'MC in {chart["mc"]["sign"]}', 11))
    svg.append(svg_text(interp_x + 15, interp_y + 125, "Die Deutung erfolgt", 11))
    svg.append(svg_text(interp_x + 15, interp_y + 143, "datenbasiert aus den", 11))
    svg.append(svg_text(interp_x + 15, interp_y + 161, "berechneten Positionen.", 11))

    svg.append(f'<rect x="270" y="1120" width="660" height="35" fill="#fffdf8" stroke="#d4c6aa" rx="8"/>')
    svg.append(svg_text(600, 1142, "Dieses Kosmogramm wurde aus berechneten astronomischen Daten erzeugt.", 12, anchor="middle"))

    svg.append("</svg>")
    return "".join(svg)


def build_chart(data: BirthData):
    fallback_locations = {
        "tschuj,kyrgyzstan": {
            "latitude": 42.7483142,
            "longitude": 75.0421531,
            "timezone": "Asia/Bishkek"
        },
        "chuy,kyrgyzstan": {
            "latitude": 42.7483142,
            "longitude": 75.0421531,
            "timezone": "Asia/Bishkek"
        }
    }

    if data.latitude is not None and data.longitude is not None:
        latitude = data.latitude
        longitude = data.longitude
        timezone_name = data.timezone or tf.timezone_at(lat=latitude, lng=longitude)
    else:
        location_query = f"{data.birth_place}, {data.country}"
        location_key = f"{data.birth_place},{data.country}".lower().replace(" ", "")

        try:
            location = geolocator.geocode(location_query, timeout=10)
        except Exception:
            location = None

        if location:
            latitude = location.latitude
            longitude = location.longitude
            timezone_name = tf.timezone_at(lat=latitude, lng=longitude)
        elif location_key in fallback_locations:
            latitude = fallback_locations[location_key]["latitude"]
            longitude = fallback_locations[location_key]["longitude"]
            timezone_name = fallback_locations[location_key]["timezone"]
        else:
            return {
                "success": False,
                "error": "Location lookup failed. Please provide coordinates manually."
            }

    if not timezone_name:
        return {
            "success": False,
            "error": "Timezone not found."
        }

    local_tz = pytz.timezone(timezone_name)
    local_datetime = local_tz.localize(
        datetime.strptime(f"{data.birth_date} {data.birth_time}", "%Y-%m-%d %H:%M")
    )
    utc_datetime = local_datetime.astimezone(pytz.utc)

    julian_day = swe.julday(
        utc_datetime.year,
        utc_datetime.month,
        utc_datetime.day,
        utc_datetime.hour + utc_datetime.minute / 60.0
    )

    houses, ascmc = swe.houses(julian_day, latitude, longitude, b'P')
    houses_raw = [norm_deg(x) for x in houses]

    planet_results = []
    points = {}

    for planet_name, planet_info in PLANETS.items():
        planet_id, glyph = planet_info
        planet_data = swe.calc_ut(julian_day, planet_id)[0]

        planet_longitude = norm_deg(planet_data[0])
        retrograde = planet_data[3] < 0
        idx, sign, sign_glyph, element, modality, degree = sign_data(planet_longitude)
        house = find_house(planet_longitude, houses_raw)

        planet_results.append({
            "planet": planet_name,
            "glyph": glyph,
            "sign": sign,
            "sign_glyph": sign_glyph,
            "degree": round(degree, 2),
            "longitude": round(planet_longitude, 2),
            "house": house,
            "retrograde": retrograde,
            "element": element,
            "modality": modality
        })

        points[planet_name] = planet_longitude

    ascendant = norm_deg(ascmc[0])
    mc = norm_deg(ascmc[1])

    _, asc_sign, asc_glyph, _, _, asc_degree = sign_data(ascendant)
    _, mc_sign, mc_glyph, _, _, mc_degree = sign_data(mc)

    aspects = calculate_aspects(points)

    element_counts = {"Feuer": 0, "Erde": 0, "Luft": 0, "Wasser": 0}
    modality_counts = {"Kardinal": 0, "Fix": 0, "Veränderlich": 0}

    for p in planet_results[:10]:
        element_counts[p["element"]] += 1
        modality_counts[p["modality"]] += 1

    chart = {
        "success": True,
        "input": data.dict(),
        "display_birth": f'{data.birth_date} um {data.birth_time} Uhr',
        "display_place": f'{data.birth_place}, {data.country}',
        "coordinates": {
            "latitude": latitude,
            "longitude": longitude
        },
        "timezone": timezone_name,
        "utc_time": utc_datetime.isoformat(),
        "julian_day": julian_day,
        "zodiac": "tropical",
        "house_system": "Placidus",
        "ascendant": {
            "sign": asc_sign,
            "glyph": asc_glyph,
            "degree": round(asc_degree, 2),
            "longitude": round(ascendant, 2)
        },
        "mc": {
            "sign": mc_sign,
            "glyph": mc_glyph,
            "degree": round(mc_degree, 2),
            "longitude": round(mc, 2)
        },
        "planets": planet_results,
        "houses": [
            {
                "house": i + 1,
                "longitude": round(h, 2),
                "sign": sign_data(h)[1],
                "degree": round(sign_data(h)[5], 2)
            }
            for i, h in enumerate(houses_raw)
        ],
        "houses_raw": houses_raw,
        "aspects": aspects,
        "elements": element_counts,
        "modalities": modality_counts,
    }

    chart["cosmogram_svg"] = generate_professional_cosmogram_svg(chart)
    return chart


@app.get("/")
def root():
    return {
        "status": "online",
        "service": "Astralytica Professional API"
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
    timezone: Optional[str] = None
):
    data = BirthData(
        birth_date=birth_date,
        birth_time=birth_time,
        birth_place=birth_place,
        country=country,
        latitude=latitude,
        longitude=longitude,
        timezone=timezone
    )

    result = build_chart(data)

    if not result.get("success"):
        return Response(
            content="<svg xmlns='http://www.w3.org/2000/svg'><text x='20' y='40'>Calculation failed</text></svg>",
            media_type="image/svg+xml"
        )

    return Response(
        content=result["cosmogram_svg"],
        media_type="image/svg+xml"
    )
