from wallba.guard.scanner import scan_tree


def test_scanner_does_not_descend_into_symlinks_or_skipped_dirs(tmp_path):
    root = tmp_path / "proj"
    (root / "node_modules").mkdir(parents=True)
    (root / "node_modules" / "left.txt").write_text("x", encoding="utf-8")
    (root / "keep.txt").write_text("y", encoding="utf-8")
    scanned = scan_tree(root)
    paths = {item.relative_path for item in scanned.entries}
    assert "keep.txt" in paths
    assert "node_modules/left.txt" not in paths
    assert scanned.files == 1
