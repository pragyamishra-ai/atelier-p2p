from p2p.data_gen.master_data import CATEGORIES, make_materials, make_vendors
from p2p.schemas import Currency


def test_deterministic_for_same_seed():
    assert make_vendors(1).equals(make_vendors(1))
    assert make_materials(1).equals(make_materials(1))
    assert not make_vendors(1).equals(make_vendors(2))


def test_keys_and_names_unique():
    vendors = make_vendors(42)
    materials = make_materials(42)
    assert vendors["vendor_id"].is_unique
    assert vendors["name"].is_unique
    assert materials["material_id"].is_unique
    assert materials["description"].is_unique


def test_currencies_match_schema():
    assert set(make_vendors(42)["currency"]) <= {c.value for c in Currency}


def test_every_category_has_vendors_and_materials():
    vendors = make_vendors(42)
    materials = make_materials(42)
    assert set(vendors["category"]) == set(CATEGORIES)
    assert set(materials["category"]) == set(CATEGORIES)
