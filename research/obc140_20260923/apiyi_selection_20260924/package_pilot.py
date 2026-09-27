"""Create a portable reading bundle from an explicit allowlist; no inference."""
import hashlib
import json
import re
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

HERE = Path(__file__).resolve().parent
MODELS = ("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.4-mini")
FILES = ["SELECTION_REPORT_20260924.html", "SELECTION_REPORT_20260924.md",
         "SEMANTIC_REVIEW.md", "cost_summary.json", "COST_METHOD.md", "PRICE_SOURCES.md",
         "provider_rates.json", "CACHE_BILLING_NOTE.md", "PACKAGE_READ_ME.md",
         "PLAN.md", "MANIFEST.md", "REPRO_COMMANDS.md", "PREDEPLOY_REVIEW.md",
         "tests_pipeline.xml", "tests_usage.xml", "browser_qa/browser_check.json"]
FILES += ["views/" + model + suffix for model in MODELS for suffix in (".html", ".json")]


def main():
    inventory = []
    for name in FILES:
        content = (HERE / name).read_bytes()
        if re.search(rb"\bsk-[A-Za-z0-9_-]{16,}", content):
            raise ValueError("Credential-like content in " + name)
        inventory.append({"path": name, "bytes": len(content),
                          "sha256": hashlib.sha256(content).hexdigest()})
    manifest = {"scope": "two_known_tasks_three_models_offline_reading_only",
                "full140_started": False, "original_request_logs_included": False,
                "credential_pattern_check": "PASS", "files": inventory}
    raw = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
    (HERE / "PACKAGE_INVENTORY.json").write_bytes(raw)
    archive = HERE / "APIYI_SMALL_SAMPLE_REVIEW.zip"
    with ZipFile(archive, "w", ZIP_DEFLATED) as package:
        for name in FILES:
            package.write(HERE / name, name)
        package.writestr("PACKAGE_INVENTORY.json", raw)
    with ZipFile(archive) as package:
        assert package.testzip() is None
        for entry in inventory:
            assert hashlib.sha256(package.read(entry["path"])).hexdigest() == entry["sha256"]
    print(json.dumps({"archive": str(archive), "files": len(FILES) + 1,
                      "bytes": archive.stat().st_size, "integrity": "PASS"}))


if __name__ == "__main__":
    main()
