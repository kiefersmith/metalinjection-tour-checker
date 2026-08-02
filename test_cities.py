"""Location matching: city+state disambiguation, radius, and date parsing.

Run with: python test_cities.py
"""
import logging
import sys

logging.disable(logging.CRITICAL)

from main import (
    CITY_STATE_PATTERN,
    HOME,
    RADIUS_MILES,
    is_near_home,
    parse_tour_dates,
)
import geo

failures = []


def check(label, actual, expected):
    if actual != expected:
        failures.append(f"{label}\n      expected: {expected}\n      actual:   {actual}")


def places_in(text):
    """The nearby (city, state) pairs the prose fallback would find."""
    return [
        (m.group(1), m.group(2))
        for m in CITY_STATE_PATTERN.finditer(text)
        if is_near_home(m.group(1), m.group(2))
    ]


# --- The state is what disambiguates. These all matched before it was required.
check("Jacksonville FL is not Jacksonville NC",
      places_in("Oct 30 - Jacksonville, FL @ Albatross"), [])
check("Charlotte MI is not Charlotte NC",
      places_in("Nov 02 - Charlotte, MI @ Some Venue"), [])
check("Greensboro GA is not Greensboro NC",
      places_in("Nov 10 - Greensboro, GA @ Festival Grounds"), [])
check("Hillsborough NJ is not Hillsborough NC",
      places_in("Hillsborough, NJ @ The Barn"), [])
check("a person named Charlotte is not a city",
      places_in("Delain vocalist Charlotte Wessels announces solo album"), [])
check("a bare city name in prose is not a show",
      places_in("The Raleigh-based quartet head to Europe"), [])
check("a venue named after a city elsewhere does not match",
      places_in("Playing Chapel Hill Road Amphitheater in Dallas, TX"), [])

# --- Real nearby shows still match.
check("listed city matches",
      places_in("Oct 21 - Charlotte, NC @ The Underground"), [("Charlotte", "NC")])
check("unlisted city inside the radius matches",
      places_in("Nov 05 - Durham, NC @ Motorco"), [("Durham", "NC")])
check("unlisted city further out but still inside the radius matches",
      places_in("Nov 06 - Fayetteville, NC @ The Rock Shop"), [("Fayetteville", "NC")])
check("listed city too small to geocode still matches",
      places_in("Nov 07 - Hillsborough, NC @ Yonder"), [("Hillsborough", "NC")])

# --- Radius behaviour.
check("home is zero miles from itself", round(geo.distance_from(HOME, *HOME)), 0)
check("a city well outside the radius is rejected", is_near_home("Nashville", "TN"), False)
check("an ungeocodable city is not assumed near", is_near_home("Nowhereville", "ZZ"), False)
check("missing state is never a match", is_near_home("Raleigh", ""), False)
durham = geo.distance_from(HOME, "Durham", "NC")
if durham is None or durham > RADIUS_MILES:
    failures.append(f"Durham should sit inside the {RADIUS_MILES} mile radius, got {durham}")

# --- Both listing styles parse.
numeric = parse_tour_dates("3/25 Philadelphia, PA Milkboy3/26 Hamden, CT Cellar on Treadwell 2026")
check("numeric listing style", numeric[:1], [("2026-03-25", "Philadelphia", "PA", "Milkboy")])

month = parse_tour_dates(
    "2026 Tour Dates Oct 21 – Charlotte, NC @ The Underground "
    "Oct 22 – Atlanta, GA @ The Masquerade"
)
check("month-name listing style", month,
      [("2026-10-21", "Charlotte", "NC", "The Underground"),
       ("2026-10-22", "Atlanta", "GA", "The Masquerade")])

check("prose is not mistaken for a listing",
      parse_tour_dates("They play Oct 3 at the House of Blues in San Diego, a day after Sacramento."),
      [])

if failures:
    print(f"FAILED {len(failures)}/{len(failures)} shown:\n")
    for f in failures:
        print("  " + f)
    sys.exit(1)
print("all location tests passed")
