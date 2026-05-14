from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


class BirthData(BaseModel):
    birth_date: str
    birth_time: str
    birth_place: str
    country: str


@app.get("/")
def root():
    return {
        "status": "online",
        "service": "Astro Birth Chart API"
    }


@app.post("/calculate-birth-chart")
def calculate_birth_chart(data: BirthData):

    return {
        "success": True,
        "input": {
            "birth_date": data.birth_date,
            "birth_time": data.birth_time,
            "birth_place": data.birth_place,
            "country": data.country
        },
        "message": "API funktioniert erfolgreich."
    }