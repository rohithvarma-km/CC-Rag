"""Reusable in-memory fake of the supabase-py query builder for backend tests."""
import copy
import itertools
from types import SimpleNamespace

_ids = itertools.count(1)


class FakeQuery:
    def __init__(self, db, table):
        self.db, self.table_name = db, table
        self.op = None
        self.payload = None
        self.filters: list[tuple[str, str, object]] = []
        self.order_by = None
        self.limit_n = None
        self.single_mode = False

    # builders
    def select(self, *a, **k): self.op = "select"; return self
    def insert(self, p, *a, **k): self.op = "insert"; self.payload = p; return self
    def update(self, p, *a, **k): self.op = "update"; self.payload = p; return self
    def delete(self, *a, **k): self.op = "delete"; return self
    def eq(self, col, val): self.filters.append(("eq", col, val)); return self
    def in_(self, col, vals): self.filters.append(("in", col, list(vals))); return self
    def or_(self, expr): self.db.or_calls.append((self.table_name, expr)); return self
    def order(self, col, desc=False): self.order_by = (col, desc); return self
    def limit(self, n): self.limit_n = n; return self
    def maybe_single(self): self.single_mode = True; return self
    def single(self): self.single_mode = True; return self

    def _matches(self, row):
        for kind, col, val in self.filters:
            if kind == "eq" and row.get(col) != val:
                return False
            if kind == "in" and row.get(col) not in val:
                return False
        return True

    def execute(self):
        db = self.db
        failure = db.fail_on.get((self.table_name, self.op))
        if failure is not None:
            raise failure
        rows = db.tables.setdefault(self.table_name, [])
        if self.op == "select":
            out = [copy.deepcopy(r) for r in rows if self._matches(r)]
            if self.order_by:
                col, desc = self.order_by
                out.sort(key=lambda r: (r.get(col) is None, r.get(col)), reverse=desc)
            if self.limit_n is not None:
                out = out[: self.limit_n]
            data = (out[0] if out else None) if self.single_mode else out
        elif self.op == "insert":
            db.writes.append((self.table_name, "insert", self.payload))
            items = self.payload if isinstance(self.payload, list) else [self.payload]
            data = []
            for it in items:
                row = dict(it)
                row.setdefault("id", f"{self.table_name}-{next(_ids)}")
                rows.append(row)
                data.append(copy.deepcopy(row))
        elif self.op == "update":
            db.writes.append((self.table_name, "update", self.payload))
            data = []
            for r in rows:
                if self._matches(r):
                    r.update(self.payload)
                    data.append(copy.deepcopy(r))
        elif self.op == "delete":
            db.writes.append((self.table_name, "delete", None))
            data = [copy.deepcopy(r) for r in rows if self._matches(r)]
            rows[:] = [r for r in rows if not self._matches(r)]
        else:
            data = []
        return SimpleNamespace(data=data)


class FakeRpc:
    def __init__(self, db, name, params):
        self.db, self.name, self.params = db, name, params

    def execute(self):
        self.db.rpc_calls.append((self.name, self.params))
        failure = self.db.fail_on.get(("rpc", self.name))
        if failure is not None:
            raise failure
        return SimpleNamespace(data=self.db.rpc_results.get(self.name, []))


class FakeDB:
    """FakeDB(threads=[...], messages=[...], documents=[...]) seeds tables.

    Attributes: tables, writes [(table, op, payload)], rpc_results {name: data},
    rpc_calls [(name, params)], or_calls [(table, expr)], fail_on {(table, op): Exception}.
    """

    def __init__(self, **tables):
        self.tables = {k: [dict(r) for r in v] for k, v in tables.items()}
        self.writes: list[tuple] = []
        self.rpc_results: dict = {}
        self.rpc_calls: list[tuple] = []
        self.or_calls: list[tuple] = []
        self.fail_on: dict = {}

    def table(self, name): return FakeQuery(self, name)
    def rpc(self, name, params=None): return FakeRpc(self, name, params or {})
