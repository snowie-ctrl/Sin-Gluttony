"""
Chooses the basics (scrambled eggs, porridge, roast chicken...) from the four
meal sites' sitemap listings, which a dry run saved in data/raw/<site>/
listing.json, and writes rules/basics.json. For each basic the recipe whose
URL slug holds the basic's words with the fewest extra words wins, ties going
to the earlier site in SITE_ORDER; a basic no site has is written with no URL
and the dry-run report lists it. Run by hand; it asks no site anything.

    python scripts/findBasics.py            # print the choice
    python scripts/findBasics.py --write    # and write rules/basics.json
"""
import argparse
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
import pagecache  # noqa: E402
import store  # noqa: E402

SITE_ORDER = ("bbcgoodfood", "recipetineats", "budgetbytes", "pinchofyum", "loveandlemons")
MAX_EXTRA_WORDS = 3     # "perfect-scrambled-eggs" is a basic; "scrambled-eggs-with-smoked-salmon-and-chives" is not

# (name, a pattern for the slug's words). Matched as whole hyphen-separated words; a pattern
# that starts ^ and ends $ must be the whole slug, so "avocado-toast" is not toast.
BASICS = [
    ("scrambled eggs", r"scrambled-eggs?"),
    ("fried eggs", r"^(?:perfect-|air-fryer-)?fried-eggs?$"),
    ("boiled eggs", r"(?:soft-|hard-)?boiled-eggs?"),
    ("poached eggs", r"poached-eggs?"),
    ("omelette", r"omelet(?:te)?s?"),
    ("toast", r"^(?:buttered-|cinnamon-)?toast$"),
    ("porridge", r"^(?:perfect-|classic-|simple-|basic-)?(?:porridge|oatmeal)$"),
    ("pancakes", r"^(?:classic-|easy-|fluffy-|perfect-|basic-)?pancakes?$"),
    ("french toast", r"french-toast"),
    ("overnight oats", r"overnight-oats"),
    ("granola", r"^(?:homemade-|easy-|simple-)?granola$"),
    ("boiled rice", r"(?:boiled|steamed|perfect|fluffy|basic)-(?:white-|basmati-)?rice|how-to-cook-(?:white-|basmati-)?rice"),
    ("fried rice", r"^(?:easy-|egg-|simple-|classic-)?fried-rice$"),
    ("pasta", r"how-to-cook-pasta|^(?:simple-|basic-|plain-|easy-)?pasta$"),
    ("spaghetti bolognese", r"spaghetti-bolognese|bolognese"),
    ("macaroni cheese", r"^(?:classic-|easy-|best-|baked-|homemade-|ultimate-)?mac(?:aroni)?-(?:and-|n-)?cheese$"),
    ("tomato pasta", r"^(?:fresh-|simple-|easy-)?tomato-pasta(?:-sauce)?$|pasta-(?:al-)?pomodoro"),
    ("mashed potatoes", r"mash(?:ed)?-potato(?:es)?|potato-mash"),
    ("roast potatoes", r"roast(?:ed)?-potato(?:es)?"),
    ("baked potato", r"^(?:classic-|perfect-|crisp-)?(?:baked|jacket)-potato(?:es)?$"),
    ("chips", r"^(?:chunky-|best-ever-|homemade-|easy-)?(?:oven-)?chips$"),
    ("roast chicken", r"(?:whole-)?roast(?:ed)?-chicken"),
    ("chicken breast", r"(?:baked|pan-fried|grilled|juicy)-chicken-breasts?"),
    ("grilled cheese", r"grilled-cheese(?:-sandwich)?|cheese-toastie"),
    ("green salad", r"(?:green|garden|simple|side)-salad"),
    ("tomato soup", r"tomato-soup"),
    ("chicken soup", r"chicken-(?:noodle-)?soup"),
    ("vegetable soup", r"vegetable-soup"),
    ("roast vegetables", r"roast(?:ed)?-vegetables|roast(?:ed)-veg"),
    ("broccoli", r"(?:steamed|roast|roasted)-broccoli"),
    ("green beans", r"^(?:simple-|easy-|sauteed-|steamed-)?green-beans$"),
    ("burgers", r"^(?:beef-|classic-|perfect-)?burgers?$"),
    ("meatballs", r"^(?:baked-|homemade-|oven-baked-|classic-|easy-|beef-)?meatballs$"),
    ("chilli con carne", r"chil(?:l)?i-con-carne"),
    ("stir fry", r"^(?:simple-|quick-|easy-)?stir-fry$"),
    ("chicken curry", r"chicken-curry"),
    ("shepherd's pie", r"shepherds?-pie|cottage-pie"),
    ("lasagne", r"lasagn(?:e|a)"),
    ("tacos", r"(?:beef-|chicken-)?tacos"),
    ("quesadillas", r"quesadillas?"),
    ("salmon", r"^(?:easy-|simple-|best-|perfect-)?(?:baked|oven-baked|pan-fried|roast)-salmon$"),
    ("steak", r"^(?:pan-fried-|perfect-|rump-|sirloin-)?steak$"),
    ("pork chops", r"^(?:pan-fried-|baked-|homemade-|oven-baked-|juicy-|easy-)?pork-chops$"),
    ("sausage and mash", r"sausages?-(?:and-)?mash|bangers-(?:and-)?mash"),
    ("guacamole", r"guacamole"),
    ("hummus", r"hummus|houmous"),
    ("garlic bread", r"garlic-bread"),
    ("gravy", r"gravy"),
    ("vinaigrette", r"^(?:classic-|simple-|easy-|basic-)?vinaigrette$"),
    ("banana bread", r"^(?:homemade-|easy-|classic-|best-|simple-)?banana-bread$"),
    ("chocolate chip cookies", r"chocolate-chip-cookies"),
    ("sponge cake", r"^(?:classic-|easy-|best-|simple-|ultimate-)?(?:victoria-sponge(?:-cake)?|vanilla-cake|sponge-cake)$"),
    ("smoothie", r"^(?:banana-|berry-|fruit-|breakfast-)?smoothie$"),
    ("bacon sandwich", r"^(?:classic-|best-|ultimate-)?bacon-(?:sandwich|sarnie|butty)$"),
]




