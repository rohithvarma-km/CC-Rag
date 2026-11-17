import pytest

from app.services.record_manager import decide

H1, H2 = "a" * 64, "b" * 64


@pytest.mark.parametrize(
    "existing,incoming,expected",
    [
        (None, H1, "created"),
        ({"content_hash": H1, "status": "completed"}, H1, "unchanged"),
        ({"content_hash": H1, "status": "processing"}, H1, "unchanged"),
        ({"content_hash": H1, "status": "failed"}, H1, "retry"),
        ({"content_hash": H1, "status": "pending"}, H1, "retry"),
        ({"content_hash": H1, "status": "completed"}, H2, "updated"),
        ({"content_hash": H1, "status": "failed"}, H2, "updated"),
        ({"content_hash": H1, "status": "pending"}, H2, "updated"),
        ({"content_hash": H1, "status": "processing"}, H2, "conflict"),
        # legacy rows (pre-Module 3) have no stored hash: treated as changed
        ({"content_hash": None, "status": "completed"}, H1, "updated"),
        ({"content_hash": None, "status": "processing"}, H1, "conflict"),
    ],
)
def test_decide(existing, incoming, expected):
    assert decide(existing, incoming) == expected
