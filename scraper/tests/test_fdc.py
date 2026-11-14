import csv, shutil
import config, fdc
from conftest import FIXTURES


def _install(tmp):
    shutil.copytree(FIXTURES / "fdc" / "sr", config.FDC_DIR / "sr")


def _writeCsv(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow(header)
        w.writerows(rows)


def _foundationFolder(foods, nutrients):
    """foods: [(id, description)], nutrients: {id: {nutrientId: amount}}; Foundation foods have no portions here."""
    folder = config.FDC_DIR / "foundation"
    _writeCsv(folder / "food.csv", ["fdc_id", "data_type", "description"],
              [[i, "foundation_food", d] for i, d in foods] + [[1, "sub_sample_food", "a sample, not a food"]])
    _writeCsv(folder / "food_nutrient.csv", ["id", "fdc_id", "nutrient_id", "amount"],
              [[0, i, n, a] for i, d in nutrients.items() for n, a in d.items()])
    _writeCsv(folder / "food_portion.csv", ["id", "fdc_id", "amount", "measure_unit_id", "portion_description",
                                            "modifier", "gram_weight"], [])


def test_import_reads_foods_nutrients_portions():
    _install(None)
    assert fdc.importFolders(log=lambda *_: None) == 5
    foods = fdc.loadFoods()
    egg = foods[900003]
    assert egg["description"] == "Egg, whole, raw, fresh"
    assert egg["dataType"] == "sr_legacy_food"
    assert egg["per100g"]["calories"] == 143 and egg["per100g"]["sodiumMg"] == 142
    assert {"amount": 1.0, "unit": "large", "grams": 50.0} in egg["portions"]


def test_missing_nutrients_are_zero_and_listed():
    _install(None)
    fdc.importFolders(log=lambda *_: None)
    oil = fdc.loadFoods()[900004]
    assert oil["per100g"]["proteinG"] == 0.0 and oil["per100g"]["carbsG"] == 0.0
    assert set(oil["missing"]) == {"proteinG", "carbsG", "fibreG", "sugarG"}
    assert fdc.loadFoods()[900001]["missing"] == []


def test_portion_units_and_dropped_portions():
    _install(None)
    fdc.importFolders(log=lambda *_: None)
    onion = fdc.loadFoods()[900001]
    assert {"amount": 1.0, "unit": "cup, chopped", "grams": 160.0} in onion["portions"]
    assert len(onion["portions"]) == 2          # the portion with no gram weight is dropped
    assert {"amount": 1.0, "unit": "tbsp", "grams": 13.5} in fdc.loadFoods()[900004]["portions"]


def test_sugar_falls_back_to_1063():
    _install(None)
    fdc.importFolders(log=lambda *_: None)
    assert fdc.loadFoods()[900005]["per100g"]["sugarG"] == 4.73


def test_portion_with_a_measure_unit_gets_the_unit_name_first(tmp_path):
    _install(None)
    portions = config.FDC_DIR / "sr" / "food_portion.csv"
    _writeCsv(portions, ["id", "fdc_id", "amount", "measure_unit_id", "portion_description", "modifier", "gram_weight"],
              [[1, 900001, 1, 1000, "", "chopped", 160], [2, 900001, 2, 9999, "Whole Onion", "x", 220]])
    fdc.importFolders(log=lambda *_: None)
    assert fdc.loadFoods()[900001]["portions"] == [{"amount": 1.0, "unit": "cup, chopped", "grams": 160.0},
                                                   {"amount": 2.0, "unit": "whole onion", "grams": 220.0}]


def test_foundation_food_without_kcal_is_derived_or_dropped():
    _foundationFolder([(10, "Derived food"), (11, "Hopeless food"), (12, "Atwater food")],
                      {10: {1003: 10, 1004: 5, 1005: 20},
                       11: {1003: 10},
                       12: {2047: 100, 1003: 1}})
    logged = []
    assert fdc.importFolders(log=logged.append) == 2
    foods = fdc.loadFoods()
    assert foods[10]["per100g"]["calories"] == 4 * 10 + 9 * 5 + 4 * 20
    assert foods[12]["per100g"]["calories"] == 100
    assert 11 not in foods and 1 not in foods
    assert any("dropped 1" in line for line in logged)


def test_incomplete_folder_is_skipped_and_logged():
    _install(None)
    (config.FDC_DIR / "foundation").mkdir(parents=True)
    (config.FDC_DIR / "foundation" / "nutrient.csv").write_text("id\n")
    logged = []
    fdc.importFolders(log=logged.append)
    assert any("incomplete" in line and "foundation" in line for line in logged)


def test_load_imports_when_cache_missing_and_empty_without_files():
    assert fdc.loadFoods() == {}
    _install(None)
    assert len(fdc.loadFoods()) == 5 and config.FDC_FOODS_FILE.exists()


def test_portions_with_zero_amount_or_weight_are_dropped():
    _install(None)
    _writeCsv(config.FDC_DIR / "sr" / "food_portion.csv",
              ["id", "fdc_id", "amount", "measure_unit_id", "portion_description", "modifier", "gram_weight"],
              [[1, 900001, 0, 9999, "", "none", 50], [2, 900001, 1, 9999, "", "zero grams", 0],
               [3, 900001, 1, 9999, "", "medium", 110]])
    fdc.importFolders(log=lambda *_: None)
    assert fdc.loadFoods()[900001]["portions"] == [{"amount": 1.0, "unit": "medium", "grams": 110.0}]
