"""Master data: vendors (LIFNR-style keys) and materials (MATNR-style keys)."""

import random
from itertools import product

import pandas as pd
from faker import Faker

# country: (currency, language, faker locale, legal-form suffixes)
COUNTRIES = {
    "FR": ("EUR", "fr", "fr_FR", ["SA", "SARL", "SAS"]),
    "IT": ("EUR", "it", "it_IT", ["SpA", "Srl"]),
    "CH": ("CHF", "fr", "fr_FR", ["SA", "AG"]),
    "GB": ("GBP", "en", "en_GB", ["Ltd", "PLC"]),
    "US": ("USD", "en", "en_US", ["Inc", "LLC"]),
}
COUNTRY_WEIGHTS = [0.30, 0.35, 0.15, 0.10, 0.10]
PAYMENT_TERMS = ["NET30", "NET45", "NET60", "2/10 NET30"]

COLOURS = ["Black", "Cognac", "Ivory", "Navy", "Burgundy", "Taupe"]

CATEGORIES = {
    "leather": {
        "items": [
            "Calf leather",
            "Lambskin",
            "Saffiano leather",
            "Goatskin",
            "Box calf",
            "Grained leather",
        ],
        "variants": COLOURS,
        "unit": "M2",
        "price": (40, 220),
        "vendor_words": ["Tannery", "Leather Works", "Hides"],
    },
    "textile": {
        "items": [
            "Silk twill",
            "Cotton canvas",
            "Wool crepe",
            "Cashmere blend",
            "Satin lining",
            "Jacquard",
        ],
        "variants": COLOURS,
        "unit": "M",
        "price": (8, 90),
        "vendor_words": ["Textiles", "Mills", "Fabrics"],
    },
    "hardware": {
        "items": ["Zipper", "Buckle", "Clasp", "Rivet set", "D-ring", "Snap button"],
        "variants": ["Gold", "Palladium", "Brass", "Antique brass", "Gunmetal", "Rose gold"],
        "unit": "EA",
        "price": (0.5, 25),
        "vendor_words": ["Metalworks", "Hardware", "Fittings"],
    },
    "packaging": {
        "items": ["Gift box", "Dust bag", "Tissue paper", "Shopping bag", "Care card", "Ribbon"],
        "variants": ["Small", "Medium", "Large", "Ivory", "Black", "Embossed"],
        "unit": "EA",
        "price": (0.3, 6),
        "vendor_words": ["Packaging", "Boxes", "Print"],
    },
}


def make_vendors(seed: int, n: int = 40) -> pd.DataFrame:
    rng = random.Random(seed)
    Faker.seed(seed)
    fakers = {c: Faker(spec[2]) for c, spec in COUNTRIES.items()}
    categories = list(CATEGORIES)
    used_names: set[str] = set()
    rows = []
    for i in range(n):
        category = categories[i % len(categories)]  # every category gets vendors
        country = rng.choices(list(COUNTRIES), weights=COUNTRY_WEIGHTS)[0]
        currency, language, _, suffixes = COUNTRIES[country]
        while True:
            last = fakers[country].last_name()
            word = rng.choice(CATEGORIES[category]["vendor_words"])
            name = f"{last} {word} {rng.choice(suffixes)}"
            if name not in used_names:
                used_names.add(name)
                break
        rows.append(
            {
                "vendor_id": f"{100000 + i:010d}",
                "name": name,
                "country": country,
                "currency": currency,
                "language": language,
                "category": category,
                "payment_terms": rng.choice(PAYMENT_TERMS),
                "vat_id": f"{country}{rng.randint(10**8, 10**9 - 1)}",
            }
        )
    return pd.DataFrame(rows)


def make_materials(seed: int, per_category: int = 30) -> pd.DataFrame:
    rng = random.Random(seed + 1)
    rows = []
    n = 0
    for category, spec in CATEGORIES.items():
        combos = rng.sample(list(product(spec["items"], spec["variants"])), per_category)
        for item, variant in combos:
            lo, hi = spec["price"]
            rows.append(
                {
                    "material_id": f"M{10000 + n}",
                    "description": f"{item}, {variant}",
                    "category": category,
                    "unit": spec["unit"],
                    "std_price_eur": round(rng.uniform(lo, hi), 2),
                }
            )
            n += 1
    return pd.DataFrame(rows)
