"""
What goes with a recipe (spec 2026-11-19 part 3, 2.1 and 2.2). Each shown recipe gets suggestions in slots chosen
by its course (the slot table in rules/pairings.json); a slot's candidates are the shown recipes of the slot's
courses. A candidate's score adds:

1. served with (+10): the recipe's description or steps say "serve with ..."; the phrase up to the next full stop
   is split on "and", "or" and commas, and a part matches a candidate when every word of the candidate's dish key is
   in it. Garnish words never match on their own, and a part naming a garnish phrase ("a squeeze of", "your
   favourite") matches nothing.
2. cuisine: same +3, same family +1, both set in different families -2, either unset 0.
3. effort and time (side and sauce slots): harder -2, longer -1.
4. flavour balance: +2 per pair (rich with fresh, spicy with cooling, ...) where the recipe has one side and the
   candidate the other. The flavour tags count, and rich, fresh and cooling are read from ingredient words.
5. occasion: +1 per shared occasion tag.

Never paired: the recipe itself, one with its dish key, a hidden one. The top `perSlot` with a score above 0 are
kept, equal scores ordered by the candidate's key, each with a why: the one or two largest parts in plain words.
Every number and word is in the rules file.
"""
import re

from matching import plainText, singular

WHY_MAX = 120               # plutus stores a why of up to 120 characters
_STOP = re.compile(r"[.!?;:\n]")
_SPLIT = re.compile(r",|&|\band\b|\bor\b|\bplus\b")


def _words(text):
    return [singular(w) for w in plainText(text).split()]


def _phrasePatterns(phrases):
    return [re.compile(r"\b" + r"\s+".join(map(re.escape, p.split())) + r"\b") for p in phrases]


def servedWithParts(recipe, rules):
    """The parts of every "serve with ..." phrase in the description and steps, each a set of plain singular words."""
    served = rules["pairings"]["servedWith"]
    patterns = _phrasePatterns(served["phrases"])
    garnishPhrases = [" ".join(_words(p)) for p in served["garnishPhrases"]]
    texts = [recipe.description or ""] + [s.text or "" for s in recipe.steps]
    parts = []
    for text in texts:
        lower = text.lower()
        for pattern in patterns:
            for found in pattern.finditer(lower):
                rest = lower[found.end():]
                stop = _STOP.search(rest)
                for piece in _SPLIT.split(rest[:stop.start()] if stop else rest):
                    words = _words(piece)
                    padded = f" {' '.join(words)} "
                    if words and not any(f" {g} " in padded for g in garnishPhrases):
                        parts.append(set(words))
    return parts


def _flavourSides(recipe, rules):
    sides = {t["tag"] for t in recipe.tags if t.get("type") == "flavour"}
    names = [f" {' '.join(_words(line.name or line.line))} " for line in recipe.ingredients]
    for side, words in rules["pairings"]["flavourWords"].items():
        phrases = [f" {' '.join(_words(w))} " for w in words]
        if any(p in name for name in names for p in phrases):
            sides.add(side)
    return sides


def features(recipe, rules):
    """What scoring reads from a recipe, worked out once per pass."""
    p = rules["pairings"]
    family = next((name for name, members in p["cuisineFamilies"].items() if recipe.cuisine in members), None)
    dishWords = set((recipe.dishKey or plainText(recipe.title)).split())
    return {"key": recipe.key, "dishKey": recipe.dishKey, "dishWords": dishWords, "course": recipe.course,
            "cuisine": recipe.cuisine, "family": family, "difficulty": recipe.difficulty,
            "minutes": recipe.totalMinutes, "hidden": recipe.hiddenReason is not None,
            "occasions": sorted({t["tag"] for t in recipe.tags if t.get("type") == "occasion"}),
            "sides": _flavourSides(recipe, rules), "parts": servedWithParts(recipe, rules)}


def _garnish(rules):
    return {singular(w) for w in rules["pairings"]["servedWith"]["garnishWords"]}


def _contributions(r, c, slot, rules, garnish):
    p = rules["pairings"]
    points, why = p["points"], p["why"]
    found = []
    if r["parts"] and c["dishWords"] - garnish and any(c["dishWords"] <= part for part in r["parts"]):
        found.append((points["servedWith"], why["servedWith"].format(dish=c["dishKey"] or " ".join(sorted(c["dishWords"])))))
    if r["cuisine"] and c["cuisine"]:
        if r["cuisine"] == c["cuisine"]:
            found.append((points["sameCuisine"], why["sameCuisine"]))
        elif r["family"] and r["family"] == c["family"]:
            found.append((points["sameFamily"],
                          why["sameFamily"].format(family=p["familyWords"].get(r["family"], r["family"]))))
        else:
            found.append((points["otherFamily"], None))
    if slot in p["effortSlots"]:
        if r["difficulty"] and c["difficulty"] and c["difficulty"] > r["difficulty"]:
            found.append((points["harder"], None))
        if r["minutes"] and c["minutes"] and c["minutes"] > r["minutes"]:
            found.append((points["longer"], None))
    for a, b in p["flavourPairs"]:
        for mine, theirs in ((a, b), (b, a)):
            if mine in r["sides"] and theirs in c["sides"]:
                found.append((points["flavour"], why["flavour"].format(
                    theirs=theirs, slot=p["slotNouns"].get(slot, slot), mine=mine, course=r["course"])))
                break
    for occasion in r["occasions"]:
        if occasion in c["occasions"]:
            found.append((points["occasion"],
                          why["occasion"].format(occasion=p["occasionWords"].get(occasion, occasion))))
    return found


