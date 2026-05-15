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
    "Nordknoten": (swe.MEAN_NODE, "☊"),
}

ASPECTS = [
    ("Konjunktion", 0, 8, "#777777"),
    ("Sextil", 60, 5, "#6FA8FF"),
    ("Quadrat", 90, 6, "#D95C5C"),
    ("Trigon", 120, 6, "#6FA8FF"),
    ("Opposition", 180, 8, "#C05050"),
]


class BirthData(BaseModel):
    birth_date: str
    birth_time: str
    birth_place: str
    country: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    timezone: Optional[str] = None


def norm_deg(x):
    return x % 360


def deg_to_dms(deg):
    d = int(deg)
    m = int(round((deg - d) * 60))
    if m == 60:
        d += 1
        m = 0
    return f"{d}°{m:02d}'"


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
        if point_on_arc(houses[i], houses[(i + 1) % 12], longitude):
            return i + 1
    return None


def calculate_aspects(points):
    aspects = []
    names = list(points.keys())

    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            diff = angular_diff(points[names[i]], points[names[j]])

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


def svg_text(x, y, text, size=9, anchor="start", weight="normal", fill="#222"):
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
    width = 1080
    height = 760

    cx = 690
    cy = 285

    outer = 245
    zodiac_inner = 222
    house_ring = 190
    planet_ring = 172
    aspect_ring = 118

    bg = "#f7f4ed"
    grid = "#b8b2a7"
    border = "#cdbf9f"

    svg = []
    svg.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">'
    )
    svg.append(f'<rect width="100%" height="100%" fill="{bg}"/>')

    # Header
    svg.append(svg_text(18, 28, "DEIN KOSMOGRAMM", 16, weight="bold"))
    svg.append(svg_text(18, 46, "Geburtshoroskop", 10))
    svg.append(svg_text(18, 76, chart["display_birth"], 8))
    svg.append(svg_text(18, 90, chart["display_place"], 8))
    svg.append(svg_text(18, 104, f'{chart["coordinates"]["latitude"]:.4f}° N / {chart["coordinates"]["longitude"]:.4f}° E', 8))

    # Rings
    svg.append(svg_circle(cx, cy, outer, stroke="#444", width=1.5))
    svg.append(svg_circle(cx, cy, zodiac_inner, stroke=grid, width=0.8))
    svg.append(svg_circle(cx, cy, house_ring, stroke=grid, width=0.8))
    svg.append(svg_circle(cx, cy, aspect_ring, stroke="#ddd5c7", width=0.7))

    # Zodiac separators + glyphs
    for i, (name, glyph, element, modality) in enumerate(ZODIAC):
        lon = i * 30
        angle = angle_for_longitude(lon)

        x1, y1 = polar(cx, cy, zodiac_inner, angle)
        x2, y2 = polar(cx, cy, outer, angle)
        svg.append(svg_line(x1, y1, x2, y2, grid, 0.8))

        mid_angle = angle_for_longitude(lon + 15)
        tx, ty = polar(cx, cy, 236, mid_angle)

        color = {
            "Feuer": "#D24A43",
            "Erde": "#5B8A4B",
            "Luft": "#C99A36",
            "Wasser": "#4477BB",
        }[element]

        svg.append(svg_text(tx, ty + 6, glyph, 20, anchor="middle", fill=color))

    # Degree ticks
    for d in range(360):
        angle = angle_for_longitude(d)
        r1 = outer
        r2 = outer - (7 if d % 10 == 0 else 3)
        x1, y1 = polar(cx, cy, r1, angle)
        x2, y2 = polar(cx, cy, r2, angle)
        svg.append(svg_line(x1, y1, x2, y2, "#c8c0b1", 0.35))

    # Houses
    houses = chart["houses_raw"]
    for i, cusp in enumerate(houses):
        angle = angle_for_longitude(cusp)
        x1, y1 = polar(cx, cy, aspect_ring, angle)
        x2, y2 = polar(cx, cy, outer, angle)

        is_axis = i in [0, 3, 6, 9]
        svg.append(svg_line(x1, y1, x2, y2, "#333" if is_axis else grid, 1.2 if is_axis else 0.7))

        next_cusp = houses[(i + 1) % 12]
        mid = cusp + ((next_cusp - cusp) % 360) / 2
        tx, ty = polar(cx, cy, 154, angle_for_longitude(mid))
        svg.append(svg_text(tx, ty + 3, str(i + 1), 8, anchor="middle", fill="#666"))

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
        x1, y1 = polar(cx, cy, aspect_ring, angle)
        x2, y2 = polar(cx, cy, outer + 12, angle)
        tx, ty = polar(cx, cy, outer + 22, angle)

        svg.append(svg_line(x1, y1, x2, y2, "#111", 1.4))
        svg.append(svg_text(tx, ty + 4, label, 10, anchor="middle", weight="bold", fill="#111"))

    # Aspects
    planet_positions = {p["planet"]: p["longitude"] for p in chart["planets"]}

    for asp in chart["aspects"]:
        if asp["aspect"] == "Konjunktion":
            continue

        a1 = angle_for_longitude(planet_positions[asp["p1"]])
        a2 = angle_for_longitude(planet_positions[asp["p2"]])

        x1, y1 = polar(cx, cy, aspect_ring, a1)
        x2, y2 = polar(cx, cy, aspect_ring, a2)

        svg.append(svg_line(x1, y1, x2, y2, asp["color"], 0.9, 0.65))

    # Planets with collision handling
    placed_angles = []
    glyph_map = {k: v[1] for k, v in PLANETS.items()}

    sorted_planets = sorted(chart["planets"], key=lambda p: p["longitude"])

    for p in sorted_planets:
        lon = p["longitude"]
        angle_deg = lon
        r = planet_ring

        for used in placed_angles:
            if abs((angle_deg - used + 180) % 360 - 180) < 6:
                r -= 18

        placed_angles.append(angle_deg)

        angle = angle_for_longitude(lon)
        px, py = polar(cx, cy, r, angle)

        glyph = glyph_map.get(p["planet"], p["planet"])
        _, _, _, _, _, deg = sign_data(lon)

        svg.append(svg_text(px, py, glyph, 17, anchor="middle", fill="#111"))
        svg.append(svg_text(px, py + 13, deg_to_dms(deg), 7, anchor="middle", fill="#333"))

    # Left tables
    x = 18
    y = 145

    svg.append(svg_text(x, y, "PLANETEN IM ZEICHEN", 9, weight="bold"))
    y += 14

    for p in chart["planets"]:
        retro = " ℞" if p["retrograde"] else ""
        line = f'{p["glyph"]} {p["planet"]}: {p["sign"]} {deg_to_dms(p["degree"])}{retro}'
        svg.append(svg_text(x, y, line, 7.4))
        y += 12

    y += 10
    svg.append(svg_text(x, y, "HÄUSER (Placidus)", 9, weight="bold"))
    y += 14

    roman = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]

    for i, h in enumerate(chart["houses_raw"]):
        _, sign, _, _, _, deg = sign_data(h)
        svg.append(svg_text(x, y, f'{roman[i]}  {sign} {deg_to_dms(deg)}', 7.4))
        y += 12

    # Core box
    core_y = 575
    svg.append(f'<rect x="15" y="{core_y}" width="210" height="115" fill="#fffdf8" stroke="{border}" rx="6"/>')
    svg.append(svg_text(28, core_y + 18, "KERNPUNKTE", 9, weight="bold"))
    svg.append(svg_text(28, core_y + 38, f'Aszendent: {chart["ascendant"]["sign"]} {deg_to_dms(chart["ascendant"]["degree"])}', 7.5))
    svg.append(svg_text(28, core_y + 54, f'MC: {chart["mc"]["sign"]} {deg_to_dms(chart["mc"]["degree"])}', 7.5))
    svg.append(svg_text(28, core_y + 70, f'UTC: {chart["utc_time"][:16]}', 7.5))
    svg.append(svg_text(28, core_y + 86, f'Zeitzone: {chart["timezone"]}', 7.5))
    svg.append(svg_text(28, core_y + 102, "Tierkreis: tropisch", 7.5))

    # Bottom boxes
    bottom_y = 545

    # Aspects
    asp_x = 260
    svg.append(f'<rect x="{asp_x}" y="{bottom_y}" width="300" height="145" fill="#fffdf8" stroke="{border}" rx="6"/>')
    svg.append(svg_text(asp_x + 14, bottom_y + 18, "WICHTIGE ASPEKTE", 9, weight="bold"))

    yy = bottom_y + 36
    for asp in chart["aspects"][:10]:
        line = f'{asp["p1"]} {asp["aspect"]} {asp["p2"]} — Orb {asp["orb"]}°'
        svg.append(svg_text(asp_x + 14, yy, line, 7))
        yy += 11

    # Elements/modalities
    stat_x = 585
    svg.append(f'<rect x="{stat_x}" y="{bottom_y}" width="170" height="145" fill="#fffdf8" stroke="{border}" rx="6"/>')
    svg.append(svg_text(stat_x + 14, bottom_y + 18, "ELEMENTE", 9, weight="bold"))

    yy = bottom_y + 38
    for key, val in chart["elements"].items():
        svg.append(svg_text(stat_x + 18, yy, f"{key}: {val}", 7.5))
        yy += 14

    yy += 10
    svg.append(svg_text(stat_x + 14, yy, "MODALITÄTEN", 9, weight="bold"))
    yy += 18

    for key, val in chart["modalities"].items():
        svg.append(svg_text(stat_x + 18, yy, f"{key}: {val}", 7.5))
        yy += 14

    # Interpretation
    interp_x = 780
    svg.append(f'<rect x="{interp_x}" y="{bottom_y}" width="270" height="145" fill="#fffdf8" stroke="{border}" rx="6"/>')
    svg.append(svg_text(interp_x + 14, bottom_y + 18, "KURZINTERPRETATION", 9, weight="bold"))

    sun = chart["planets"][0]
    svg.append(svg_text(interp_x + 14, bottom_y + 40, f'Sonne in {sun["sign"]}', 7.5))
    svg.append(svg_text(interp_x + 14, bottom_y + 56, f'Aszendent in {chart["ascendant"]["sign"]}', 7.5))
    svg.append(svg_text(interp_x + 14, bottom_y + 72, f'MC in {chart["mc"]["sign"]}', 7.5))
    svg.append(svg_text(interp_x + 14, bottom_y + 98, "Die Deutung erfolgt datenbasiert", 7.5))
    svg.append(svg_text(interp_x + 14, bottom_y + 112, "aus den berechneten Positionen.", 7.5))

    # Footer
    svg.append(f'<rect x="245" y="710" width="610" height="24" fill="#fffdf8" stroke="{border}" rx="5"/>')
    svg.append(svg_text(550, 725, "Dieses Kosmogramm wurde aus berechneten astronomischen Daten erzeugt.", 7.5, anchor="middle"))

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
        datetime.strptime(
            f"{data.birth_date} {data.birth_time}",
            "%Y-%m-%d %H:%M"
        )
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

        _, sign, sign_glyph, element, modality, degree = sign_data(planet_longitude)
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
