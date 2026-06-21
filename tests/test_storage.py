from postcodejager.storage import Store


def test_token_roundtrip(tmp_path):
    s = Store(str(tmp_path / "db.sqlite"))
    assert s.load_token() is None
    s.save_token({"access_token": "x", "refresh_token": "y", "expires_at": 123})
    assert s.load_token()["access_token"] == "x"


def test_collected_roundtrip_unions(tmp_path):
    s = Store(str(tmp_path / "db.sqlite"))
    assert s.get_collected() == set()
    s.set_collected({"1011", "1012"})
    s.set_collected({"1012", "1013"})  # union, never shrink
    assert s.get_collected() == {"1011", "1012", "1013"}


def test_last_sync(tmp_path):
    s = Store(str(tmp_path / "db.sqlite"))
    assert s.get_last_sync() is None
    s.set_last_sync(1700)
    assert s.get_last_sync() == 1700


def test_planned_toggle_and_clear(tmp_path):
    s = Store(str(tmp_path / "db.sqlite"))
    assert s.get_planned() == set()
    s.toggle_planned("1011")
    s.toggle_planned("1012")
    assert s.get_planned() == {"1011", "1012"}
    s.toggle_planned("1011")  # toggle off
    assert s.get_planned() == {"1012"}
    s.clear_planned()
    assert s.get_planned() == set()


def test_activity_ids(tmp_path):
    s = Store(str(tmp_path / "db.sqlite"))
    s.mark_activity(1)
    s.mark_activity(2)
    assert s.seen_activity_ids() == {1, 2}
