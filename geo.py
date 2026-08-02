"""City coordinates and great-circle distance, for matching shows near home.

Backed by geonamescache, which ships an offline dataset — no API key, no network
call at runtime. It only covers places above ~15k population, so small towns
(Hillsborough, NC among them) simply won't resolve. Callers must treat "unknown"
as "can't say", never as "far away"; the explicit city list in main.py is what
covers those.
"""
import logging
import math
from functools import lru_cache

EARTH_RADIUS_MILES = 3958.8

# Only US and Canada: their admin1 codes are the two-letter state/province codes
# that show listings actually print ("Charlotte, NC", "Toronto, ON"). Other
# countries use numeric codes that would collide with those.
_GEOCODED_COUNTRIES = {"US", "CA"}

_cities = None


def _load():
    """Builds a {(city, state): (lat, lon)} index once, on first use."""
    global _cities
    if _cities is not None:
        return _cities

    _cities = {}
    try:
        import geonamescache
    except ImportError:
        # Radius matching degrades to nothing; the explicit list still works.
        logging.warning("geonamescache is not installed; radius matching disabled")
        return _cities

    populations = {}
    for city in geonamescache.GeonamesCache().get_cities().values():
        if city["countrycode"] not in _GEOCODED_COUNTRIES:
            continue
        key = (city["name"].casefold(), city["admin1code"].upper())
        # Several places in one state can share a name; keep the biggest, which
        # is the one a touring band is overwhelmingly likely to be playing.
        if key not in populations or city["population"] > populations[key]:
            populations[key] = city["population"]
            _cities[key] = (city["latitude"], city["longitude"])

    return _cities


@lru_cache(maxsize=8192)
def coordinates(city, state):
    """Returns (lat, lon) for a city, or None if it isn't in the dataset."""
    if not city or not state:
        return None
    return _load().get((city.strip().casefold(), state.strip().upper()))


def miles_between(origin, destination):
    """Great-circle distance in miles between two (lat, lon) pairs."""
    lat1, lon1 = map(math.radians, origin)
    lat2, lon2 = map(math.radians, destination)
    a = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(a))


def distance_from(home, city, state):
    """Miles from `home` (a (city, state) pair) to a city, or None if unknown."""
    origin = coordinates(*home)
    destination = coordinates(city, state)
    if origin is None or destination is None:
        return None
    return miles_between(origin, destination)
