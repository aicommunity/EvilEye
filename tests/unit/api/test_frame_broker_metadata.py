from evileye.api.core.frame_broker import FrameBroker


def test_latest_metadata_and_subscribe():
    broker = FrameBroker()
    broker.publish_jpeg("1:0", b"jpeg", metadata={"source_id": 0, "objects": [{"track_id": 1}]})
    meta = broker.latest_metadata("1:0")
    assert meta is not None
    assert meta["source_id"] == 0
    assert meta["objects"][0]["track_id"] == 1

    q = broker.subscribe("1:0")
    broker.publish_jpeg("1:0", b"jpeg2", metadata={"source_id": 0, "objects": []})
    assert q.get(timeout=1)["source_id"] == 0
    broker.unsubscribe("1:0", q)
