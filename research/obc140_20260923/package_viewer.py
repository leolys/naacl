"""Package only the shareable offline view and human documentation, never keys/gold."""
import hashlib
import json
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parent
NAMES = ("OBC140_REVIEW.html", "PACKAGE_READ_ME.md", "STATUS_20260923.md", "STATUS_20260923.html")


def main():
    archive = ROOT / "OBC140_VIEWER.zip"
    # An existing delivered bundle is never overwritten.
    inventory = []
    for name in NAMES:
        content = (ROOT / name).read_bytes()
        inventory.append({"file": name, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()})
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        for name in NAMES:
            bundle.write(ROOT / name, name)
        bundle.writestr("FILES.json", json.dumps(inventory, ensure_ascii=False, indent=2))
    with zipfile.ZipFile(archive) as bundle:
        bad = bundle.testzip()
        if bad:
            raise ValueError("Archive failed integrity: " + bad)
    record = {"archive": str(archive), "bytes": archive.stat().st_size,
              "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(), "files": inventory,
              "integrity": "PASS", "contains_api_credential": False,
              "contains_raw_gateway_errors": False, "contains_offline_gold": False}
    (ROOT / "PACKAGE_INVENTORY.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in record.items() if k != "files"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
