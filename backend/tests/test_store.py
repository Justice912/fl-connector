import threading

from app.store import PayloadStore, _atomic_write_text


def test_atomic_write_replaces_content_without_residue(tmp_path):
    target = tmp_path / "x.json"
    _atomic_write_text(target, "one")
    _atomic_write_text(target, "two")
    assert target.read_text(encoding="utf-8") == "two"
    assert list(tmp_path.glob("*.tmp")) == []


def test_atomic_write_is_thread_safe_on_same_target(tmp_path):
    target = tmp_path / "current.json"
    errors: list[Exception] = []

    def writer(value: str) -> None:
        try:
            for _ in range(20):
                _atomic_write_text(target, value)
        except Exception as exc:  # noqa: BLE001 - surfaced to the assertion below
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(f"value-{index}",)) for index in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert target.exists()
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
