"""Read-only audit of completed wire artifacts; no API/browser/model imports.

Writes only the two explicitly requested audit artifacts, never source runs.
Wire/state equality is an engineering property, not a semantic-evidence PASS.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path

from PIL import Image


HERE = Path(__file__).resolve().parent


def read(path, default=None):
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def relative(path, root):
    return os.path.relpath(Path(path).resolve(), Path(root).resolve()).replace("\\", "/")


def archived_image_file(value, run):
    """API archives may use paths relative to the original project cwd."""
    supplied = Path(value)
    candidates = [supplied, HERE.parent / supplied]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError("Recorded image file unavailable: " + str(value))


def wire_parts(payload):
    user = payload["messages"][1]["content"]
    context = json.loads(user[0]["text"])
    images = []
    if (len(user) - 1) % 2:
        raise ValueError("Unrecognized observed-image layout")
    for offset in range(1, len(user), 2):
        label, image = user[offset:offset + 2]
        if not label["text"].startswith("Observation "):
            raise ValueError("Image observation label is missing")
        binary = base64.b64decode(image["image_url"]["url"].split(";base64,", 1)[1], validate=True)
        with Image.open(io.BytesIO(binary)) as decoded:
            dimensions, image_format = list(decoded.size), decoded.format
        images.append({"ref": label["text"][len("Observation "):], "sha256": digest(binary),
                       "bytes": len(binary), "dimensions": dimensions, "format": image_format})
    return context, images


def audit(run, output_prefix):
    run, output_prefix = Path(run).resolve(), Path(output_prefix).resolve()
    if not (run / "completion.json").is_file() or not (run / "offline_results.json").is_file():
        raise RuntimeError("Audit waits for immutable completion artifacts; run is not complete")
    json_path, md_path = output_prefix.with_suffix(".json"), output_prefix.with_suffix(".md")
    if json_path.exists() or md_path.exists():
        raise FileExistsError("Prior audit preserved; choose a new output prefix")
    budget, config = read(run / "budget.json"), read(run / "config_snapshot.json")
    completion, protocol, runtime = read(run / "completion.json"), read(run / "frozen_protocol.json"), read(run / "runtime.json")
    requests = []
    attempts = []
    requested_models, response_models, usage_models, http_statuses = Counter(), Counter(), Counter(), Counter()
    finishes, tokens, missing_tokens, prompt_hashes = Counter(), Counter(), Counter(), defaultdict(set)
    parameters = Counter()
    response_count = failed_attempts = extra_retry_attempts = 0
    service_error_classes = Counter()
    parsed_missing = response_missing = usage_missing = 0
    wire_cache = {}
    for request_path in sorted(run.glob("**/request.json")):
        folder = request_path.parent
        payload, archived = read(request_path), read(folder / "context.json", {})
        context, images = wire_parts(payload)
        rel = relative(folder, run)
        phase = archived.get("phase", "unknown")
        profile = "ordinary_actor" if "ordinary_proposal" in rel else folder.parent.name
        wire_cache[rel] = {"context": context, "images": images, "payload": payload}
        actual_system = payload["messages"][0]["content"]
        prompt_hashes[profile + "/" + phase].add(digest(actual_system.encode("utf-8")))
        settings = {key: payload.get(key) for key in ("model", "temperature", "max_tokens")}
        parameters[canonical(settings)] += 1
        archived_refs = [entry["ref"] for entry in archived.get("images", [])]
        archive_hashes = [digest(archived_image_file(entry["file"], run).read_bytes()) for entry in archived.get("images", [])]
        row = {"folder": rel, "phase": phase, "profile": profile, "request_sha256": digest(request_path.read_bytes()),
               "requested_model": payload.get("model"), "request_parameters": settings,
               "system_prompt_sha256": digest(actual_system.encode("utf-8")), "actual_images": images,
               "readable_context_matches_wire": context == archived.get("context"),
               "readable_image_refs_match_wire": archived_refs == [image["ref"] for image in images],
               "readable_image_file_bytes_match_wire": archive_hashes == [image["sha256"] for image in images],
               "authorization_header_archived_in_payload": any(key.lower() == "authorization" for key in payload),
               "attempt_files": [], "response_files": [], "parsed_result_exists": (folder / "parsed.json").exists()}
        parsed_missing += not row["parsed_result_exists"]
        for attempt_file in sorted(folder.glob("attempt_*.json")):
            meta = read(attempt_file)
            number = meta.get("attempt")
            response_file = folder / ("response_%02d.json" % number)
            body = read(response_file)
            usage = meta.get("usage")
            safe_usage = {key: usage[key] for key in ("prompt_tokens", "completion_tokens", "total_tokens", "model_name")
                          if key in usage} if isinstance(usage, dict) else None
            error_class = "budget_exceeded" if body is not None and (
                "budget_exceeded" in canonical(body).lower() or "budget has been exceeded" in canonical(body).lower()) else None
            if error_class:
                service_error_classes[error_class] += 1
            record = {"folder": rel, "phase": phase, "attempt": number,
                      "http_status": meta.get("http_status"), "requested_model": meta.get("requested_model"),
                      "response_model": meta.get("response_model"),
                      "error_type": str(meta["error"]).split(":", 1)[0] if meta.get("error") else None,
                      "service_error_class": error_class,
                      "retryable": meta.get("retryable"), "elapsed_seconds": meta.get("elapsed_seconds"),
                      "response_exists": body is not None, "usage": safe_usage}
            response_missing += body is None
            requested_models[str(meta.get("requested_model") or "not_reported")] += 1
            response_models[str(meta.get("response_model") or "not_reported")] += 1
            http_statuses[str(meta.get("http_status") or "not_reported")] += 1
            usage_missing += not isinstance(usage, dict)
            usage_models[str(usage.get("model_name") or "not_reported") if isinstance(usage, dict) else "not_reported"] += 1
            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                value = usage.get(key) if isinstance(usage, dict) else None
                if isinstance(value, (int, float)):
                    tokens[key] += value
                else:
                    missing_tokens[key] += 1
            failed = bool(meta.get("error")) or meta.get("http_status") != 200
            failed_attempts += failed
            extra_retry_attempts += isinstance(number, int) and number > 1
            choices = body.get("choices", []) if isinstance(body, dict) else []
            finish_values = [choice.get("finish_reason") for choice in choices]
            for value in finish_values:
                finishes[str(value or "not_reported")] += 1
            record["finish_reasons"] = finish_values
            record["failed_attempt"] = failed
            record["response_identity_and_usage_match_metadata"] = body is None or (
                body.get("model") == meta.get("response_model") and body.get("usage") == meta.get("usage"))
            attempts.append(record)
            row["attempt_files"].append(relative(attempt_file, run))
        row["response_files"] = [relative(path, run) for path in sorted(folder.glob("response_*.json"))]
        response_count += len(row["response_files"])
        requests.append(row)
    pairs = []
    for case in protocol["cases"]:
        task = case["task_slug"]
        legacy = wire_cache.get(task + "/legacy/generate")
        revised = wire_cache.get(task + "/observation_boundary_v4/generate")
        old_check = wire_cache.get(task + "/legacy/verify")
        new_check = wire_cache.get(task + "/observation_boundary_v4/verify")
        recorded = read(run / task / "paired_input_proof.json")
        pair = {"task_slug": task, "recorded_proof": recorded, "both_generator_requests_present": bool(legacy and revised)}
        if legacy and revised:
            pair.update(generator_contexts_equal=legacy["context"] == revised["context"],
                        generator_image_bytes_and_refs_equal=legacy["images"] == revised["images"],
                        complete_user_payload_equal=legacy["payload"]["messages"][1] == revised["payload"]["messages"][1],
                        system_prompts_differ=legacy["payload"]["messages"][0] != revised["payload"]["messages"][0])
            pair["recorded_proof_matches_independent_check"] = recorded is not None and (
                recorded.get("generator_contexts_equal") == pair["generator_contexts_equal"] and
                recorded.get("same_image_refs_and_hashes") == pair["generator_image_bytes_and_refs_equal"])
        if old_check and new_check:
            fields = ("task", "state", "history", "interpretation_rules")
            pair["verifier_shared_public_context_equal"] = all(old_check["context"].get(key) == new_check["context"].get(key) for key in fields)
            pair["verifier_argument_sets_equal"] = old_check["context"].get("arguments") == new_check["context"].get("arguments")
            pair["verifier_images_equal"] = old_check["images"] == new_check["images"]
        pairs.append(pair)
    caps = [{"file": relative(path, run), "audit": read(path)} for path in sorted(run.glob("**/candidate_bound_audit.json"))]
    json_repairs = [{"file": relative(path, run), "repair": read(path)} for path in sorted(run.glob("**/json_representation_normalization.json"))]
    action_adaptations = []
    for path in sorted(run.glob("*/ordinary_proposal/normalized_proposal.json")):
        original = read(path.parent / "actor" / "parsed.json")
        action_adaptations.append({"file": relative(path, run), "representation_changed": original != read(path)})
    modules = [{"file": relative(path, run), "result": read(path)} for path in sorted(run.glob("**/module_result.json"))]
    all_slots = read(run / "module_results_unscored.json", [])
    browser_events = [event for event in budget["events"] if event["kind"] == "browser"]
    request_events = [event for event in budget["events"] if event["kind"] == "request"]
    source_hash_checks = {name: digest((run / "runtime_source" / name).read_bytes()) == expected
                          for name, expected in runtime["source_sha256"].items()}
    summary = {
        "source_run": str(run), "created_at": datetime.now(timezone.utc).isoformat(), "audit_api_calls": 0,
        "audit_browser_operations": 0, "scope": "engineering_cost_and_wire_only_not_semantic_validation",
        "planned_logical_calls": protocol["planned_module_calls"] + protocol["planned_new_ordinary_proposal_calls"],
        "request_payload_count": len(requests), "attempt_metadata_count": len(attempts),
        "response_file_count": response_count, "failed_attempts_including_parse_errors": failed_attempts,
        "extra_retry_attempts": extra_retry_attempts, "response_missing_attempts": response_missing,
        "logical_calls_without_parsed_result": parsed_missing,
        "budget_request_attempts": budget["attempts"], "budget_browser_operations": budget["browser_operations"],
        "ledger_counts_consistent": len(attempts) == len(request_events) == budget["attempts"] and len(browser_events) == budget["browser_operations"],
        "within_configured_caps": budget["attempts"] <= config["max_request_attempts"] and budget["browser_operations"] <= config["max_browser_operations"],
        "requested_models": dict(requested_models), "response_models": dict(response_models), "usage_model_names": dict(usage_models),
        "http_status_counts": dict(http_statuses), "finish_reason_counts": dict(finishes), "length_finish_count": finishes["length"],
        "service_error_classes": dict(service_error_classes),
        "service_error_detail_policy": "Only fixed error classes retained; original response message/email/team/account details are not copied into this audit.",
        "known_token_totals": dict(tokens), "attempts_without_usage": usage_missing,
        "attempts_missing_each_token_field": dict(missing_tokens),
        "request_parameters": [{"settings": json.loads(key), "logical_calls": count} for key, count in parameters.items()],
        "prompt_hashes_by_profile_phase": {key: sorted(value) for key, value in prompt_hashes.items()},
        "candidate_cap_trigger_count": sum(bool(item["audit"].get("omitted_raw_indices")) for item in caps),
        "candidate_cap_audits": caps, "json_representation_repair_count": len(json_repairs), "json_representation_repairs": json_repairs,
        "ordinary_action_container_adaptations": action_adaptations,
        "ordinary_action_container_changes": sum(item["representation_changed"] for item in action_adaptations),
        "actual_browser_action_kinds": dict(Counter(event["detail"].get("kind") for event in browser_events)),
        "business_submit_events": sum(event["detail"].get("kind") == "submit" for event in browser_events),
        "nonempty_submission_receipt_files": [relative(path, run) for path in run.glob("**/submission_receipts.jsonl") if path.stat().st_size],
        "runtime_snapshot_hash_checks": source_hash_checks, "paired_wire_checks": pairs,
        "module_slot_count": len(all_slots), "started_module_count": len(modules),
        "module_status_counts": dict(Counter(item["status"] for item in all_slots)),
        "modules_with_verifier_request_attempts": sum(item["result"].get("verifier_executed", False) for item in modules),
        "verifier_http200_response_count": sum(record["phase"] == "verify" and record["http_status"] == 200 for record in attempts),
        "verifier_parsed_result_count": sum(record["phase"] == "verify" and record["parsed_result_exists"] for record in requests),
        "fresh_ordinary_actor_successful_parsed_proposals": sum(record["phase"] == "ordinary_proposal" and record["parsed_result_exists"] for record in requests),
        "source_tasks_added_field_means_prepared_not_successfully_evaluated": True,
        "completion_record": completion, "requests": requests, "attempts": attempts,
    }
    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    fresh_rejections = sum(record["phase"] == "ordinary_proposal" and record["service_error_class"] == "budget_exceeded" for record in attempts)
    fresh_sentence = ("新两例各尝试获取一次普通 Actor 提案，但均被网关拒绝"
                      if fresh_rejections == 2 and summary["fresh_ordinary_actor_successful_parsed_proposals"] == 0 else
                      "新两例各只尝试一次普通 Actor 提案请求，是否实际取得提案见下项")
    lines = ["# 五任务旧／新观察边界提示：工程成本与实际请求审计", "",
             "本文件只读真实运行工件，不发起 API 请求、不启动浏览器、不修改旧结果。检查通过只能证明成本与输入工程关系，不能证明观察内容真实、规则合理或核验具有独立依据。", "",
             "## 实际调用与成本", "",
             "| 项目 | 实际记录 |", "|---|---:|",
             "| 计划逻辑调用 | %s |" % summary["planned_logical_calls"],
             "| 实际请求体数量 | %s |" % len(requests), "| 真实请求尝试 | %s |" % len(attempts),
             "| 失败尝试（含解析失败） | %s |" % failed_attempts, "| 额外重试尝试 | %s |" % extra_retry_attempts,
             "| 浏览器操作 | %s |" % budget["browser_operations"],
             "| 以 length 结束的响应 | %s |" % finishes["length"],
             "| 发生候选截断的生成 | %s |" % summary["candidate_cap_trigger_count"],
             "| 实际 JSON 表示修复 | %s |" % len(json_repairs),
             "| 新任务 Actor 动作容器实际变化 | %s |" % summary["ordinary_action_container_changes"], "",
             "总账／尝试文件计数一致：%s；未超过冻结上限：%s。" % (summary["ledger_counts_consistent"], summary["within_configured_caps"]), "",
             "已报告 token 合计：`%s`。缺少 usage 的尝试为 %s；各 token 字段缺失计数为 `%s`。未知开销不作零处理。" % (json.dumps(dict(tokens), ensure_ascii=False), usage_missing, json.dumps(dict(missing_tokens), ensure_ascii=False)), "",
             "内网费用按用户既定豁免口径，本审计不估算真实付费金额。", "",
             "## 网关路由与完成状态", "",
             "- 请求模型名：`%s`。" % json.dumps(dict(requested_models), ensure_ascii=False),
             "- 响应顶层模型名：`%s`。" % json.dumps(dict(response_models), ensure_ascii=False),
             "- usage 内模型名：`%s`。" % json.dumps(dict(usage_models), ensure_ascii=False),
             "- HTTP 状态：`%s`；finish_reason：`%s`。" % (json.dumps(dict(http_statuses)), json.dumps(dict(finishes))),
             "- 模块状态：`%s`；固定模块槽位 %s，已开始模块 %s。" % (json.dumps(summary["module_status_counts"], ensure_ascii=False), summary["module_slot_count"], summary["started_module_count"]),
             "- 发起过核验请求的模块数 %s；核验 HTTP200 响应 %s；有已解析核验结果的逻辑调用 %s。`verifier_executed` 只代表请求尝试，不代表服务已完成模型推理。" % (summary["modules_with_verifier_request_attempts"], summary["verifier_http200_response_count"], summary["verifier_parsed_result_count"]),
             "- 服务端错误类型：`%s`。仅保留错误类别，不抄录响应里的个人邮箱、团队或账户细节。" % json.dumps(dict(service_error_classes), ensure_ascii=False), "",
             "本轮 budget_exceeded 为 %s 次；本地请求 %s/%s、浏览器操作 %s/%s，仍在冻结上限内。该类阻塞来自服务端账户累计阈值，而不是本地实验预算用尽；这不是得到继续换账户、换服务或绕过限制的授权。" % (service_error_classes["budget_exceeded"], budget["attempts"], config["max_request_attempts"], budget["browser_operations"], config["max_browser_operations"]), "",
             "这些模型名都是网关自报字段，不是对底层权重的独立认证。length 计数仅反映协议报告的输出上限终止，不判断图像裁剪；本实验发送的图像尺寸和哈希逐次记录在 JSON 附录中。", "",
             "## 配对实际输入核对", "",
             "| 任务 | 生成器完整 user 消息相同 | 图像字节／标识相同 | system 提示不同 | 与原配对证明一致 | 核验候选集合相同 |",
             "|---|---|---|---|---|---|"]
    for pair in pairs:
        lines.append("| %s | %s | %s | %s | %s | %s |" % tuple(pair.get(key, "未发生／未知") for key in (
            "task_slug", "complete_user_payload_equal", "generator_image_bytes_and_refs_equal", "system_prompts_differ", "recorded_proof_matches_independent_check", "verifier_argument_sets_equal")))
    lines += ["", "生成器收到相同公开内容、初始提案和图像，只改变提示配置。核验器候选集允许因上游生成不同而不同；不能将它描述为对完全相同候选进行的单一核验器消融。两个阶段的提示都发生变化。", "",
              "## 浏览器与复现边界", "",
              "实际浏览器动作种类：`%s`。提交事件 %s；非空提交回执文件 %s。" % (json.dumps(summary["actual_browser_action_kinds"], ensure_ascii=False), summary["business_submit_events"], len(summary["nonempty_submission_receipt_files"])), "",
              "旧三例复用已有真实输入，不进行页面恢复；%s，不落实选择、不提交。该结果是观察／规则／推论模块诊断，不是新的自然轨迹结果、恢复率或业务完成率。" % fresh_sentence, "",
              "新两例取得已解析普通 Actor 提案的逻辑调用为 %s。完成记录中的 `source_tasks_added: 2` 表示固定的两个新增任务已纳入数据准备，不表示两例都成功接受了被测模块评测。未取得前置选择时，其两个提示配置均未运行。" % summary["fresh_ordinary_actor_successful_parsed_proposals"], "",
              "运行时源快照哈希检查：`%s`。本审计读取运行快照，不用当前可编辑源码冒充执行版本。" % json.dumps(source_hash_checks, ensure_ascii=False), "",
              "完整逐次请求、响应、模型路由、图像尺寸／哈希、候选裁剪索引和 JSON 修复日志见 [%s](%s)。" % (json_path.name, relative(json_path, md_path.parent)), "",
              "来源：[冻结协议](%s)、[实际总账](%s)、[完成记录](%s)。" % tuple(relative(run / name, md_path.parent) for name in ("frozen_protocol.json", "budget.json", "completion.json")), ""]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path), "request_attempts": len(attempts), "audit_api_calls": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True)
    parser.add_argument("--output-prefix", default=str(HERE / "COST_AND_WIRE_AUDIT_20260923"))
    arguments = parser.parse_args()
    print(json.dumps(audit(arguments.run, arguments.output_prefix), ensure_ascii=False, indent=2))
