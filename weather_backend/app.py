import os
import time
import threading
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, Optional, Any

# Constants and configuration
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY", "03378a93aa0f42a1bc962751250907")
WEATHER_API_BASE_URL = "https://api.weatherapi.com/v1"
CACHE_TTL = 300  # seconds (5 minutes)

app = FastAPI(
    title="WeatherBackend API",
    description="Backend REST API for real-time weather data with WeatherAPI integration and in-memory caching.",
    version="1.0.0",
    openapi_tags=[
        {"name": "weather", "description": "Weather endpoints"}
    ]
)

class WeatherRequest(BaseModel):
    city: str = Field(..., description="City name to fetch weather for")


class WeatherResponse(BaseModel):
    city: str = Field(..., description="City name")
    country: str = Field(..., description="Country name")
    region: str = Field(..., description="Region name")
    temperature_c: float = Field(..., description="Temperature in Celsius")
    condition: str = Field(..., description="Weather condition")
    icon_url: str = Field(..., description="Icon URL for the weather condition")
    last_updated: str = Field(..., description="Timestamp of last update")


class WeatherCacheEntry:
    def __init__(self, value: Any, timestamp: float):
        self.value = value
        self.timestamp = timestamp


class WeatherCache:
    def __init__(self, ttl: int = 300):
        self._cache: Dict[str, WeatherCacheEntry] = {}
        self._ttl = ttl
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[WeatherCacheEntry]:
        with self._lock:
            entry = self._cache.get(key)
            if entry and (time.time() - entry.timestamp) < self._ttl:
                return entry
            if entry:
                del self._cache[key]
            return None

    def set(self, key: str, value: Any):
        with self._lock:
            self._cache[key] = WeatherCacheEntry(value, time.time())

weather_cache = WeatherCache(ttl=CACHE_TTL)

# PUBLIC_INTERFACE
@app.get("/weather", response_model=WeatherResponse, tags=["weather"], summary="Get weather by city name", description="Fetches current weather for the specified city using WeatherAPI. Handles caching, loading, and error states.")
def get_weather(city: str):
    """
    Returns weather data for the given city, integrating with WeatherAPI and using in-memory caching. Shows appropriate error if city is not found or API fails.
    - Query parameter: city (str) - required city name.
    - Caching: Results cached for 5 minutes per city.

    Returns:
        WeatherResponse: Weather info for the city.
    Raises:
        HTTPException: If city not found, API error, or request fails.
    """
    city_key = city.strip().lower()
    # Loading state is managed client-side; backend replies synchronously

    # Check cache
    cached_entry = weather_cache.get(city_key)
    if cached_entry:
        return cached_entry.value

    # Not found in cache - fetch from WeatherAPI
    api_url = f"{WEATHER_API_BASE_URL}/current.json"
    params = {
        "key": WEATHER_API_KEY,
        "q": city_key,
    }
    try:
        resp = requests.get(api_url, params=params, timeout=6)
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=f"WeatherAPI error: {resp.text}")
        data = resp.json()
        if "error" in data:
            raise HTTPException(status_code=404, detail=f"City not found: {city}")
        response = WeatherResponse(
            city=data["location"]["name"],
            country=data["location"]["country"],
            region=data["location"]["region"],
            temperature_c=data["current"]["temp_c"],
            condition=data["current"]["condition"]["text"],
            icon_url="https:" + data["current"]["condition"]["icon"],
            last_updated=data["current"]["last_updated"]
        )
        weather_cache.set(city_key, response)
        return response
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"External API call failed: {str(e)}")


# PUBLIC_INTERFACE
@app.get("/", tags=["weather"], include_in_schema=False)
def root():
    """Root endpoint for health-check or welcome message."""
    return {"message": "WeatherBackend API is running. See /docs for usage."}

