"""Fase C · C7 / Fase E5 — event bus peer request/response + priority."""
from harness.event_bus import EventBus, PEER_REQUEST, PEER_RESPONSE


def test_basic_delivery():
    bus = EventBus()
    seen = []
    bus.subscribe("WebAgent", lambda m: seen.append(m) or None)
    bus.publish("SearchAgent", "WebAgent", "NOTE", {"x": 1})
    assert bus.pump() == 1
    assert seen[0].payload == {"x": 1}


def test_peer_request_gets_correlated_response():
    bus = EventBus()
    # WebAgent answers any PEER_REQUEST by returning a result dict.
    bus.subscribe("WebAgent", lambda m: {"status": "ok", "result": "sig()"})
    seen = []
    bus.subscribe("SearchAgent", lambda m: seen.append(m) or None)

    cid = bus.publish("SearchAgent", "WebAgent", PEER_REQUEST,
                      {"url": "docs"}, priority="normal")
    bus.pump()   # delivers request -> auto-publishes response -> delivers response

    responses = bus.responses_for(cid)
    assert len(responses) == 1
    assert responses[0].msg_type == PEER_RESPONSE
    assert responses[0].payload["result"] == "sig()"
    assert seen and seen[0].correlation_id == cid   # SearchAgent received it


def test_priority_ordering():
    bus = EventBus()
    order = []
    bus.subscribe("A", lambda m: order.append(m.payload["tag"]) or None)
    bus.publish("X", "A", "N", {"tag": "bg"}, priority="background")
    bus.publish("X", "A", "N", {"tag": "crit"}, priority="critical")
    bus.publish("X", "A", "N", {"tag": "norm"}, priority="normal")
    bus.pump()
    assert order == ["crit", "norm", "bg"]


def test_full_history_recorded():
    bus = EventBus()
    bus.subscribe("A", lambda m: None)
    bus.publish("X", "A", "N", {})
    bus.pump()
    assert len(bus.history) == 1
