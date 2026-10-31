from wallba.guard.store import GuardStore


def test_rules_survive_reopen(tmp_path):
    path = tmp_path / "state" / "guard.sqlite"
    store = GuardStore(path)
    project_id = store.save_project(
        project_id="11111111-1111-4111-8111-111111111111",
        root=str(tmp_path / "proj"),
        name="proj",
        opened_at="2026-10-31T20:00:00+00:00",
        files=1,
        directories=0,
        truncated=False,
    )
    store.upsert_rule(project_id, "config/.env", "file", False, "alert")
    reopened = GuardStore(path)
    rules = reopened.rules(project_id)
    assert rules[0]["posture"] == "alert"
    assert rules[0]["relative_path"] == "config/.env"
