"""The relays, through TestClient's WebSocket client: init first with every field, values and records reach the
others, complete saves once for everyone, presence-sync, and the connections each relay refuses."""

import json
from pathlib import Path

import pytest
from starlette.websockets import WebSocketDisconnect

from app.relay.room_key import room_key, snapshot_path
from tests.conftest import Api, start_app


def next_of(ws: object, kind: str) -> dict:
    """The next message of a type, skipping the others (a peer's presence, say)."""
    for _ in range(20):
        message = ws.receive_json()
        if message["type"] == kind:
            return message
    raise AssertionError(f"no {kind} message")


def test_fill_init_has_every_field_and_values_reach_the_others(api: Api) -> None:
    with api.websocket("/ws/rooms/relay-a?name=Ann") as ann:
        init = ann.receive_json()
        assert init["type"] == "init"
        assert set(init) == {"type", "clientId", "name", "colorIndex", "seed", "values", "peers", "sessionId", "responseId"}
        assert init["name"] == "Ann" and init["colorIndex"] == 1 and init["responseId"] is None
        assert len(init["sessionId"]) == 32 and init["seed"]["title"]
        with api.websocket("/ws/rooms/relay-a?name=Ben") as ben:
            assert ben.receive_json()["sessionId"] == init["sessionId"]
            ann.send_json({"type": "value", "key": "q1", "value": {"d": {}, "g": 1.0}})
            assert next_of(ben, "value") == {"type": "value", "from": init["clientId"], "key": "q1", "value": {"d": {}, "g": 1.0}}
            ann.send_json({"type": "presence", "state": {"focus": "q1"}, "retain": True})
            peer = next_of(ben, "peer")
            assert peer["retain"] is True and peer["peer"]["clientId"] == init["clientId"]
            ann.send_text("not json")
            ann.send_json({"type": "nonsense"})
            with api.websocket("/ws/rooms/relay-a?name=Cat") as cat:
                late = cat.receive_json()
                assert late["values"]["q1"] == {"d": {}, "g": 1.0}
                assert [p["clientId"] for p in late["peers"]] == [init["clientId"]]
        assert next_of(ann, "peer-left")["clientId"]


def test_fill_two_completes_save_one_row_for_everyone(api: Api) -> None:
    before = api.count("responses", "form_id = 'job-sheet'")
    with api.websocket("/ws/rooms/relay-b?name=Ann") as ann, api.websocket("/ws/rooms/relay-b?name=Ben") as ben:
        ann.receive_json()
        ben.receive_json()
        data = {"q1": "done", "d": {}, "g": 1.5}
        ann.send_json({"type": "complete", "data": data})
        ben.send_json({"type": "complete", "data": data})
        first, second = next_of(ann, "completed"), next_of(ann, "completed")
        assert first["id"] == second["id"] and first["data"] == data
        assert next_of(ben, "completed")["id"] == first["id"]
        ann.send_json({"type": "value", "key": "q1", "value": "changed after completing"})
        with api.websocket("/ws/rooms/relay-b?name=Cat") as cat:
            late = cat.receive_json()
            assert (late["responseId"], late["values"]["q1"]) == (first["id"], "done")
    assert api.count("responses", "form_id = 'job-sheet'") == before + 1


def test_fill_seeds_a_room_from_the_saved_record(api: Api) -> None:
    with api.db() as conn:
        id, data = conn.execute("SELECT id, data FROM responses WHERE form_id = 'job-sheet' ORDER BY id LIMIT 1").fetchone()
    with api.websocket(f"/ws/rooms/{id}") as ws:
        init = ws.receive_json()
    assert init["values"] == json.loads(data) and init["name"] == "Alice Martin"


def test_edit_records_reach_late_joiners_in_order_and_presence_sync_follows_init(api: Api) -> None:
    records = [{"seq": 1, "op": 0, "payload": {"name": "title", "value": "One"}}, {"seq": 1, "op": 0, "payload": {}}]
    with api.websocket("/ws/forms/relay-c?name=Ann") as ann:
        init = ann.receive_json()
        assert set(init) == {"type", "clientId", "colorIndex", "color", "seed", "log"} and init["log"] == []
        ann.send_json({"type": "presence", "state": {"tab": "designer"}})
        with api.websocket("/ws/forms/relay-c?name=Ben") as ben:
            assert ben.receive_json()["type"] == "init"
            sync = ben.receive_json()
            assert sync["type"] == "presence-sync" and sync["peers"][0]["clientId"] == init["clientId"]
            for record in records:
                ann.send_json({"type": "append", "payload": record})
            assert [next_of(ben, "record")["payload"] for _ in records] == records
            with api.websocket("/ws/forms/relay-c?name=Cat") as cat:
                assert cat.receive_json()["log"] == records
        assert next_of(ann, "presence-leave")["clientId"]


@pytest.mark.parametrize(("path", "user"), [("/ws/rooms/x", None), ("/ws/rooms/x", "mallory"), ("/ws/forms/x", None),
                                            ("/ws/forms/x", "bob"), ("/ws/rooms/bad%20id", "alice"), ("/ws/forms/" + "x" * 65, "alice")])
def test_refused_connections_close_before_accept(api: Api, path: str, user: str | None) -> None:
    with pytest.raises(WebSocketDisconnect) as refused:
        with api.websocket(path, user=user) as ws:
            ws.receive_json()
    assert refused.value.code == 1008


def test_sandboxes_get_their_own_rooms_and_snapshots(tmp_path: Path) -> None:
    with start_app(tmp_path, demo_mode=True) as api:
        api.get("/demo/stored/fill-together")
        with pytest.raises(WebSocketDisconnect):   # no demo_sid, no sandbox: refused
            with Api(api.client, api.settings).websocket("/ws/rooms/shared") as ws:
                ws.receive_json()
        other = Api(api.client, api.settings)
        other.get("/demo/stored/fill-together")
        assert api.sid and other.sid and api.sid != other.sid
        with api.websocket("/ws/rooms/shared") as mine:
            mine.receive_json()
            mine.send_json({"type": "value", "key": "q1", "value": "mine"})
            with api.websocket("/ws/rooms/shared") as same:
                assert same.receive_json()["values"].get("q1") == "mine"
            with other.websocket("/ws/rooms/shared") as theirs:
                assert "q1" not in theirs.receive_json()["values"]
        snapshot = snapshot_path(api.settings.relay_dir, room_key(api.sid, "shared"))
        assert snapshot.name == f"{snapshot.stem}.json" and ":" not in snapshot.name and snapshot.is_file()
        room = api.get("/demo/stored/fill-together?room=shared").json()["relay room"]
        assert room["values"] == {"q1": "mine"}
