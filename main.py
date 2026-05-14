from fastapi import FastAPI, Response
from pydantic import BaseModel
from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder
from datetime import datetime
import pytz
import swisseph as swe
import math

app = FastAPI()

geolocator = Nominatim(user_agent="astralytica")
tf = TimezoneFinder()
def zodiac_to_circle(longitude):
    return math.radians(longitude - 90)


def polar_to_cartesian(cx, cy, radius, angle_rad):
    x = cx + radius * math.cos(angle_rad)
    y = cy + radius * math.sin(angle_rad)
    return x, y


def generate_cosmogram_svg(planets):
    size = 800
    center = size / 2
    outer_radius = 320
    inner_radius = 260

    svg = []

    svg.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 {size} {size}">'
    )

    svg.append(
        f'<rect width="100%" height="100%" fill="white"/>'
    )

    svg.append(
        f'<circle cx="{center}" cy="{center}" r="{outer_radius}" fill="none" stroke="black" stroke-width="2"/>'
    )

    svg.append(
        f'<circle cx="{center}" cy="{center}" r="{inner_radius}" fill="none" stroke="black" stroke-width="1"/>'
    )

    for i in range(12):
        angle = math.radians(i * 30 - 90)

        x1, y1 = polar_to_cartesian(
            center,
            center,
            inner_radius,
            angle
        )

        x2, y2 = polar_to_cartesian(
            center,
            center,
            outer_radius,
            angle
        )

        svg.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="black" stroke-width="1"/>'
        )

    for planet in planets:
        angle = zodiac_to_circle(planet["longitude"])

        px, py = polar_to_cartesian(
            center,
            center,
            220,
            angle
        )

        svg.append(
            f'<circle cx="{px}" cy="{py}" r="6" fill="red"/>'
        )

        svg.append(
            f'<text x="{px + 10}" y="{py}" font-size="14">{planet["planet"]}</text>'
        )

    svg.append("</svg>")

    return "".join(svg)


class BirthData(BaseModel):
    birth_date: str
    birth_time: str
    birth_place: str
    country: str


@app.get("/")
def root():
    return {
        "status": "online",
        "service": "Astralytica API"
    }


@app.post("/calculate-birth-chart")
def calculate_birth_chart(data: BirthData):
    location_query = f"{data.birth_place}, {data.country}"

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
            "error": "Location lookup failed. Please provide coordinates manually or use a more precise city/country."
        }

    if not timezone_name:
        return {
            "success": False,
            "error": "Timezone not found"
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

    zodiac_signs = [
        "Widder",
        "Stier",
        "Zwillinge",
        "Krebs",
        "Löwe",
        "Jungfrau",
        "Waage",
        "Skorpion",
        "Schütze",
        "Steinbock",
        "Wassermann",
        "Fische"
    ]

    planets = {
        "Sonne": swe.SUN,
        "Mond": swe.MOON,
        "Merkur": swe.MERCURY,
        "Venus": swe.VENUS,
        "Mars": swe.MARS,
        "Jupiter": swe.JUPITER,
        "Saturn": swe.SATURN,
        "Uranus": swe.URANUS,
        "Neptun": swe.NEPTUNE,
        "Pluto": swe.PLUTO
    }

    planet_results = []

    for planet_name, planet_id in planets.items():
        planet_data = swe.calc_ut(julian_day, planet_id)[0]

        planet_longitude = planet_data[0]
        retrograde = planet_data[3] < 0

        sign_index = int(planet_longitude // 30)
        degree = planet_longitude % 30

        planet_results.append({
            "planet": planet_name,
            "sign": zodiac_signs[sign_index],
            "degree": round(degree, 2),
            "longitude": round(planet_longitude, 2),
            "retrograde": retrograde
        })

    houses, ascmc = swe.houses(
        julian_day,
        latitude,
        longitude,
        b'P'
    )

    ascendant = ascmc[0]
    mc = ascmc[1]

    asc_sign = zodiac_signs[int(ascendant // 30)]
    mc_sign = zodiac_signs[int(mc // 30)]
    cosmogram_svg = generate_cosmogram_svg(planet_results)

    return {
        "success": True,
        "input": {
            "birth_date": data.birth_date,
            "birth_time": data.birth_time,
            "birth_place": data.birth_place,
            "country": data.country
        },
        "coordinates": {
            "latitude": latitude,
            "longitude": longitude
        },
        "timezone": timezone_name,
        "utc_time": utc_datetime.isoformat(),
        "ascendant": {
            "sign": asc_sign,
            "degree": round(ascendant % 30, 2),
            "longitude": round(ascendant, 2)
        },
        "mc": {
            "sign": mc_sign,
            "degree": round(mc % 30, 2),
            "longitude": round(mc, 2)
        },
        "planets": planet_results,
        "houses": [
            round(house, 2)
            for house in houses
        ],
        "cosmogram_svg": cosmogram_svg
    }
    
    @app.get("/cosmogram.svg")
def get_cosmogram_svg(
    birth_date: str,
    birth_time: str,
    birth_place: str,
    country: str
):
    data = BirthData(
        birth_date=birth_date,
        birth_time=birth_time,
        birth_place=birth_place,
        country=country
    )

    result = calculate_birth_chart(data)

    if not result.get("success"):
        return Response(
            content="<svg xmlns='http://www.w3.org/2000/svg'><text x='20' y='40'>Calculation failed</text></svg>",
            media_type="image/svg+xml"
        )

    return Response(
        content=result["cosmogram_svg"],
        media_type="image/svg+xml"
    )
