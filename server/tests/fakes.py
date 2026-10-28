# Copied from Artemis/Pageturner/server/tests/fakes.py at 7acc9ec; changes: rowcounts for UPDATE, failOn may be a
# callable of (sql, params), and FakeConn counts commits and rollbacks (one batch commits once per recipe).
"""A stand-in MySQL connection for route tests: rows are queued in the order the route will ask for them, and every
statement is recorded so a test can check what would have been written."""
import re


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

    def _shaped(self, row):
        if isinstance(row, dict) and not self.dictionary:
            return tuple(row.values())
        return row

    def execute(self, sql, params=None):
        flat = " ".join(sql.split())
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
        return self._shaped(self._one.pop(0)) if self._one else None

    def fetchall(self):
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
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True
