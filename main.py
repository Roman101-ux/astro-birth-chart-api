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
    ("Widder", "♈︎", "Feuer", "Kardinal"),
    ("Stier", "♉︎", "Erde", "Fix"),
    ("Zwillinge", "♊︎", "Luft", "Veränderlich"),
    ("Krebs", "♋︎", "Wasser", "Kardinal"),
    ("Löwe", "♌︎", "Feuer", "Fix"),
    ("Jungfrau", "♍︎", "Erde", "Veränderlich"),
    ("Waage", "♎︎", "Luft", "Kardinal"),
    ("Skorpion", "♏︎", "Wasser", "Fix"),
    ("Schütze", "♐︎", "Feuer", "Veränderlich"),
    ("Steinbock", "♑︎", "Erde", "Kardinal"),
    ("Wassermann", "♒︎", "Luft", "Fix"),
    ("Fische", "♓︎", "Wasser", "Veränderlich"),
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
    ("Sextil", 60, 5, "#4F8FE8"),
    ("Quadrat", 90, 6, "#D85C5C"),
    ("Trigon", 120, 6, "#4F8FE8"),
    ("Opposition", 180, 8, "#C74747"),
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
    start, end, value = norm_deg(start), norm_deg(end), norm_deg(value)
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

    return sorted(aspects, key=lambda x: x["orb"])


def safe_text(x):
    return escape(str(x))


def svg_text(x, y, text, size=9, anchor="start", weight="400", fill="#222"):
    return (
        f'<text x="{x}" y="{y}" font-size="{size}" '
        f'text-anchor="{anchor}" '
        f'font-family="Arial, Helvetica, DejaVu Sans, sans-serif" '
        f'font-weight="{weight}" fill="{fill}">{safe_text(text)}</text>'
    )


