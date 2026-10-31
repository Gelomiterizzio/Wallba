from pathlib import Path

from wallba.guard.classifier import classify
from wallba.guard.scanner import scan_tree


def test_env_is_critical_without_reading_it(tmp_path, monkeypatch):
    def fail_open(self, *args, **kwargs):
        raise AssertionError(f"no se debía abrir {self}")

    monkeypatch.setattr(Path, "open", fail_open)
    found = classify("config/.env", "file")
    assert found.risk == "CRITICAL"
    assert found.category == "credentials"
    assert any("No se leyó" in reason for reason in found.reasons)


def test_source_named_token_is_not_critical():
    found = classify("src/token_helper.py", "file")
    assert found.risk == "MEDIUM"


def test_scan_keeps_normal_files_low(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.py").write_text("print(1)\n", encoding="utf-8")
    (root / "README.md").write_text("nota\n", encoding="utf-8")
    monkeypatch.setattr(Path, "open", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("abierto")))
    scanned = scan_tree(root)
    by_path = {item.relative_path: item.classification.risk for item in scanned.entries}
    assert by_path["src/app.py"] == "LOW"
    assert by_path["README.md"] == "LOW"
