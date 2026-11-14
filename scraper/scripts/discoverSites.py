"""
Milestone 1's one look at a recipe site before rules/sites.json is written:
its robots.txt, the sitemap it names, and (given a sitemap and a pattern) how
many of that sitemap's pages the pattern takes. Every request is net.crawl's:
the crawler's own name, 5 s apart per host. Run by hand; the scraper never
runs it.

    python scripts/discoverSites.py www.recipetineats.com
    python scripts/discoverSites.py www.recipetineats.com --sitemap URL --pattern REGEX
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import net  # noqa: E402
from sources import sites  # noqa: E402


def show(entries, limit=40):
    for loc, lastmod in entries[:limit]:
        print(f"  {loc}  {lastmod or '-'}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Look at one recipe site's robots.txt and sitemaps")
    parser.add_argument("host")
    parser.add_argument("--sitemap", help="a sitemap to list (otherwise the first robots.txt names)")
    parser.add_argument("--pattern", help="a recipeUrl candidate to try on that sitemap")
    args = parser.parse_args(argv)
    robots = sites.robotsFor({"site": "discovery", "host": args.host})
    named = robots.site_maps() or []
    print(f"robots.txt names {len(named) or 'no'} sitemap(s):", *named, sep="\n  ")
    print("a generic crawler may fetch /:", robots.can_fetch(sites.AGENT, f"https://{args.host}/"))
    print("Crawl-delay for us:", robots.crawl_delay(sites.AGENT))
    target = args.sitemap or (named[0] if named else None)
    if not target:
        print("no sitemap to read: try --sitemap https://<host>/sitemap_index.xml or /sitemap.xml")
        return 1
    kind, entries = sites.parseSitemap(net.crawl(target, binary=True))
    withLastmod = sum(1 for _, lastmod in entries if lastmod)
    print(f"{target} is a {kind} with {len(entries)} entries, {withLastmod} with lastmod")
    if not args.pattern:
        show(entries)
        return 0
    pattern = re.compile(args.pattern)
    taken = [entry for entry in entries if pattern.match(entry[0])]
    left = [entry for entry in entries if not pattern.match(entry[0])]
    allowed = sum(1 for loc, _ in taken if robots.can_fetch(sites.AGENT, loc))
    print(f"the pattern takes {len(taken)}, robots.txt allows {allowed} of them")
    print("taken (first 15):")
    show(taken, 15)
    print("left out (first 15):")
    show(left, 15)
    return 0


if __name__ == "__main__":
    sys.exit(main())
