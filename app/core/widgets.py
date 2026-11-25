"""Widgets: world clocks and weather (Open-Meteo, keyless). Made by Nur Al Mahtab.

Privacy: the only thing ever sent is the city name you typed (to find its coordinates) and then those
coordinates (to get the forecast). No account, no key, never your IP-derived location.
"""
from __future__ import annotations
import json, re, urllib.parse, urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_CLOCKS = ["London=Europe/London", "New York=America/New_York", "Tokyo=Asia/Tokyo"]

# Spoken city -> time zone, for "what time is it in Tokyo". Your own clock list is checked first.
CITIES = {
    "london": "Europe/London", "paris": "Europe/Paris", "berlin": "Europe/Berlin", "madrid": "Europe/Madrid", "rome": "Europe/Rome",
    "moscow": "Europe/Moscow", "istanbul": "Europe/Istanbul", "dubai": "Asia/Dubai", "karachi": "Asia/Karachi", "delhi": "Asia/Kolkata",
    "mumbai": "Asia/Kolkata", "dhaka": "Asia/Dhaka", "bangkok": "Asia/Bangkok", "singapore": "Asia/Singapore", "hong kong": "Asia/Hong_Kong",
    "beijing": "Asia/Shanghai", "shanghai": "Asia/Shanghai", "tokyo": "Asia/Tokyo", "seoul": "Asia/Seoul", "sydney": "Australia/Sydney",
    "melbourne": "Australia/Melbourne", "auckland": "Pacific/Auckland", "new york": "America/New_York", "washington": "America/New_York",
    "toronto": "America/Toronto", "chicago": "America/Chicago", "denver": "America/Denver", "los angeles": "America/Los_Angeles",
    "san francisco": "America/Los_Angeles", "vancouver": "America/Vancouver", "mexico city": "America/Mexico_City",
    "sao paulo": "America/Sao_Paulo", "buenos aires": "America/Argentina/Buenos_Aires", "cairo": "Africa/Cairo", "lagos": "Africa/Lagos",
    "nairobi": "Africa/Nairobi", "johannesburg": "Africa/Johannesburg", "riyadh": "Asia/Riyadh", "tehran": "Asia/Tehran", "kabul": "Asia/Kabul",
    "kathmandu": "Asia/Kathmandu", "colombo": "Asia/Colombo", "jakarta": "Asia/Jakarta", "manila": "Asia/Manila", "kuala lumpur": "Asia/Kuala_Lumpur",
    "utc": "UTC", "gmt": "UTC"}

# Open-Meteo WMO weather codes -> (text, emoji). Weather symbols live in the emoji font, not the icon font.
WMO = {0: ("Clear", "☀️"), 1: ("Mostly clear", "🌤️"), 2: ("Partly cloudy", "⛅"), 3: ("Overcast", "☁️"),
       45: ("Fog", "🌫️"), 48: ("Freezing fog", "🌫️"), 51: ("Light drizzle", "🌦️"), 53: ("Drizzle", "🌦️"),
       55: ("Heavy drizzle", "🌧️"), 56: ("Freezing drizzle", "🌧️"), 57: ("Freezing drizzle", "🌧️"),
       61: ("Light rain", "🌦️"), 63: ("Rain", "🌧️"), 65: ("Heavy rain", "🌧️"), 66: ("Freezing rain", "🌧️"),
       67: ("Freezing rain", "🌧️"), 71: ("Light snow", "🌨️"), 73: ("Snow", "🌨️"), 75: ("Heavy snow", "❄️"),
       77: ("Snow grains", "🌨️"), 80: ("Showers", "🌦️"), 81: ("Showers", "🌧️"), 82: ("Heavy showers", "🌧️"),
       85: ("Snow showers", "🌨️"), 86: ("Snow showers", "❄️"), 95: ("Thunderstorm", "⛈️"), 96: ("Thunderstorm, hail", "⛈️"),
       99: ("Thunderstorm, hail", "⛈️")}
NIGHT_CLEAR = "🌙"


