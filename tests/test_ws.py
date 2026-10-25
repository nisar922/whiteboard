import pytest
from starlette.websockets import WebSocketDisconnect
def recv_type(ws, kind, limit=15):
    for _ in range(limit):
        m = ws.receive_json()
        if m["type"] == kind:
            return m
    raise AssertionError(f"never received a '{kind}' message")
def recv_presence(ws, emails, limit=15):
    for _ in range(limit):
        m = ws.receive_json()
        if m["type"] == "presence" and all(e in m["users"] for e in emails):
            return m
    raise AssertionError("presence never listed all users")
def make_board(client, user):
    r = client.post("/boards", json={"title": "T"}, headers=user["headers"])
    return r.json()
def test_ws_rejects_bad_token(client, new_user):
    board = make_board(client, new_user())
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/boards/{board['id']}?token=garbage"):
            pass
def test_ws_rejects_user_without_access(client, new_user):
    a, b = new_user(), new_user()
    board = make_board(client, a)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/boards/{board['id']}?token={b['token']}"):
            pass
def test_drawing_syncs_between_two_users(client, new_user):
    a, b = new_user(), new_user()
    board = make_board(client, a)
    client.post("/boards/join", json={"code": board["join_code"]}, headers=b["headers"])
    url = f"/ws/boards/{board['id']}?token="
    with client.websocket_connect(url + a["token"]) as wa, \
         client.websocket_connect(url + b["token"]) as wb:
        recv_type(wa, "init")
        recv_type(wb, "init")
        wa.send_json({"type": "point", "id": "s1", "p": {"x": 5, "y": 6}})
        m = recv_type(wb, "point")
        assert m["id"] == "s1"
        assert m["p"] == {"x": 5, "y": 6}
def test_new_connection_receives_existing_drawing(client, new_user):
    a = new_user()
    board = make_board(client, a)
    url = f"/ws/boards/{board['id']}?token={a['token']}"
    with client.websocket_connect(url) as w1, client.websocket_connect(url) as w2:
        recv_type(w1, "init")
        recv_type(w2, "init")
        w1.send_json({"type": "point", "id": "s1", "p": {"x": 1, "y": 2}})
        recv_type(w2, "point")                       # server ne point process kar liya
        w1.send_json({"type": "end"})
        w1.send_json({"type": "cursor", "x": 0, "y": 0})
        recv_type(w2, "cursor")                      # 'end' (save) isse pehle poora ho chuka
        with client.websocket_connect(url) as w3:
            init = recv_type(w3, "init")
            assert "s1" in init["strokes"]
def test_presence_lists_online_users(client, new_user):
    a, b = new_user(), new_user()
    board = make_board(client, a)
    client.post("/boards/join", json={"code": board["join_code"]}, headers=b["headers"])
    url = f"/ws/boards/{board['id']}?token="
    with client.websocket_connect(url + a["token"]) as wa, \
         client.websocket_connect(url + b["token"]) as wb:
        recv_type(wa, "init")
        recv_type(wb, "init")
        recv_presence(wb, [a["email"], b["email"]])