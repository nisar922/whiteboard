from contextlib import ExitStack
def make_board(client, user, default_can_edit=True):
    r = client.post(
        "/boards",
        json={"title": "Room", "default_can_edit": default_can_edit},
        headers=user["headers"],
    )
    assert r.status_code == 201
    return r.json()
def join(client, user, board):
    r = client.post("/boards/join", json={"code": board["join_code"]},
                    headers=user["headers"])
    assert r.status_code == 200
def ws(client, board, user):
    return client.websocket_connect(f"/ws/boards/{board['id']}?token={user['token']}")
def recv_type(sock, kind, limit=30):
    for _ in range(limit):
        m = sock.receive_json()
        if m["type"] == kind:
            return m
    raise AssertionError(f"never received a '{kind}' message")
def collect_until(sock, kind, limit=30):
    seen = []
    for _ in range(limit):
        m = sock.receive_json()
        seen.append(m["type"])
        if m["type"] == kind:
            return seen
    raise AssertionError(f"never received '{kind}', saw {seen}")
def wait_roster(sock, user_id, can_edit, limit=30):
    for _ in range(limit):
        m = sock.receive_json()
        if m["type"] == "roster":
            row = next((x for x in m["members"] if x["user_id"] == user_id), None)
            if row and row["can_edit"] == can_edit:
                return
    raise AssertionError("roster never showed the new permission")
def recv_presence(sock, emails, limit=30):
    for _ in range(limit):
        m = sock.receive_json()
        if m["type"] == "presence" and all(e in m["users"] for e in emails):
            return m
    raise AssertionError("presence never listed all users")
def test_empty_room_name_is_rejected(client, new_user):
    a = new_user()
    r = client.post("/boards", json={"title": ""}, headers=a["headers"])
    assert r.status_code == 422
def test_only_owner_sees_room_code(client, new_user):
    a, b = new_user(), new_user()
    board = make_board(client, a)
    join(client, b, board)
    with ws(client, board, a) as wa, ws(client, board, b) as wb:
        init_a = recv_type(wa, "init")
        init_b = recv_type(wb, "init")
        assert init_a["room"]["code"] == board["join_code"]
        assert init_b["room"]["code"] is None
def test_view_only_user_cannot_draw(client, new_user):
    a, b = new_user(), new_user()
    board = make_board(client, a, default_can_edit=False)
    join(client, b, board)
    with ws(client, board, a) as wa, ws(client, board, b) as wb:
        recv_type(wa, "init")
        init_b = recv_type(wb, "init")
        assert init_b["you"]["can_edit"] is False
        wb.send_json({"type": "point", "id": "x1", "p": {"x": 1, "y": 2}})
        wb.send_json({"type": "cursor", "x": 0, "y": 0})
        seen = collect_until(wa, "cursor")   # cursor se pehle point nahi aana chahiye
        assert "point" not in seen
def test_owner_can_grant_draw_permission(client, new_user):
    a, b = new_user(), new_user()
    board = make_board(client, a, default_can_edit=False)
    join(client, b, board)
    b_id = client.get("/auth/me", headers=b["headers"]).json()["id"]
    with ws(client, board, a) as wa, ws(client, board, b) as wb:
        recv_type(wa, "init")
        recv_type(wb, "init")
        wa.send_json({"type": "set_perm", "user_id": b_id, "can_edit": True})
        wait_roster(wb, b_id, True)
        wb.send_json({"type": "point", "id": "y1", "p": {"x": 3, "y": 4}})
        m = recv_type(wa, "point")
        assert m["id"] == "y1"
def test_non_owner_cannot_change_permissions(client, new_user):
    a, b = new_user(), new_user()
    board = make_board(client, a, default_can_edit=False)
    join(client, b, board)
    b_id = client.get("/auth/me", headers=b["headers"]).json()["id"]
    with ws(client, board, a) as wa, ws(client, board, b) as wb:
        recv_type(wa, "init")
        recv_type(wb, "init")
        wb.send_json({"type": "set_perm", "user_id": b_id, "can_edit": True})
        wb.send_json({"type": "point", "id": "z1", "p": {"x": 1, "y": 1}})
        wb.send_json({"type": "cursor", "x": 0, "y": 0})
        seen = collect_until(wa, "cursor")
        assert "point" not in seen
def test_room_is_full_after_10_people(client, new_user):
    owner = new_user()
    board = make_board(client, owner)
    users = [owner]
    for _ in range(10):
        u = new_user()
        join(client, u, board)
        users.append(u)
    with ExitStack() as stack:
        sockets = []
        for u in users[:10]:
            sock = stack.enter_context(ws(client, board, u))
            recv_type(sock, "init")
            sockets.append(sock)
        recv_presence(sockets[-1], [u["email"] for u in users[:10]])
        with ws(client, board, users[10]) as extra:
            msg = extra.receive_json()
            assert msg["type"] == "error"
            assert "full" in msg["message"].lower()