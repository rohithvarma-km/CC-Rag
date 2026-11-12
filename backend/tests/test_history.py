import pytest

from app.config import Settings, get_settings
from app.services.history import load_history, trim_history


def rows(*pairs):
    return [{"role": r, "content": c, "extra": 1} for r, c in pairs]


def test_empty():
    assert trim_history([], 20, 1000) == []


def test_strips_extra_keys_and_preserves_order():
    out = trim_history(rows(("user", "a"), ("assistant", "b"), ("user", "c")), 20, 1000)
    assert out == [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}, {"role": "user", "content": "c"}]


def test_count_cap_keeps_latest():
    r = rows(*[("user" if i % 2 == 0 else "assistant", str(i)) for i in range(10)])
    out = trim_history(r, 4, 1000)
    assert [m["content"] for m in out] == ["6", "7", "8", "9"]
    out = trim_history(r, 3, 1000)  # window "7","8","9" starts on assistant -> dropped to user "8"
    assert [m["content"] for m in out] == ["8", "9"]


def test_char_trim_drops_oldest():
    r = rows(("user", "a" * 10), ("assistant", "b" * 10), ("user", "c" * 10), ("assistant", "d" * 10))
    out = trim_history(r, 20, 25)
    assert [m["content"][0] for m in out] == ["c", "d"]
    assert sum(len(m["content"]) for m in out) <= 25


def test_window_starts_with_user():
    out = trim_history(rows(("assistant", "x"), ("assistant", "y"), ("user", "z")), 20, 1000)
    assert out == [{"role": "user", "content": "z"}]


def test_only_assistant_gives_empty():
    assert trim_history(rows(("assistant", "x")), 20, 1000) == []


def test_char_limit_smaller_than_any_message():
    assert trim_history(rows(("user", "a" * 50)), 20, 10) == []


def test_zero_max_messages():
    assert trim_history(rows(("user", "a")), 0, 100) == []


class FakeQuery:
    def __init__(self, data):
        self.data = data
        self.ops = []

    def select(self, c):
        self.ops.append(("select", c))
        return self

    def eq(self, k, v):
        self.ops.append(("eq", k, v))
        return self

    def order(self, c, desc=False):
        self.ops.append(("order", c, desc))
        return self

    def limit(self, n):
        self.ops.append(("limit", n))
        return self

    def execute(self):
        return type("R", (), {"data": self.data})()


class FakeDB:
    def __init__(self, data):
        self.q = FakeQuery(data)
        self.tables = []

    def table(self, name):
        self.tables.append(name)
        return self.q


@pytest.fixture
def env(monkeypatch):
    for n in Settings.model_fields:
        monkeypatch.delenv(n.upper(), raising=False)
    get_settings.cache_clear()
    yield monkeypatch
    get_settings.cache_clear()


def test_load_history_reverses_and_queries(env):
    env.setenv("HISTORY_MAX_MESSAGES", "3")
    # DB returns newest first
    newest_first = [
        {"role": "assistant", "content": "4"},
        {"role": "user", "content": "3"},
        {"role": "assistant", "content": "2"},
    ]
    db = FakeDB(newest_first)
    out = load_history(db, "t1")
    assert db.tables == ["messages"]
    assert ("eq", "thread_id", "t1") in db.q.ops
    assert ("order", "created_at", True) in db.q.ops
    assert ("limit", 3) in db.q.ops
    # chronological: 2(assistant) dropped to start with user
    assert out == [{"role": "user", "content": "3"}, {"role": "assistant", "content": "4"}]


def test_load_history_empty(env):
    assert load_history(FakeDB([]), "t") == []
