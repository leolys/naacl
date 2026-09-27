# -*- coding: utf-8 -*-
"""Create a portable offline review archive; never include credentials or old runs."""
from pathlib import Path
import hashlib
import json
import re
import zipfile

HERE = Path(__file__).resolve().parent
DEST = HERE.parent / "OBC140_RUNTIME_ALIGNED_ZH_20260924.zip"
EXCLUDED_DIRS = {"__pycache__", ".pytest_cache", "request_previews", "mock_run", "mock_post_review"}
EXCLUDED_NAMES = {"PACKAGE_INDEX.json", "PACKAGE_CHECK.json"}
SUFFIXES = {".json", ".jsonl", ".md", ".py", ".html", ".xml", ".txt", ".yaml", ".yml", ".toml", ".cfg"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def has_credential_pattern(content):
    # A key prefix starts a token. Do not match the suffix of ordinary
    # model prose such as "task-to-action-relation" as if it were a key.
    return bool(re.search(rb"(?<![A-Za-z0-9_])sk-[A-Za-z0-9_-]{16,}", content)
                or re.search(rb"Bearer\s+[A-Za-z0-9_-]{16,}", content, re.IGNORECASE))


def main():
    required = ("OBC140_TERRA_ZH_REVIEW.html", "REPORT.md", "RESULTS.json", "all_request_checks.json")
    for name in required:
        if not (HERE / name).is_file():
            raise RuntimeError("Missing final artifact: " + name)
    if DEST.exists():
        raise FileExistsError("Preserve existing archive; choose an explicitly new version")
    sources = []
    for path in sorted(HERE.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(HERE)
        if any(part in EXCLUDED_DIRS for part in rel.parts) or path.name in EXCLUDED_NAMES or path.suffix == ".zip":
            continue
        if path.suffix.lower() in SUFFIXES:
            content = path.read_bytes()
            if has_credential_pattern(content):
                raise RuntimeError("Possible credential in artifact; archive not created: " + str(rel))
        sources.append(path)
    index = [{"path": str(path.relative_to(HERE)).replace("\\", "/"), "bytes": path.stat().st_size,
              "sha256": digest(path.read_bytes())} for path in sources]
    manifest = {"scope": "new fixed140 runtime-aligned results, source evidence and single-file offline views",
                "credential_scan": "no token-start sk- or long Bearer pattern found in included text artifacts; not an exhaustive secret proof",
                "excluded": sorted(EXCLUDED_DIRS | EXCLUDED_NAMES), "files": index}
    index_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    (HERE / "PACKAGE_INDEX.json").write_bytes(index_bytes)
    with zipfile.ZipFile(DEST, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path, row in zip(sources, index):
            archive.write(path, HERE.name + "/" + row["path"])
        archive.writestr(HERE.name + "/PACKAGE_INDEX.json", index_bytes)
    with zipfile.ZipFile(DEST) as archive:
        bad_file = archive.testzip()
        if bad_file:
            raise RuntimeError("Archive integrity failure: " + bad_file)
        for name in ("OBC140_TERRA_ZH_REVIEW.html", "RUNTIME_INPUTS_140_ZH.html"):
            if archive.read(HERE.name + "/" + name) != (HERE / name).read_bytes():
                raise RuntimeError("Viewer bytes changed in archive")
    result = {"archive": str(DEST), "files": len(index) + 1, "bytes": DEST.stat().st_size,
              "sha256": digest(DEST.read_bytes()), "zip_integrity": "PASS", "viewer_byte_identity": "PASS"}
    (HERE / "PACKAGE_CHECK.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
