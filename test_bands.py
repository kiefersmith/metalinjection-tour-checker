"""Expected band extraction for real metalinjection.net headlines.

Run with: python test_bands.py
"""
import sys
import logging
logging.disable(logging.CRITICAL)
from main import extract_band_names

CASES = [
    # The two bugs this change fixes.
    ("FAITH NO MORE Return, Announce Tour Dates With SYSTEM OF A DOWN",
     ["FAITH NO MORE", "SYSTEM OF A DOWN"]),
    ("DANNY ELFMAN Live Band To Consist Of Members From NINE INCH NAILS, A PERFECT CIRCLE, DETHKLOK, And More",
     ["A PERFECT CIRCLE", "DANNY ELFMAN", "DETHKLOK", "NINE INCH NAILS"]),

    # All-caps connectives inside names.
    ("COHEED AND CAMBRIA Announces Headlining North American Shows Around SHINEDOWN Tour",
     ["COHEED AND CAMBRIA", "SHINEDOWN"]),
    ("CORROSION OF CONFORMITY Announces July North American Shows With WHORES & CROBOT",
     ["CORROSION OF CONFORMITY", "CROBOT", "WHORES"]),
    ("SILVERSTEIN & STORY OF THE YEAR Announce North American Tour",
     ["SILVERSTEIN", "STORY OF THE YEAR"]),
    ("BURY TOMORROW Announce 2027 European Tour With STICK TO YOUR GUNS",
     ["BURY TOMORROW", "STICK TO YOUR GUNS"]),
    ("LAMP OF MURMUUR Announces More European Tour Dates",
     ["LAMP OF MURMUUR"]),
    ("TRIVIUM Announces Massive Fall 2026 Headline Tour Featuring IN FLAMES + More",
     ["IN FLAMES", "TRIVIUM"]),

    # Editorial all-caps must be dropped.
    ("LISTEN: MINISTRY Announce Final Album, Farewell Tour + Single \"Burned Out\"",
     ["MINISTRY"]),
    ("THE MARS VOLTA Announce U.S. Tour Dates, Including MY CHEMICAL ROMANCE Support Slot",
     ["MY CHEMICAL ROMANCE", "THE MARS VOLTA"]),
    ("Legendary NYC Metal Venue SAINT VITUS Returns With THE DILLINGER ESCAPE PLAN + More",
     ["SAINT VITUS", "THE DILLINGER ESCAPE PLAN"]),
    ("AUTHOR & PUNISHER Announces US Tour",
     ["AUTHOR & PUNISHER"]),

    # Stray Title Case article must not become a band.
    ("METALLICA To Perform Two Intimate Shows In A Connecticut Arena",
     ["METALLICA"]),

    # Separators, digits, lowercase 'and'.
    ("NEUROSIS Announce Huge Gig With ACID BATH and MELVINS + More Shows",
     ["ACID BATH", "MELVINS", "NEUROSIS"]),
    ("WAKING THE CADAVER, STILLBIRTH & 9DEAD Announce Slam Domination Tour 2026 European Run",
     ["9DEAD", "STILLBIRTH", "WAKING THE CADAVER"]),
    ("THE BODY & BIG|BRAVE Announce North American Tour",
     ["BIG|BRAVE", "THE BODY"]),
    ("POWERMAN 5000 And THE OFFSPRING Announce New Dates",
     ["POWERMAN 5000", "THE OFFSPRING"]),
    ("FEAR FACTORY Announce European Tour With CRYSTAL LAKE, HATE & THE NOCTURNAL AFFAIR",
     ["CRYSTAL LAKE", "FEAR FACTORY", "HATE", "THE NOCTURNAL AFFAIR"]),
    ("THE BLACK DAHLIA MURDER Shares 'Nocturnal' 20th Anniversary European Tour Dates",
     ["THE BLACK DAHLIA MURDER"]),
    ("STABBING WESTWARD Expand 'Wither Blister Burn + Peel' 30th Anniversary Tour",
     ["STABBING WESTWARD"]),
    ("THE NEAL MORSE BAND Announces Shows Around Morsefest",
     ["THE NEAL MORSE BAND"]),
]

failed = 0
for title, expected in CASES:
    actual = extract_band_names(title)
    if actual != expected:
        failed += 1
        print(f"FAIL  {title[:70]}")
        print(f"      expected: {expected}")
        print(f"      actual:   {actual}")

print(f"\n{len(CASES) - failed}/{len(CASES)} passed")
sys.exit(1 if failed else 0)
