# Copied from Artemis/Pageturner/server/tests/fakes.py at 7acc9ec; changes: rowcounts for UPDATE, failOn may be a
# callable of (sql, params), FakeConn counts commits and rollbacks (one batch commits once per recipe), and a
# SELECT left unread refuses the next statement or commit, as mysql.connector's unbuffered cursor does.
"""A stand-in MySQL connection for route tests: rows are queued in the order the route will ask for them, and every
statement is recorded so a test can check what would have been written."""
import re


class UnreadResult(Exception):
    """mysql.connector's InternalError("Unread result found")."""


class FakeCursor:
    def __init__(self, fetchone=(), fetchall=(), lastrowids=None, failOn=None, rowcounts=()):
        self.executed = []
        self._one = list(fetchone)
        self._all = list(fetchall)
        self._ids = {table: list(ids) for table, ids in (lastrowids or {}).items()}
        self._failOn = failOn
        self._rowcounts = list(rowcounts)
        self.lastrowid = None
        self.rowcount = 0
        self.dictionary = True
        self.unread = False

    def _shaped(self, row):
        if isinstance(row, dict) and not self.dictionary:
            return tuple(row.values())
        return row

    def execute(self, sql, params=None):
        flat = " ".join(sql.split())
        # As mysql.connector's unbuffered cursor: a SELECT whose rows were never fetched refuses the next statement
        # (this is how /lists/create's unread FOR UPDATE lock reached the real server untested).
        if self.unread:
            raise UnreadResult(f"Unread result found (before: {flat[:60]})")
        self.unread = flat.startswith("SELECT")
        self.executed.append((flat, params))
        failing = self._failOn(flat, params) if callable(self._failOn) else (self._failOn and self._failOn in flat)
        if failing:
            raise RuntimeError(f"forced failure on: {flat[:60]}")
        match = re.match(r"INSERT (?:IGNORE )?INTO (\w+)", flat)
        if match and self._ids.get(match.group(1)):
            self.lastrowid = self._ids[match.group(1)].pop(0)
        if flat.startswith("UPDATE"):
            self.rowcount = self._rowcounts.pop(0) if self._rowcounts else 0

    def fetchone(self):
        self.unread = False
        return self._shaped(self._one.pop(0)) if self._one else None

    def fetchall(self):
        self.unread = False
        return [self._shaped(r) for r in self._all.pop(0)] if self._all else []

    def close(self):
        pass

    def statements(self, prefix):
        return [(sql, params) for sql, params in self.executed if sql.startswith(prefix)]


class FakeConn:
    def __init__(self, cur):
        self.cur = cur
        self.commits = 0
        self.rollbacks = 0
        self.closed = False
        self.autocommit = True

    def cursor(self, dictionary=False):
        self.cur.dictionary = dictionary
        return self.cur

    def commit(self):
        if self.cur.unread:
            raise UnreadResult("Unread result found (before: COMMIT)")
        self.commits += 1

    def rollback(self):
        # A rollback reads and drops any rows still waiting, as the real connection does.
        self.cur.unread = False
        self.rollbacks += 1

    def close(self):
        self.closed = True
