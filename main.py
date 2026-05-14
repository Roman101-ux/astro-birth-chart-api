from fastapi import FastAPI
from pydantic import BaseModel
from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder
from datetime import datetime
import pytz
import swisseph as swe

app = FastAPI()

geolocator = Nominatim(user_agent="astralytica")
tf = TimezoneFinder()


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
        ]
    }
