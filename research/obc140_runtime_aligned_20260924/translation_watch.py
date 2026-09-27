"""Prepare native-translation inboxes while the one authorized API batch runs."""
import time
from pathlib import Path
import json

import native_zh

HERE = Path(__file__).resolve().parent


def main():
    while True:
        result = native_zh.prepare()
        if result["new_strings"]:
            print(json.dumps(result, ensure_ascii=False), flush=True)
        state = native_zh.core.read(HERE / "run/run_state.json", {})
        if state.get("status") in {"completed_with_terminal_records", "blocked"}:
            (HERE / "translations/ALL_INPUTS_PREPARED").write_text(
                json.dumps({"run_status": state["status"], "scope": "all currently available actual responses"}),
                encoding="utf-8")
            print("ALL_INPUTS_PREPARED", flush=True)
            return
        time.sleep(20)


if __name__ == "__main__":
    main()
