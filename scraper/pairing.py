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
kept, equal scores ordered by tieKey (the same every pass, but spread over the catalog), each with a why: the one or two largest parts in plain words.
Every number and word is in the rules file.
"""
import hashlib
import heapq
import re

from matching import plainText, singular

WHY_MAX = 120               # plutus stores a why of up to 120 characters
_STOP = re.compile(r"[.!?;:\n]")
_SPLIT = re.compile(r",|&|\band\b|\bor\b|\bplus\b")
_MASK = (1 << 64) - 1


def _words(text):
    return [singular(w) for w in plainText(text).split()]


def _phrasePatterns(phrases):
    return [re.compile(r"\b" + r"\s+".join(map(re.escape, p.split())) + r"\b") for p in phrases]


def _servedWith(recipe, rules):
    """(parts, phrases) of every "serve with ..." in the description and steps: each part a set of plain singular
    words, each phrase the whole of it before splitting (" fish and chip "), so a dish named with "and" still
    matches."""
    served = rules["pairings"]["servedWith"]
    patterns = _phrasePatterns(served["phrases"])
    garnishPhrases = [" ".join(_words(p)) for p in served["garnishPhrases"]]
    texts = [recipe.description or ""] + [s.text or "" for s in recipe.steps]
    parts, phrases = [], []
    for text in texts:
        lower = text.lower()
        for pattern in patterns:
            for found in pattern.finditer(lower):
                rest = lower[found.end():]
                stop = _STOP.search(rest)
                phrase = rest[:stop.start()] if stop else rest
                whole = f" {' '.join(_words(phrase))} "
                if not any(f" {g} " in whole for g in garnishPhrases):
                    phrases.append(whole)
                for piece in _SPLIT.split(phrase):
                    words = _words(piece)
                    padded = f" {' '.join(words)} "
                    if words and not any(f" {g} " in padded for g in garnishPhrases):
                        parts.append(set(words))
    return parts, phrases


def servedWithParts(recipe, rules):
    """The parts of every "serve with ..." phrase in the description and steps, each a set of plain singular words."""
    return _servedWith(recipe, rules)[0]


def _flavourSides(recipe, rules):
    """The flavour tags, plus each side in flavourWords (rich, fresh, cooling) that at least flavourMinLines of the
    ingredient lines name: one knob of butter does not make a dish rich."""
    p = rules["pairings"]
    sides = {t["tag"] for t in recipe.tags if t.get("type") == "flavour"}
    names = [f" {' '.join(_words(line.name or line.line))} " for line in recipe.ingredients]
    for side, words in p["flavourWords"].items():
        phrases = [f" {' '.join(_words(w))} " for w in words]
        if sum(1 for name in names if any(ph in name for ph in phrases)) >= p["flavourMinLines"]:
            sides.add(side)
    return sides


def _spread(key):
    """A 64-bit number from a key, so ties are spread over the catalog the same way every pass."""
    return int.from_bytes(hashlib.sha1(key.encode("utf-8")).digest()[:8], "big")


def tieKey(rKey, cKey):
    """Equal scores are ordered by this: the same from one pass to the next, but not the same few recipes (the
    lowest keys) for every recipe in the catalog."""
    return _spread(rKey) ^ _spread(cKey)


def features(recipe, rules):
    """What scoring reads from a recipe, worked out once per pass."""
    p = rules["pairings"]
    families = frozenset(name for name, members in p["cuisineFamilies"].items() if recipe.cuisine in members)
    dishWords = set((recipe.dishKey or plainText(recipe.title)).split())
    parts, phrases = _servedWith(recipe, rules)
    return {"key": recipe.key, "spread": _spread(recipe.key), "title": recipe.title,
            "dishKey": recipe.dishKey or " ".join(sorted(dishWords)), "dishWords": dishWords,
            "course": recipe.course, "cuisine": recipe.cuisine, "families": families,
            "difficulty": recipe.difficulty, "minutes": recipe.totalMinutes,
            "occasions": frozenset(t["tag"] for t in recipe.tags if t.get("type") == "occasion"),
            "sides": frozenset(_flavourSides(recipe, rules)), "parts": parts, "phrases": phrases}


def _garnish(rules):
    return {singular(w) for w in rules["pairings"]["servedWith"]["garnishWords"]}


def _named(r, c, garnish):
    """Whether the recipe's "serve with" names candidate c: all its dish words in one part, or its whole dish key in
    the phrase; garnish words never match on their own."""
    if not (c["dishWords"] - garnish):
        return False
    return (any(c["dishWords"] <= part for part in r["parts"])
            or any(f" {c['dishKey']} " in phrase for phrase in r["phrases"]))


def _flavourWants(r, rules):
    """[(theirs, mine)] per flavour pair the recipe is one side of. A recipe that is both sides of a pair (rich and
    fresh) is neither, so it never reads "a rich side for a fresh main" beside its own richness."""
    wants = []
    for a, b in rules["pairings"]["flavourPairs"]:
        if (a in r["sides"]) != (b in r["sides"]):
            mine, theirs = (a, b) if a in r["sides"] else (b, a)
            wants.append((theirs, mine))
    return wants


def _flavourMatches(wants, sides):
    return [(theirs, mine) for theirs, mine in wants if theirs in sides and mine not in sides]


def _cuisinePart(r, cuisine, families, points):
    """(points, "same" | the shared family | None) for the cuisine part; (0, None) when either cuisine is unset. A
    cuisine may sit in two families (Cuban: Latin American and Caribbean); sharing either counts."""
    if not (r["cuisine"] and cuisine):
        return 0, None
    if r["cuisine"] == cuisine:
        return points["sameCuisine"], "same"
    shared = sorted(r["families"] & families)
    if shared:
        return points["sameFamily"], shared[0]
    return points["otherFamily"], None


def _contributions(r, c, slot, rules, garnish):
    p = rules["pairings"]
    points, why = p["points"], p["why"]
    found = []
    if (r["parts"] or r["phrases"]) and _named(r, c, garnish):
        found.append((points["servedWith"], why["servedWith"].format(dish=c["title"].lower())))
    n, family = _cuisinePart(r, c["cuisine"], c["families"], points)
    if family == "same":
        found.append((n, why["sameCuisine"]))
    elif family:
        found.append((n, why["sameFamily"].format(family=p["familyWords"].get(family, family))))
    elif n:
        found.append((n, None))
    if slot in p["effortSlots"]:
        if r["difficulty"] and c["difficulty"] and c["difficulty"] > r["difficulty"]:
            found.append((points["harder"], None))
        if r["minutes"] and c["minutes"] and c["minutes"] > r["minutes"]:
            found.append((points["longer"], None))
    for theirs, mine in _flavourMatches(_flavourWants(r, rules), c["sides"]):
        found.append((points["flavour"], why["flavour"].format(
            theirs=theirs, slot=p["slotNouns"].get(slot, slot), mine=mine, course=r["course"])))
    for occasion in sorted(r["occasions"] & c["occasions"]):
        found.append((points["occasion"], why["occasion"].format(occasion=p["occasionWords"].get(occasion, occasion))))
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
    """{key: candidate} for every candidate the recipe's "serve with" names, found through a word index rather than
    by testing every candidate."""
    words = set().union(*r["parts"], *(set(phrase.split()) for phrase in r["phrases"]))
    found = {}
    for word in words:
        for c in wordIndex.get(word, ()):
            if c["key"] not in found and _named(r, c, garnish):
                found[c["key"]] = c
    return found


def _signature(c):
    return (c["cuisine"], c["families"], c["sides"], c["occasions"])


def _groups(candidates):
    """Candidates that differ only in key, dish, effort and time score the same apart from effort and time: one group
    per (cuisine, families, sides, occasions)."""
    groups = {}
    for c in candidates:
        groups.setdefault(_signature(c), []).append(c)
    return list(groups.items())


def _baseOf(r, signature, wants, points):
    """A group's points before "serve with", effort and time (the same sums as _contributions)."""
    cuisine, families, sides, occasions = signature
    n = _cuisinePart(r, cuisine, families, points)[0]
    n += points["flavour"] * len(_flavourMatches(wants, sides))
    return n + points["occasion"] * len(r["occasions"] & occasions)


