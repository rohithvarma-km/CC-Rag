def test_health(client):
    assert client.get("/health").status_code == 200


def test_me_no_token(client):
    assert client.get("/me").status_code == 401


def test_me_bad_token(client):
    assert client.get("/me", headers={"Authorization": "Bearer bad"}).status_code == 401


def test_me_good_token(client):
    r = client.get("/me", headers={"Authorization": "Bearer good"})
    assert r.status_code == 200 and r.json()["id"] == "user-1"
