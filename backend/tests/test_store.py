from app.store import PayloadStore, _atomic_write_text


def test_atomic_write_replaces_content_without_residue(tmp_path):
    target = tmp_path / "x.json"
    _atomic_write_text(target, "one")
    _atomic_write_text(target, "two")
    assert target.read_text(encoding="utf-8") == "two"
    assert list(tmp_path.glob("*.tmp")) == []


def test_events_skip_malformed_lines(tmp_path):
    store = PayloadStore(tmp_path)
    store.ensure()
    store.event("a", "first")
    with store.events_path.open("a", encoding="utf-8") as handle:
        handle.write("{ broken json line\n")
        handle.write("[1, 2, 3]\n")
        handle.write("\n")
    store.event("b", "second")
    messages = [row["message"] for row in store.events()]
    assert messages == ["first", "second"]