def _top(r, slot, groups, served, rules):
    """The best `perSlot` (-score, tie, key, candidate) for one slot. Groups are walked from the best base down;
    effort and time only take points away, so the walk stops once a group's base cannot reach the last place kept."""
    p = rules["pairings"]
    points, keep = p["points"], p["perSlot"]
    wants = _flavourWants(r, rules)
    effort = slot in p["effortSlots"]
    mine = r["spread"]

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
        return c["key"] != r["key"] and not (r["dishKey"] and c["dishKey"] == r["dishKey"]) and c["key"] not in served

    scored = []
    for c in served.values():
        if c["key"] != r["key"] and not (r["dishKey"] and c["dishKey"] == r["dishKey"]):
            total = _baseOf(r, _signature(c), wants, points) + points["servedWith"] + penalty(c)
            if total > 0:
                scored.append((-total, mine ^ c["spread"], c["key"], c))
    bases = sorted(((_baseOf(r, signature, wants, points), members) for signature, members in groups),
                   key=lambda item: -item[0])
    for base, members in bases:
        if base <= 0:
            break
        scored.sort(key=lambda item: item[:3])
        del scored[keep:]
        if len(scored) == keep and -scored[-1][0] > base:
            break
        if effort:
            for c in members:
                total = base + penalty(c)
                if total > 0 and allowed(c):
                    scored.append((-total, mine ^ c["spread"], c["key"], c))
        else:       # the whole group scores `base`: only its `keep` first by tie can be kept
            want = keep + len(served) + 8
            first = [c for c in heapq.nsmallest(want, members, key=lambda c: mine ^ c["spread"]) if allowed(c)]
            if len(first) < keep < len(members) and len(members) > want:      # many of the dish left out: all of it
                first = [c for c in sorted(members, key=lambda c: mine ^ c["spread"]) if allowed(c)]
            scored += [(-base, mine ^ c["spread"], c["key"], c) for c in first[:keep]]
    scored.sort(key=lambda item: item[:3])
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
            served = _servedMatches(r, indexOf[courses], garnish) if r["parts"] or r["phrases"] else {}
            top = _top(r, slot, groupsOf[courses], served, rules)
            pairs += [{"slot": slot, "key": key, "rank": rank,
                       "why": _whyOf(_contributions(r, c, slot, rules, garnish))}
                      for rank, (_, _, key, c) in enumerate(top, start=1)]
        if pairs:
            result[r["key"]] = pairs
    return result
