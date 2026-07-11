#!/usr/bin/env python3
"""
Location presets for the Ekadashi Panchang calculator.

Tithi is computed at *local sunrise*, so the same Gregorian date can be a
different tithi in different cities. Add your own city with `--location
LAT,LON[,ELEV,TZ]` if it isn't listed here.

Coordinates are city-center; a few km either way does not change the sunrise
enough to shift a tithi verdict, so any point in a metro area is fine.
"""

from dataclasses import dataclass
from zoneinfo import ZoneInfo


@dataclass
class Location:
    name: str
    lat: float
    lon: float
    elevation: float  # meters
    tz: ZoneInfo


# ---------------------------------------------------------------------------
# India — Ahmedabad first (Swaminarayan Sampradaya headquarters / reference)
# ---------------------------------------------------------------------------

INDIA_LOCATIONS = {
    "ahmedabad": Location("Ahmedabad, India", 23.0225, 72.5714, 53, ZoneInfo("Asia/Kolkata")),
    "gandhinagar": Location("Gandhinagar, India", 23.2156, 72.6369, 81, ZoneInfo("Asia/Kolkata")),
    "vadtal": Location("Vadtal, India", 22.6110, 72.9080, 20, ZoneInfo("Asia/Kolkata")),
    "bochasan": Location("Bochasan, India", 22.4590, 72.8280, 20, ZoneInfo("Asia/Kolkata")),
    "gadhada": Location("Gadhada, India", 21.9700, 71.5770, 120, ZoneInfo("Asia/Kolkata")),
    "sarangpur": Location("Sarangpur, India", 22.1900, 71.7500, 100, ZoneInfo("Asia/Kolkata")),
    "junagadh": Location("Junagadh, India", 21.5222, 70.4579, 107, ZoneInfo("Asia/Kolkata")),
    "rajkot": Location("Rajkot, India", 22.3039, 70.8022, 138, ZoneInfo("Asia/Kolkata")),
    "surat": Location("Surat, India", 21.1702, 72.8311, 13, ZoneInfo("Asia/Kolkata")),
    "vadodara": Location("Vadodara, India", 22.3072, 73.1812, 39, ZoneInfo("Asia/Kolkata")),
    "mumbai": Location("Mumbai, India", 19.0760, 72.8777, 14, ZoneInfo("Asia/Kolkata")),
    "pune": Location("Pune, India", 18.5204, 73.8567, 560, ZoneInfo("Asia/Kolkata")),
    "delhi": Location("Delhi, India", 28.6139, 77.2090, 216, ZoneInfo("Asia/Kolkata")),
    "bangalore": Location("Bengaluru, India", 12.9716, 77.5946, 920, ZoneInfo("Asia/Kolkata")),
    "hyderabad": Location("Hyderabad, India", 17.3850, 78.4867, 542, ZoneInfo("Asia/Kolkata")),
    "chennai": Location("Chennai, India", 13.0827, 80.2707, 6, ZoneInfo("Asia/Kolkata")),
    "kolkata": Location("Kolkata, India", 22.5726, 88.3639, 9, ZoneInfo("Asia/Kolkata")),
}

# ---------------------------------------------------------------------------
# USA — top 10 cities by population, plus Bay Area / Swaminarayan-heavy metros
# ---------------------------------------------------------------------------

US_LOCATIONS = {
    "newyork": Location("New York, NY", 40.7128, -74.0060, 10, ZoneInfo("America/New_York")),
    "losangeles": Location("Los Angeles, CA", 34.0522, -118.2437, 71, ZoneInfo("America/Los_Angeles")),
    "chicago": Location("Chicago, IL", 41.8781, -87.6298, 181, ZoneInfo("America/Chicago")),
    "houston": Location("Houston, TX", 29.7604, -95.3698, 24, ZoneInfo("America/Chicago")),
    "phoenix": Location("Phoenix, AZ", 33.4484, -112.0740, 331, ZoneInfo("America/Phoenix")),
    "philadelphia": Location("Philadelphia, PA", 39.9526, -75.1652, 12, ZoneInfo("America/New_York")),
    "sanantonio": Location("San Antonio, TX", 29.4241, -98.4936, 198, ZoneInfo("America/Chicago")),
    "sandiego": Location("San Diego, CA", 32.7157, -117.1611, 19, ZoneInfo("America/Los_Angeles")),
    "dallas": Location("Dallas, TX", 32.7767, -96.7970, 131, ZoneInfo("America/Chicago")),
    "sanjose": Location("San Jose, CA", 37.3382, -121.8863, 26, ZoneInfo("America/Los_Angeles")),
    "fremont": Location("Fremont, CA", 37.5485, -121.9886, 17, ZoneInfo("America/Los_Angeles")),
    "atlanta": Location("Atlanta, GA", 33.7490, -84.3880, 320, ZoneInfo("America/New_York")),
    "edison": Location("Edison, NJ", 40.5187, -74.4121, 25, ZoneInfo("America/New_York")),
    "robbinsville": Location("Robbinsville, NJ", 40.2148, -74.6191, 32, ZoneInfo("America/New_York")),  # BAPS Akshardham
}

LOCATIONS = {**INDIA_LOCATIONS, **US_LOCATIONS}
DEFAULT_LOCATION = "ahmedabad"


def list_locations():
    """Return a formatted string of all preset locations, grouped by country."""
    lines = ["India:"]
    for key, loc in INDIA_LOCATIONS.items():
        lines.append(f"    {key:<14} {loc.name}")
    lines.append("")
    lines.append("USA:")
    for key, loc in US_LOCATIONS.items():
        lines.append(f"    {key:<14} {loc.name}")
    lines.append("")
    lines.append("Any other place:  --location LAT,LON[,ELEV,TIMEZONE]")
    lines.append("    e.g.  --location 51.5074,-0.1278,11,Europe/London   (London)")
    return "\n".join(lines)
