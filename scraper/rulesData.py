"""
The rule tables live as JSON files in rules/, so tuning a rule is a reviewed
change to data rather than to code. Each file is loaded under its name without
.json; a missing file is simply absent, so later rules can be added one file
at a time.
"""
import json

import config
import quantity


def load(folder=None):
    folder = folder or config.RULES_DIR
    rules = {path.stem: json.loads(path.read_text(encoding="utf-8")) for path in sorted(folder.glob("*.json"))}
    rules["unitMap"] = quantity.unitMap(rules.get("units", {}))
    return rules