def slugOf(url):
    return urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1].lower()


def _words(text):
    return [word for word in text.split("-") if word]


def candidates(pattern, listings):
    """(extra words, site rank, url) for every listed URL whose slug holds the pattern as whole words, best first."""
    whole = re.compile(rf"(?:^|-)({pattern})(?:-|$)")
    found = []
    for rank, site in enumerate(SITE_ORDER):
        for url, _ in listings.get(site, []):
            slug = slugOf(url)
            match = whole.search(slug)
            if match:
                extra = len(_words(slug)) - len(_words(match.group(1)))
                if extra <= MAX_EXTRA_WORDS:
                    found.append((extra, rank, url))
    return sorted(found)


def chooseBasics(listings, basics=BASICS):
    chosen = []
    for name, pattern in basics:
        best = candidates(pattern, listings)
        urls, sitesSeen = [], set()
        for _, rank, url in best:          # the best page of each site, in ranking order
            if rank not in sitesSeen:
                sitesSeen.add(rank)
                urls.append(url)
        chosen.append({"name": name, "url": urls[0] if urls else None, "urls": urls})
    return chosen


def main(argv=None):
    parser = argparse.ArgumentParser(description="Choose the basics from the meal sites' saved sitemap listings")
    parser.add_argument("--write", action="store_true", help="write rules/basics.json")
    args = parser.parse_args(argv)
    listings = {site: pagecache.listing(site) for site in SITE_ORDER}
    for site, entries in listings.items():
        print(f"{site}: {len(entries)} recipe URLs listed" + ("" if entries else " (run a dry run first)"))
    chosen = chooseBasics(listings)
    for basic in chosen:
        print(f"  {basic['name']:24} {basic['url'] or '(no site has it)'}")
    print(f"{sum(1 for b in chosen if b['url'])} of {len(chosen)} found")
    if args.write:
        store.writeJson(config.RULES_DIR / "basics.json", chosen)
        print(f"wrote {config.RULES_DIR / 'basics.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