def svg_symbol(x, y, text, size=18, anchor="middle", fill="#111"):
    return (
        f'<text x="{x}" y="{y}" font-size="{size}" '
        f'text-anchor="{anchor}" '
        f'font-family="DejaVu Serif, Noto Sans Symbols, Arial Unicode MS, serif" '
        f'font-weight="500" fill="{fill}">{safe_text(text)}</text>'
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

        out.append(
            f'<path d="M {cx} {cy} L {x1:.2f} {y1:.2f} '
            f'A {r} {r} 0 {large} 1 {x2:.2f} {y2:.2f} Z" '
            f'fill="{colors.get(key, "#999")}" opacity="0.95"/>'
        )
        start = end

    out.append(svg_circle(cx, cy, r, stroke="#ddd", width=0.6))
    return "".join(out)


def spread_planets(planets, min_gap=8.0):
    planets = sorted(planets, key=lambda p: p["longitude"])
    result = []
    cluster = []

    def flush_cluster(items):
        if not items:
            return

        if len(items) == 1:
            p = items[0].copy()
            p["display_longitude"] = p["longitude"]
            p["display_radius_offset"] = 0
            result.append(p)
            return

        center = sum(p["longitude"] for p in items) / len(items)
        spread = min(34, max(18, len(items) * 7.0))
        start = center - spread / 2

        for idx, p in enumerate(items):
            q = p.copy()
            q["display_longitude"] = norm_deg(start + idx * (spread / max(len(items) - 1, 1)))
            q["display_radius_offset"] = (idx % 3) * 12
            result.append(q)

    for p in planets:
        if not cluster:
            cluster = [p]
            continue

        if angular_diff(cluster[-1]["longitude"], p["longitude"]) < min_gap:
            cluster.append(p)
        else:
            flush_cluster(cluster)
            cluster = [p]

    flush_cluster(cluster)
    return result


def generate_professional_cosmogram_svg(chart):
    width, height = 1080, 760

    cx, cy = 690, 300

    outer = 250
    zodiac_inner = 226
    house_ring = 192
    planet_ring = 174
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
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="100%" height="100%" fill="{bg}"/>',
        """
<defs>
<filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
<feDropShadow dx="0" dy="1.5" stdDeviation="2" flood-opacity="0.13"/>
</filter>
</defs>
"""
    ]

    svg.append(svg_text(18, 28, "DEIN KOSMOGRAMM", 16, weight="700", fill=ink))
    svg.append(svg_text(18, 46, "Geburtshoroskop", 10, fill=ink))
    svg.append(svg_text(18, 76, chart["display_birth"], 8))
    svg.append(svg_text(18, 90, chart["display_place"], 8))
    svg.append(svg_text(
        18,
        104,
        f'{chart["coordinates"]["latitude"]:.5f}° N / {chart["coordinates"]["longitude"]:.5f}° E',
        8
    ))

    # Main wheel
    svg.append(svg_circle(cx, cy, outer, stroke="#3d3d3d", width=1.45))
    svg.append(svg_circle(cx, cy, zodiac_inner, stroke=grid, width=0.8))
    svg.append(svg_circle(cx, cy, house_ring, stroke=grid, width=0.8))
    svg.append(svg_circle(cx, cy, aspect_ring, stroke="#ddd5c7", width=0.65))

    # Zodiac ring
    for i, (_, glyph, element, _) in enumerate(ZODIAC):
        lon = i * 30
        angle = angle_for_longitude(lon)

        x1, y1 = polar(cx, cy, zodiac_inner, angle)
        x2, y2 = polar(cx, cy, outer, angle)
        svg.append(svg_line(x1, y1, x2, y2, grid, 0.8))

        mid = angle_for_longitude(lon + 15)
        tx, ty = polar(cx, cy, 239, mid)
        svg.append(svg_symbol(tx, ty + 8, glyph, 23, fill=element_colors[element]))

    # Degree ticks
    for d in range(360):
        angle = angle_for_longitude(d)
        r2 = outer - (7 if d % 10 == 0 else 3)
        x1, y1 = polar(cx, cy, outer, angle)
        x2, y2 = polar(cx, cy, r2, angle)
        svg.append(svg_line(x1, y1, x2, y2, "#c8c0b1", 0.35))

    # Houses
    houses = chart["houses_raw"]
    for i, cusp in enumerate(houses):
        angle = angle_for_longitude(cusp)

        x1, y1 = polar(cx, cy, aspect_ring, angle)
        x2, y2 = polar(cx, cy, outer, angle)

        is_axis = i in [0, 3, 6, 9]
        svg.append(svg_line(x1, y1, x2, y2, "#222" if is_axis else grid, 1.2 if is_axis else 0.7))

        next_cusp = houses[(i + 1) % 12]
        mid = cusp + ((next_cusp - cusp) % 360) / 2
        tx, ty = polar(cx, cy, 160, angle_for_longitude(mid))
        svg.append(svg_text(tx, ty + 3, str(i + 1), 9.5, anchor="middle", fill="#666"))

    # Axes kept inside viewbox
    asc = chart["ascendant"]["longitude"]
    mc = chart["mc"]["longitude"]

    for label, lon in [
        ("AC", asc),
        ("DC", norm_deg(asc + 180)),
        ("MC", mc),
        ("IC", norm_deg(mc + 180)),
    ]:
        angle = angle_for_longitude(lon)

        x1, y1 = polar(cx, cy, aspect_ring, angle)
        x2, y2 = polar(cx, cy, outer + 4, angle)
        tx, ty = polar(cx, cy, outer + 12, angle)

        svg.append(svg_line(x1, y1, x2, y2, "#111", 1.25))
        svg.append(svg_text(tx, ty + 4, label, 9.5, anchor="middle", weight="700", fill="#111"))

    # Straight aspect lines
    planet_positions = {p["planet"]: p["longitude"] for p in chart["planets"]}

    for idx, asp in enumerate(chart["aspects"]):
        if asp["aspect"] == "Konjunktion":
            continue

        lon1 = planet_positions[asp["p1"]]
        lon2 = planet_positions[asp["p2"]]

        a1 = angle_for_longitude(lon1)
        a2 = angle_for_longitude(lon2)

        offset = (idx % 5) * 1.8
        r1 = aspect_ring - offset
        r2 = aspect_ring - offset

        x1, y1 = polar(cx, cy, r1, a1)
        x2, y2 = polar(cx, cy, r2, a2)

        svg.append(svg_line(x1, y1, x2, y2, asp["color"], 1.15, 0.74))

    # Planets
    for p in spread_planets(chart["planets"]):
        true_lon = p["longitude"]
        disp_lon = p["display_longitude"]

        angle = angle_for_longitude(disp_lon)
        r = planet_ring - p.get("display_radius_offset", 0)

        px, py = polar(cx, cy, r, angle)
        _, _, _, _, _, deg = sign_data(true_lon)

        svg.append(svg_symbol(px, py, p["glyph"], 20, fill="#111"))
        svg.append(svg_text(px, py + 14, deg_to_dms(deg), 7.7, anchor="middle", fill="#333"))

        if angular_diff(true_lon, disp_lon) > 1.5:
            tx, ty = polar(cx, cy, r - 18, angle_for_longitude(true_lon))
            svg.append(svg_line(px, py + 3, tx, ty, "#888", 0.45, 0.55))

    # Left column
    x, y = 18, 145
    svg.append(svg_text(x, y, "PLANETEN IM ZEICHEN", 9, weight="700"))
    y += 14

    for p in chart["planets"]:
        retro = " ℞" if p["retrograde"] else ""
        svg.append(svg_text(x, y, f'{p["glyph"]} {p["planet"]}: {p["sign"]} {deg_to_dms(p["degree"])}{retro}', 7.9))
        y += 14

    y += 10
    svg.append(svg_text(x, y, "HÄUSER (Placidus)", 9, weight="700"))
    y += 14

    roman = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]
    for i, h in enumerate(chart["houses_raw"]):
        _, sign, _, _, _, deg = sign_data(h)
        svg.append(svg_text(x, y, f'{roman[i]}  {sign} {deg_to_dms(deg)}', 7.9))
        y += 14

    # Bottom boxes
    core_y = 575
    bottom_y = 575

    svg.append(f'<rect x="15" y="{core_y}" width="210" height="130" fill="#fffdf8" stroke="{border}" rx="6" filter="url(#shadow)"/>')
    svg.append(svg_text(28, core_y + 18, "KERNPUNKTE", 9, weight="700"))
    svg.append(svg_text(28, core_y + 38, f'Aszendent: {chart["ascendant"]["sign"]} {deg_to_dms(chart["ascendant"]["degree"])}', 7.5))
    svg.append(svg_text(28, core_y + 54, f'MC: {chart["mc"]["sign"]} {deg_to_dms(chart["mc"]["degree"])}', 7.5))
    svg.append(svg_text(28, core_y + 70, f'UTC: {chart["utc_time"][:16]}', 7.5))
    svg.append(svg_text(28, core_y + 86, f'Zeitzone: {chart["timezone"]}', 7.5))
    svg.append(svg_text(28, core_y + 102, f'Quelle Ort: {chart["location_source"]}', 7.5))
    svg.append(svg_text(28, core_y + 118, "System: tropisch / Placidus", 7.5))

    asp_x = 250
    svg.append(f'<rect x="{asp_x}" y="{bottom_y}" width="310" height="145" fill="#fffdf8" stroke="{border}" rx="6" filter="url(#shadow)"/>')
    svg.append(svg_text(asp_x + 14, bottom_y + 18, "WICHTIGE ASPEKTE", 9, weight="700"))

    yy = bottom_y + 36
    for asp in chart["aspects"][:9]:
        svg.append(svg_text(asp_x + 14, yy, f'{asp["p1"]} {asp["aspect"]} {asp["p2"]} — Orb {asp["orb"]}°', 7))
        yy += 12

    stat_x = 585
    svg.append(f'<rect x="{stat_x}" y="{bottom_y}" width="170" height="145" fill="#fffdf8" stroke="{border}" rx="6" filter="url(#shadow)"/>')
    svg.append(svg_text(stat_x + 14, bottom_y + 18, "ELEMENTE", 9, weight="700"))
    svg.append(svg_pie(stat_x + 42, bottom_y + 60, 22, chart["elements"], element_colors))

    yy = bottom_y + 38
    for key, val in chart["elements"].items():
        svg.append(svg_text(stat_x + 78, yy, f"{key}: {val}", 7.5))
        yy += 14

    yy = bottom_y + 98
    svg.append(svg_text(stat_x + 14, yy, "MODALITÄTEN", 9, weight="700"))
    svg.append(svg_pie(stat_x + 42, bottom_y + 125, 20, chart["modalities"], modality_colors))

    yy += 18
    for key, val in chart["modalities"].items():
        svg.append(svg_text(stat_x + 78, yy, f"{key}: {val}", 7.5))
        yy += 14

    interp_x = 780
    svg.append(f'<rect x="{interp_x}" y="{bottom_y}" width="270" height="145" fill="#fffdf8" stroke="{border}" rx="6" filter="url(#shadow)"/>')
    svg.append(svg_text(interp_x + 14, bottom_y + 18, "KURZINTERPRETATION", 9, weight="700"))

    sun = chart["planets"][0]
    svg.append(svg_text(interp_x + 14, bottom_y + 42, f'Sonne in {sun["sign"]}', 7.5))
    svg.append(svg_text(interp_x + 14, bottom_y + 58, f'Aszendent in {chart["ascendant"]["sign"]}', 7.5))
    svg.append(svg_text(interp_x + 14, bottom_y + 74, f'MC in {chart["mc"]["sign"]}', 7.5))
    svg.append(svg_text(interp_x + 14, bottom_y + 104, "Deutung nur auf Basis", 7.5))
    svg.append(svg_text(interp_x + 14, bottom_y + 118, "der berechneten Daten.", 7.5))

    svg.append(f'<rect x="245" y="735" width="610" height="20" fill="#fffdf8" stroke="{border}" rx="5"/>')
    svg.append(svg_text(550, 748, "Berechnung: Swiss Ephemeris, tropischer Tierkreis, Placidus-Häuser.", 7.2, anchor="middle"))

    svg.append("</svg>")
    return "".join(svg)


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

    houses, ascmc = swe.houses(julian_day, latitude, longitude, b"P")
    houses_raw = [norm_deg(x) for x in houses]

    planet_results = []
    points = {}

    for planet_name, (planet_id, glyph) in PLANETS.items():
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
            "degree": round(degree, 4),
            "longitude": round(planet_longitude, 4),
            "house": house,
            "retrograde": retrograde,
            "element": element,
            "modality": modality,
        })

        points[planet_name] = planet_longitude

    ascendant = norm_deg(ascmc[0])
    mc = norm_deg(ascmc[1])

    _, asc_sign, asc_glyph, _, _, asc_degree = sign_data(ascendant)
    _, mc_sign, mc_glyph, _, _, mc_degree = sign_data(mc)

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
                "degree": round(sign_data(h)[5], 4),
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


@app.get("/")
def root():
    return {"status": "online", "service": "Astralytica Professional API"}


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
        return Response(
            content=f"<svg xmlns='http://www.w3.org/2000/svg' width='900' height='160'><text x='20' y='50' font-size='18'>{message}</text></svg>",
            media_type="image/svg+xml",
        )

    return Response(content=result["cosmogram_svg"], media_type="image/svg+xml")
