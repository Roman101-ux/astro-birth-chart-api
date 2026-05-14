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
    location = geolocator.geocode(location_query)

    if not location:
        return {
            "success": False,
            "error": "Location not found"
        }

    latitude = location.latitude
    longitude = location.longitude

    timezone_name = tf.timezone_at(lat=latitude, lng=longitude)

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

    sun_position = swe.calc_ut(julian_day, swe.SUN)[0][0]

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

    sign_index = int(sun_position // 30)
    sign_degree = sun_position % 30

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
        "sun": {
            "sign": zodiac_signs[sign_index],
            "degree": round(sign_degree, 2)
        }
    }