def _whyOf(found):
    best = sorted((item for item in found if item[0] > 0 and item[1]), key=lambda item: -item[0])[:2]
    text = "; ".join(words for _, words in best)
    return text if len(text) <= WHY_MAX else text[:WHY_MAX - 1].rstrip() + "…"


def score(r, c, slot, rules):
    """(points, [why words, largest first]) for candidate c in recipe r's slot; for the tests and the curious."""
    found = _contributions(features(r, rules), features(c, rules), slot, rules, _garnish(rules))
    best = sorted((item for item in found if item[0] > 0 and item[1]), key=lambda item: -item[0])
    return sum(points for points, _ in found), [words for _, words in best]


def _servedMatches(r, wordIndex, garnish):
    """{key: candidate} for every candidate the recipe's "serve with" parts name, found through a word index rather than by
    testing every candidate."""
    found = {}
    for part in r["parts"]:
        for word in part:
            for c in wordIndex.get(word, ()):
                if c["dishWords"] <= part and c["dishWords"] - garnish:
                    found[c["key"]] = c
    return found


def _groups(candidates):
    """Candidates that differ only in key, dish, effort and time score the same apart from effort and time: one group
    per (cuisine, sides, occasions), members in key order."""
    groups = {}
    for c in candidates:
        signature = (c["cuisine"], c["family"], frozenset(c["sides"]), frozenset(c["occasions"]))
        groups.setdefault(signature, []).append(c)
    return [(signature, sorted(members, key=lambda c: c["key"])) for signature, members in groups.items()]


def _baseOf(r, signature, wants, occasions, points):
    """A group's points before "serve with", effort and time (the same sums as _contributions)."""
    cuisine, family, sides, theirOccasions = signature
    n = 0
    if r["cuisine"] and cuisine:
        if r["cuisine"] == cuisine:
            n += points["sameCuisine"]
        elif r["family"] and r["family"] == family:
            n += points["sameFamily"]
        else:
            n += points["otherFamily"]
    n += points["flavour"] * sum(1 for want in wants if want & sides)
    return n + points["occasion"] * len(occasions & theirOccasions)


def _top(r, slot, groups, served, rules):
    """The best `perSlot` (score, key, candidate) for one slot. Groups are walked from the best base down; effort
    and time only take points away, so the walk stops once a group's base cannot reach the last place kept."""
    p = rules["pairings"]
    points, keep = p["points"], p["perSlot"]
    wants = [w for w in ({b for mine, b in ((a, b), (b, a)) if mine in r["sides"]} for a, b in p["flavourPairs"]) if w]
    occasions = set(r["occasions"])
    effort = slot in p["effortSlots"]

    def penalty(c):
        if not effort:
            return 0
        n = 0
        if r["difficulty"] and c["difficulty"] and c["difficulty"] > r["difficulty"]:
            n += points["harder"]
        if r["minutes"] and c["minutes"] and c["minutes"] > r["minutes"]:
            n += points["longer"]
        return n

    def allowed(c):
        return c["key"] != r["key"] and not (r["dishKey"] and c["dishKey"] == r["dishKey"])

    scored = []
    bases = sorted(((_baseOf(r, signature, wants, occasions, points), members) for signature, members in groups),
                   key=lambda item: -item[0])
    for c in served.values():
        if allowed(c):
            signature = (c["cuisine"], c["family"], frozenset(c["sides"]), frozenset(c["occasions"]))
            total = _baseOf(r, signature, wants, occasions, points) + points["servedWith"] + penalty(c)
            if total > 0:
                scored.append((-total, c["key"], c))
    for base, members in bases:
        if base <= 0:
            break
        scored.sort(key=lambda item: (item[0], item[1]))
        del scored[keep:]
        if len(scored) == keep and -scored[-1][0] > base:
            break
        taken = 0
        for c in members:
            if c["key"] in served or not allowed(c):
                continue
            total = base + penalty(c)
            if total > 0:
                scored.append((-total, c["key"], c))
                taken += 1
                if not effort and taken == keep:        # the rest of the group scores the same, with later keys
                    break
    scored.sort(key=lambda item: (item[0], item[1]))
    return scored[:keep]


def pairAll(recipes, rules):
    """{key: [{"slot", "key", "rank", "why"}]} for every shown recipe with at least one pairing, slots in the rules
    file's order, ranks from 1 within a slot."""
    p = rules["pairings"]
    garnish = _garnish(rules)
    shown = [features(r, rules) for r in recipes if r.hiddenReason is None and r.course]
    byCourse = {}
    for f in shown:
        byCourse.setdefault(f["course"], []).append(f)
    groupsOf, indexOf = {}, {}
    result = {}
    for r in shown:
        pairs = []
        for slot in p["slots"].get(r["course"], []):
            courses = tuple(p["rowCourses"].get(r["course"], {}).get(slot) or p["slotCourses"][slot])
            if courses not in groupsOf:
                candidates = [c for course in courses for c in byCourse.get(course, [])]
                groupsOf[courses] = _groups(candidates)
                index = {}
                for c in candidates:
                    for word in c["dishWords"]:
                        index.setdefault(word, []).append(c)
                indexOf[courses] = index
            served = _servedMatches(r, indexOf[courses], garnish) if r["parts"] else {}
            top = _top(r, slot, groupsOf[courses], served, rules)
            pairs += [{"slot": slot, "key": key, "rank": rank,
                       "why": _whyOf(_contributions(r, c, slot, rules, garnish))}
                      for rank, (_, key, c) in enumerate(top, start=1)]
        if pairs:
            result[r["key"]] = pairs
    return result
