"""Build a portable archive of this experiment only, excluding envs/caches/secrets."""
import argparse
import json
import re
from pathlib import Path
import zipfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    target = Path(args.output).resolve()
    if target.exists():
        raise FileExistsError("archive already exists; choose a new name")
    files = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(p in {".venv", "__pycache__", ".pytest_cache", "pytest_saved", "pytest_final"} for p in relative.parts):
            continue
        if path.suffix.lower() in {".zip", ".pyc"} or path.name in {".env", "MANIFEST.md"}:
            continue
        # Authentication is environment-only. Refuse to package accidental header/key dumps.
        if path.suffix.lower() in {".json", ".jsonl", ".md", ".py", ".txt", ".ps1"}:
            content = path.read_text(encoding="utf-8", errors="replace")
            if re.search(r'Bearer\s+sk-[A-Za-z0-9_-]{12,}|"api_key"\s*:\s*"sk-[A-Za-z0-9_-]{12,}', content):
                raise ValueError("possible credential in " + str(relative))
        files.append(path)
    manifest = root / "MANIFEST.md"
    manifest.write_text("# 本轮交付文件清单\n\n不含凭据、Python环境或缓存。完整运行请求中的图片base64已保留。\n\n" +
                        "\n".join("- `" + p.relative_to(root).as_posix() + "`" for p in files) + "\n", encoding="utf-8")
    files.append(manifest)
    with zipfile.ZipFile(target, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in files:
            archive.write(path, arcname="competing_rules_demo/" + path.relative_to(root).as_posix())
    print(json.dumps({"archive": str(target), "files": len(files), "bytes": target.stat().st_size}))


if __name__ == "__main__":
    main()
