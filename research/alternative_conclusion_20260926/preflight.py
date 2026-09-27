"""No-inference service and browser reconstruction check using archived actions."""
import argparse
import json
from pathlib import Path
import platform
import subprocess
import sys
import threading

import requests

from runner import BrowserSession, Ledger, clean_action, digest, dump, is_submit


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--historical", type=Path, required=True)
    args = parser.parse_args()
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(args.project))
    from web_agent_benchmark.evaluation import run_public39 as original
    from playwright.sync_api import sync_playwright
    from werkzeug.serving import make_server
    args.output.mkdir(parents=True, exist_ok=False)
    config = json.loads((Path(__file__).parent / "config.json").read_text(encoding="utf-8"))
    ledger = Ledger(args.output, config)
    session = requests.Session()
    session.trust_env = False
    health = session.get("http://127.0.0.1:8058/health", timeout=10)
    models = session.get("http://127.0.0.1:8058/v1/models", timeout=10).json()
    assert health.status_code == 200
    assert config["model"] in [m["id"] for m in models["data"]]
    receipt = {"model_inference_calls": 0, "health_http": health.status_code, "models": models,
               "python": sys.version, "platform": platform.platform(), "browser_pairs": []}
    for command, name in [(["nvidia-smi", "--query-gpu=index,uuid,memory.used,utilization.gpu", "--format=csv,noheader"], "gpu"),
                          (["ps", "-p", "316818,319282,282313", "-o", "pid,lstart,args"], "process_identity")]:
        receipt[name] = subprocess.run(command, capture_output=True, text=True, check=False).stdout
    with sync_playwright() as pw:
        for arm in config["arms"]:
            out = args.output / arm
            out.mkdir()
            private = out / "private"
            private.mkdir()
            tasks = args.project / "web_agent_benchmark/benchmark_v2_open/splits" / arm / "public39_tasks.jsonl"
            app = original.shell.make_app(private / "submissions.jsonl", tasks, private / "shell_summary.md", False)
            server = make_server("127.0.0.1", 0, app)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = "http://127.0.0.1:%d" % server.server_port
            row = json.loads((args.historical / arm / "runs.jsonl").read_text(encoding="utf-8").splitlines()[0])
            historical_actions = []
            for item in row["trace"]:
                action = clean_action(item["action"])
                if is_submit(action):
                    break
                historical_actions.append(action)
            states, hashes, histories = [], [], []
            try:
                for name in ("first", "replay"):
                    env = BrowserSession(pw, base, out / name, ledger, original, config)
                    try:
                        for action in historical_actions:
                            assert env.execute(action, "offline_historical_replay")["executed"]
                        state, image = env.snapshot()
                        states.append(state)
                        hashes.append(digest(image))
                        histories.append(env.history)
                        if name == "first":
                            old_image = args.historical / arm / "screenshots/pub001/step_03.png"
                            old_hash = digest(old_image)
                    finally:
                        env.close()
                item = {"arm": arm, "state_equal": states[0] == states[1], "image_equal": hashes[0] == hashes[1],
                        "history_equal": histories[0] == histories[1], "image_hashes": hashes,
                        "historical_checkpoint_image_equal": hashes[0] == old_hash,
                        "historical_image_sha256": old_hash, "model_result": "not_run_offline_replay_only"}
                assert item["state_equal"] and item["image_equal"] and item["history_equal"]
                receipt["browser_pairs"].append(item)
            finally:
                server.shutdown()
                server.server_close()
    receipt["passed"] = True
    receipt["browser_operations"] = ledger.data["browser_operations"]
    dump(args.output / "receipt.json", receipt)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
