from wallba.guard.runtime import GuardRuntime


def test_external_modification_is_detected_and_not_restored(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    target = root / "notes.txt"
    target.write_text("original", encoding="utf-8")
    state = tmp_path / "state"
    runtime = GuardRuntime(state / "guard.sqlite", state)
    opened = runtime.open_project(str(root))
    project_id = opened["project"]["id"]
    runtime.protect(project_id, "notes.txt", "file", "block_write")
    target.write_text("cambiado-fuera", encoding="utf-8")
    found = runtime.watch_once(project_id)
    assert found[0]["outcome"] == "detected"
    assert found[0]["origin_detail"] == "ORIGEN NO DETERMINADO"
    assert found[0]["preventive"] is False
    assert target.read_text(encoding="utf-8") == "cambiado-fuera"
    again = runtime.watch_once(project_id)
    assert again == []


def test_new_critical_file_is_reported_without_reading_it(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "readme.txt").write_text("hola", encoding="utf-8")
    state = tmp_path / "state"
    runtime = GuardRuntime(state / "guard.sqlite", state)
    project_id = runtime.open_project(str(root))["project"]["id"]
    (root / ".env").write_text("TOKEN=falso\n", encoding="utf-8")
    found = runtime.watch_once(project_id)
    created = [item for item in found if item["operation"] == "create"]
    assert created[0]["relative_path"] == ".env"
    assert "TOKEN" not in created[0]["explanation"]
    assert created[0]["origin_detail"] == "ORIGEN NO DETERMINADO"