# ------------------------------------------------------------------ clocks
def parse_clocks(entries: list[str]) -> list[tuple[str, str]]:
    """['London=Europe/London', ...] -> [(label, zone)], dropping anything that is not a real time zone."""
    out = []
    for e in entries:
        label, _, zone = e.partition("=")
        label, zone = label.strip(), zone.strip()
        if label and zone:
            try:
                ZoneInfo(zone)
                out.append((label[:24], zone))
            except (ZoneInfoNotFoundError, ValueError, OSError):
                pass
    return out[:4]


def clock_rows(zones: list[tuple[str, str]], now: datetime | None = None, local_name: str = "Here") -> list[dict]:
    """One row per place: the time there and whether it is a different day than here."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    here = now.astimezone().date()
    rows = []
    for label, zone in zones:
        t = now.astimezone(ZoneInfo(zone))
        diff = (t.date() - here).days
        rows.append({"city": label, "time": t.strftime("%H:%M"), "day": "Tomorrow" if diff > 0 else "Yesterday" if diff < 0 else "Today",
                     "night": not (6 <= t.hour < 19)})
    return rows


def zone_for(name: str, clocks: list[tuple[str, str]]) -> tuple[str, str] | None:
    """Find a time zone for a spoken city: your own clock labels first, then the built-in list."""
    q = " ".join(name.lower().split())
    for label, zone in clocks:
        if label.lower() == q:
            return label, zone
    if q in CITIES:
        return q.title(), CITIES[q]
    return None


def time_in(name: str, clocks, now: datetime | None = None) -> str | None:
    hit = zone_for(name, clocks)
    if not hit:
        return None
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    t = now.astimezone(ZoneInfo(hit[1]))
    diff = (t.date() - now.astimezone().date()).days
    day = " tomorrow" if diff > 0 else " yesterday" if diff < 0 else ""
    return f"It is {t.strftime('%I:%M %p').lstrip('0')}{day} in {hit[0]}."


# ------------------------------------------------------------------ weather
@dataclass
class Weather:
    temp: int
    text: str
    glyph: str
    high: int
    low: int
    unit: str          # "C" or "F"
    place: str
    night: bool = False

    def sentence(self) -> str:
        return f"It is {self.temp} degrees and {self.text.lower()} in {self.place}, with a high of {self.high} and a low of {self.low}."


def parse_weather(data: dict, place: str, unit: str) -> Weather | None:
    try:
        cur, daily = data["current"], data["daily"]
        code = int(cur["weather_code"])
        text, glyph = WMO.get(code, ("Unsettled", "☁️"))
        night = not cur.get("is_day", 1)
        if night and code in (0, 1):
            glyph = NIGHT_CLEAR                         # a sun at midnight looks wrong
        return Weather(round(cur["temperature_2m"]), text, glyph, round(daily["temperature_2m_max"][0]),
                       round(daily["temperature_2m_min"][0]), unit, place, night=night)
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def _get(url: str, opener: Callable, timeout: float = 8.0) -> dict | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Jarvis-notch/0.1"})
        with opener(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def geocode(city: str, opener: Callable = urllib.request.urlopen) -> dict | None:
    """City name -> {name, lat, lon}. Only the name you typed is sent."""
    city = city.strip()
    if not city:
        return None
    data = _get("https://geocoding-api.open-meteo.com/v1/search?" + urllib.parse.urlencode({"name": city, "count": 1, "language": "en"}), opener)
    hit = (data or {}).get("results", [None])[0]
    if not hit:
        return None
    place = hit.get("name", city) + (f", {hit['country_code']}" if hit.get("country_code") else "")
    return {"name": place, "lat": float(hit["latitude"]), "lon": float(hit["longitude"])}


def fetch_weather(lat: float, lon: float, place: str, unit: str = "C", opener: Callable = urllib.request.urlopen) -> Weather | None:
    q = {"latitude": round(lat, 3), "longitude": round(lon, 3), "current": "temperature_2m,weather_code,is_day",
         "daily": "temperature_2m_max,temperature_2m_min", "timezone": "auto", "forecast_days": 1,
         "temperature_unit": "fahrenheit" if unit == "F" else "celsius"}
    data = _get("https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(q), opener)
    return parse_weather(data, place, unit) if data else None
