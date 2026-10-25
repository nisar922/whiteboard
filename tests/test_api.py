def make_board(client, user, title="T"):
    r = client.post("/boards", json={"title": title}, headers=user["headers"])
    assert r.status_code == 201
    return r.json()
def test_register_and_login(new_user):
    assert new_user()["token"]
def test_duplicate_email_rejected(client, new_user):
    u = new_user()
    r = client.post("/auth/register", json={"email": u["email"], "password": "another123"})
    assert r.status_code == 400
def test_wrong_password_rejected(client, new_user):
    u = new_user()
    r = client.post("/auth/login", json={"email": u["email"], "password": "wrong"})
    assert r.status_code == 401
def test_password_is_not_returned(client):
    r = client.post("/auth/register", json={"email": "nopw@test.com", "password": "secret123"})
    if r.status_code == 201:
        assert "password" not in r.text
def test_boards_require_login(client):
    assert client.get("/boards").status_code in (401, 403)
def test_other_user_cannot_access_board(client, new_user):
    a, b = new_user(), new_user()
    board = make_board(client, a)
    assert client.get(f"/boards/{board['id']}", headers=b["headers"]).status_code == 404
    assert client.delete(f"/boards/{board['id']}", headers=b["headers"]).status_code == 404
def test_join_code_gives_access(client, new_user):
    a, b = new_user(), new_user()
    board = make_board(client, a)
    r = client.post("/boards/join", json={"code": board["join_code"]}, headers=b["headers"])
    assert r.status_code == 200
    assert client.get(f"/boards/{board['id']}", headers=b["headers"]).status_code == 200
    listed = client.get("/boards", headers=b["headers"]).json()
    assert board["id"] in [x["id"] for x in listed]
def test_member_cannot_delete_board(client, new_user):
    a, b = new_user(), new_user()
    board = make_board(client, a)
    client.post("/boards/join", json={"code": board["join_code"]}, headers=b["headers"])
    assert client.delete(f"/boards/{board['id']}", headers=b["headers"]).status_code == 404
    assert client.delete(f"/boards/{board['id']}", headers=a["headers"]).status_code == 204
def test_invalid_join_code(client, new_user):
    b = new_user()
    r = client.post("/boards/join", json={"code": "ZZZZZZ"}, headers=b["headers"])
    assert r.status_code == 404
def test_join_is_rate_limited(client, new_user):
    b = new_user()
    codes = [
        client.post("/boards/join", json={"code": "ZZZZZZ"}, headers=b["headers"]).status_code
        for _ in range(11)
    ]
    assert codes[-1] == 429