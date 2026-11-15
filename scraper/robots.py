"""
A robots.txt read the way Google reads one (RFC 9309), because the standard
library's parser ignores `*` and `$` and would let the crawler fetch pages a
site disallows with them. Our group is the one whose User-agent is the longest
case-insensitive prefix of our name, else `*`; within it the longest matching
rule wins and Allow wins a tie. `*` matches any run of characters, a trailing
`$` anchors the end, and the query string is part of the path. Paths and
patterns are compared with unreserved characters unescaped.
"""
import re
from urllib.parse import quote, urlsplit

_UNRESERVED = re.compile(r"[A-Za-z0-9\-._~]")
_ESCAPE = re.compile(r"%([0-9A-Fa-f]{2})")
_KEEP = "".join(chr(c) for c in range(0x21, 0x7F))     # printable ASCII stays as it is; anything else is escaped


def _normal(path):
    """%7E -> ~ and %2d -> -, other escapes in capitals, non-ASCII escaped as UTF-8."""
    def one(match):
        char = chr(int(match.group(1), 16))
        return char if _UNRESERVED.fullmatch(char) else "%" + match.group(1).upper()
    return _ESCAPE.sub(one, quote(path, safe=_KEEP))


def _rule(allow, path):
    """(allow, length, regex): the length is the normalised pattern's, so %2D and - weigh the same."""
    anchored = path.endswith("$")
    body = _normal(path[:-1] if anchored else path)
    regex = re.compile(".*".join(re.escape(part) for part in body.split("*")) + (r"\Z" if anchored else ""))
    return allow, len(body) + anchored, regex


class Rules:
    def __init__(self, groups, sitemaps):
        self.groups = groups        # [(agents, [(allow, length, regex)], crawlDelay or None)]
        self.sitemaps = sitemaps

    @classmethod
    def parse(cls, text):
        groups, sitemaps, current, collecting = [], [], None, False
        for line in text.removeprefix("﻿").splitlines():
            key, sep, value = line.split("#", 1)[0].partition(":")
            if not sep:
                continue
            key, value = key.strip().lower(), value.strip()
            if key == "sitemap":
                sitemaps.append(value)
            elif key == "user-agent":
                if not collecting:
                    current = ([], [], [None])
                    groups.append(current)
                    collecting = True
                current[0].append(value.split("/", 1)[0].strip().lower())   # "Name/1.0" is matched as "Name"
            elif key in ("allow", "disallow", "crawl-delay"):
                collecting = False
                if current is None:
                    continue        # a rule before any User-agent belongs to nobody
                if key == "crawl-delay":
                    if current[2][0] is None:
                        try:
                            current[2][0] = float(value)
                        except ValueError:
                            pass        # an unreadable delay is no delay
                elif value:         # an empty Disallow (or Allow) allows everything: no rule
                    current[1].append(_rule(key == "allow", value))
        return cls([(agents, rules, delay[0]) for agents, rules, delay in groups], sitemaps)

    def _ours(self, agent):
        """The groups that name us most specifically, merged; else the `*` groups."""
        agent = agent.lower()
        best, chosen = -1, []
        for agents, rules, delay in self.groups:
            length = max((len(token) for token in agents if token != "*" and token and agent.startswith(token)),
                         default=-1)
            if length < 0:
                continue
            if length > best:
                best, chosen = length, []
            if length == best:
                chosen.append((rules, delay))
        if chosen:
            return chosen
        return [(rules, delay) for agents, rules, delay in self.groups if "*" in agents]

    def allows(self, agent, url):
        parts = urlsplit(url)
        path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        if parts.path == "/robots.txt":
            return True
        path = _normal(path)
        verdict, longest = True, -1
        for rules, _ in self._ours(agent):
            for allow, length, regex in rules:
                if regex.match(path) and (length > longest or (length == longest and allow)):
                    verdict, longest = allow, length
        return verdict

    def crawlDelay(self, agent):
        delays = [delay for _, delay in self._ours(agent) if delay is not None]
        return delays[0] if delays else None
