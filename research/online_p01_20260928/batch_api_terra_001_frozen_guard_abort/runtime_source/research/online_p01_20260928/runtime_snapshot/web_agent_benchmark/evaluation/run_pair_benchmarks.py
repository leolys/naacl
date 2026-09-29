#!/usr/bin/env python3
"""Run paired official/clean browser-agent benchmark evaluations."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = REPO_ROOT / "web_agent_benchmark" / "evaluation"
RECORD_ROOT = REPO_ROOT / "web_agent_benchmark" / "pair_evaluation_records"

KIMIK2_BASE_URL = "http://10.240.24.60:8000/v1/chat/completions"
KIMIK2_MODEL = "kimik26"
LOCAL_VISION_CUDA_VISIBLE_DEVICES = "4,5,6,7"
QWEN_PYTHON = Path(
    "/mnt/data/code_generation/liyisheng/8H100conda/envs/qwen3_vl/bin/python"
)
QWEN32_MODEL_PATH = Path("/mnt/data/datasets/open_source_models/Qwen3-vl-32-instruct")
QWEN32_SERVER_URL = "http://127.0.0.1:8046"
LLAMA32_PYTHON = Path(
    "/mnt/data/code_generation/liyisheng/8H100conda/envs/internvl/bin/python"
)
LLAMA32_90B_MODEL_PATH = Path("/mnt/data/datasets/open_source_models/Llama-3.2-90B-Vision")
LLAMA32_90B_SERVER_URL = "http://127.0.0.1:8048"

SCENARIOS: dict[str, dict[str, Any]] = {
    "public39": {
        "task_count": 39,
        "runner": EVAL_DIR / "run_public39.py",
        "dryrun_tasks": "pub001,pub020,pub039",
        "full_tasks": "pub001-pub039",
        "tasks_file": "public39_tasks.jsonl",
        "base_slug": "public",
        "ports": {"official": 18226, "clean": 18326},
    },
    "business47": {
        "task_count": 47,
        "runner": EVAL_DIR / "run_business47.py",
        "dryrun_tasks": "b001,b024,b047",
        "full_tasks": "b001-b047",
        "tasks_file": "business47_tasks.jsonl",
        "base_slug": "business",
        "ports": {"official": 18216, "clean": 18316},
    },
    "environment35": {
        "task_count": 35,
        "runner": EVAL_DIR / "run_environment35.py",
        "dryrun_tasks": "env001,env017,env035",
        "full_tasks": "env001-env035",
        "tasks_file": "environment35_tasks.jsonl",
        "base_slug": "environment",
        "ports": {"official": 18233, "clean": 18333},
    },
    "health19": {
        "task_count": 19,
        "runner": EVAL_DIR / "run_health19.py",
        "dryrun_tasks": "health001,health010,health019",
        "full_tasks": "health001-health019",
        "tasks_file": "health19_tasks.jsonl",
        "base_slug": "health",
        "ports": {"official": 18237, "clean": 18337},
    },
}
SCENARIO_ORDER = ["public39", "business47", "environment35", "health19"]

BENCHMARK_DIRS = {
    "official": REPO_ROOT / "web_agent_benchmark" / "official_benchmark_v1",
    "clean": REPO_ROOT / "web_agent_benchmark" / "clean_benchmark_v1",
}

MODEL_PRESETS: dict[str, dict[str, Any]] = {
    "gpt54": {
        "record_slug": "gpt54_temp0_top_p1_seed12345",
        "agent_backend": "hexin_openai",
        "agent_model_family": "gpt",
        "agent_model_name": "gpt-5.4",
        "agent_model_id": "gpt-5.4",
        "max_output_tokens": 1024,
        "env": {
            "LLM_BACKEND": "hexin_openai",
            "HEXIN_MODEL": "gpt-5.4",
            "HTTP_PROXY": "",
            "HTTPS_PROXY": "",
            "ALL_PROXY": "",
            "NO_PROXY": "*",
        },
    },
    "kimik26": {
        "record_slug": "kimik2_6_temp0_top_p1_seed12345",
        "agent_backend": "kimik2_http",
        "agent_model_family": "kimik2",
        "agent_model_name": "Kimi-K2.6",
        "agent_model_id": KIMIK2_MODEL,
        "kimik2_base_url": KIMIK2_BASE_URL,
        "max_output_tokens": 8096,
        "env": {
            "LLM_BACKEND": "kimik2_http",
            "KIMIK2_BASE_URL": KIMIK2_BASE_URL,
            "KIMIK2_MODEL": KIMIK2_MODEL,
            "KIMIK2_ENABLE_THINKING": "true",
            "KIMIK2_MAX_RETRIES": "5",
            "KIMIK2_REQUEST_DELAY_SEC": "2",
            "KIMIK2_HTTP_READ_TIMEOUT_SEC": "900",
        },
    },
    "kimi_k2_6_aime_litellm": {
        "record_slug": "kimi_k2_6_aime_litellm_temp0_top_p1_seed12345",
        "agent_backend": "aime_litellm",
        "agent_model_family": "kimik2",
        "agent_model_name": "Kimi K2.6 AIME LiteLLM",
        "agent_model_id": "kimi-k2.6",
        "aime_litellm_base_url": "https://aimemodeldev.myhexin.com/litellm/v1",
        "aime_litellm_host_header": "",
        "max_output_tokens": 8096,
        "env": {
            "LLM_BACKEND": "aime_litellm",
            "AIME_LITELLM_BASE_URL": "https://aimemodeldev.myhexin.com/litellm/v1",
            "AIME_LITELLM_HOST_HEADER": "",
            "AIME_LITELLM_VERIFY_SSL": "true",
            "AIME_LITELLM_MODEL": "kimi-k2.6",
            "AIME_LITELLM_API_STYLE": "chat_completions",
            "AIME_LITELLM_MAX_RETRIES": "5",
            "AIME_LITELLM_REQUEST_DELAY_SEC": "2",
            "AIME_LITELLM_HTTP_READ_TIMEOUT_SEC": "900",
            "AIME_LITELLM_OMIT_TEMPERATURE": "true",
            "AIME_LITELLM_OMIT_TOP_P": "true",
        },
    },
    "kimik26_aime_rebuttal": {
        "record_slug": "kimik2_6_temp0_top_p1_seed12345",
        "agent_backend": "aime_litellm",
        "agent_model_family": "kimik2",
        "agent_model_name": "Kimi-K2.6 AIME rebuttal route",
        "agent_model_id": "kimi-k2.6",
        "aime_litellm_base_url": "https://aimemodeldev.myhexin.com/litellm/v1",
        "aime_litellm_host_header": "",
        "max_output_tokens": 8096,
        "env": {
            "LLM_BACKEND": "aime_litellm",
            "AIME_LITELLM_BASE_URL": "https://aimemodeldev.myhexin.com/litellm/v1",
            "AIME_LITELLM_HOST_HEADER": "",
            "AIME_LITELLM_VERIFY_SSL": "true",
            "AIME_LITELLM_MODEL": "kimi-k2.6",
            "AIME_LITELLM_API_STYLE": "chat_completions",
            "AIME_LITELLM_MAX_RETRIES": "5",
            "AIME_LITELLM_REQUEST_DELAY_SEC": "2",
            "AIME_LITELLM_HTTP_READ_TIMEOUT_SEC": "900",
            "AIME_LITELLM_OMIT_TEMPERATURE": "true",
            "AIME_LITELLM_OMIT_TOP_P": "true",
            "AIME_LITELLM_REASONING_CONTENT_FALLBACK": "true",
        },
    },
    "kimi_k2_6_vip_litellm": {
        "record_slug": "kimi_k2_6_vip_litellm_temp0_top_p1_seed12345",
        "agent_backend": "aime_litellm",
        "agent_model_family": "kimik2",
        "agent_model_name": "Kimi K2.6 VIP LiteLLM",
        "agent_model_id": "kimi-k2.6",
        "aime_litellm_base_url": "https://vip.yi-zhan.top/v1",
        "aime_litellm_host_header": "",
        "max_output_tokens": 8096,
        "env": {
            "LLM_BACKEND": "aime_litellm",
            "AIME_LITELLM_BASE_URL": "https://vip.yi-zhan.top/v1",
            "AIME_LITELLM_HOST_HEADER": "",
            "AIME_LITELLM_VERIFY_SSL": "true",
            "AIME_LITELLM_MODEL": "kimi-k2.6",
            "AIME_LITELLM_API_STYLE": "chat_completions",
            "AIME_LITELLM_MAX_RETRIES": "5",
            "AIME_LITELLM_REQUEST_DELAY_SEC": "2",
            "AIME_LITELLM_HTTP_READ_TIMEOUT_SEC": "900",
            "AIME_LITELLM_OMIT_TEMPERATURE": "true",
            "AIME_LITELLM_OMIT_TOP_P": "true",
            "AIME_LITELLM_REASONING_CONTENT_FALLBACK": "true",
        },
    },
    "gpt55_litellm": {
        "record_slug": "gpt_5_5_litellm_temp0_top_p1_seed12345",
        "agent_backend": "aime_litellm",
        "agent_model_family": "gpt",
        "agent_model_name": "GPT-5.5",
        "agent_model_id": "gpt-5.5",
        "aime_litellm_base_url": "https://127.0.0.1:18443/litellm/v1",
        "aime_litellm_host_header": "aimemodeldev.myhexin.com",
        "max_output_tokens": 8192,
        "env": {
            "LLM_BACKEND": "aime_litellm",
            "AIME_LITELLM_BASE_URL": "https://127.0.0.1:18443/litellm/v1",
            "AIME_LITELLM_HOST_HEADER": "aimemodeldev.myhexin.com",
            "AIME_LITELLM_VERIFY_SSL": "false",
            "AIME_LITELLM_MODEL": "gpt-5.5",
            "AIME_LITELLM_MAX_RETRIES": "2",
            "AIME_LITELLM_REQUEST_DELAY_SEC": "2",
            "AIME_LITELLM_HTTP_READ_TIMEOUT_SEC": "300",
            "AIME_LITELLM_OMIT_TEMPERATURE": "true",
            "AIME_LITELLM_OMIT_TOP_P": "true",
        },
    },
    "gpt56_sol_litellm": {
        "record_slug": "gpt_5_6_sol_litellm_temp0_top_p1_seed12345",
        "agent_backend": "aime_litellm",
        "agent_model_family": "gpt",
        "agent_model_name": "GPT-5.6-SOL",
        "agent_model_id": "gpt-5.6-sol",
        "aime_litellm_base_url": "https://hk.yi-zhan.top/v1",
        "aime_litellm_host_header": "",
        "max_output_tokens": 8192,
        "env": {
            "LLM_BACKEND": "aime_litellm",
            "AIME_LITELLM_BASE_URL": "https://hk.yi-zhan.top/v1",
            "AIME_LITELLM_HOST_HEADER": "",
            "AIME_LITELLM_VERIFY_SSL": "true",
            "AIME_LITELLM_MODEL": "gpt-5.6-sol",
            "AIME_LITELLM_API_STYLE": "chat_completions",
            "AIME_LITELLM_MAX_RETRIES": "2",
            "AIME_LITELLM_REQUEST_DELAY_SEC": "2",
            "AIME_LITELLM_HTTP_READ_TIMEOUT_SEC": "300",
            "AIME_LITELLM_OMIT_TEMPERATURE": "true",
            "AIME_LITELLM_OMIT_TOP_P": "true",
        },
    },
    "claude_haiku_4_5_litellm": {
        "record_slug": "claude_haiku_4_5_litellm_temp0_top_p1_seed12345",
        "agent_backend": "aime_litellm",
        "agent_model_family": "claude",
        "agent_model_name": "Claude Haiku 4.5",
        "agent_model_id": "claude-haiku-4-5-20251001",
        "aime_litellm_base_url": "https://127.0.0.1:18443/litellm/v1",
        "aime_litellm_host_header": "aimemodeldev.myhexin.com",
        "max_output_tokens": 4096,
        "env": {
            "LLM_BACKEND": "aime_litellm",
            "AIME_LITELLM_BASE_URL": "https://127.0.0.1:18443/litellm/v1",
            "AIME_LITELLM_HOST_HEADER": "aimemodeldev.myhexin.com",
            "AIME_LITELLM_VERIFY_SSL": "false",
            "AIME_LITELLM_MODEL": "claude-haiku-4-5-20251001",
            "AIME_LITELLM_MAX_RETRIES": "2",
            "AIME_LITELLM_REQUEST_DELAY_SEC": "2",
            "AIME_LITELLM_HTTP_READ_TIMEOUT_SEC": "300",
            "AIME_LITELLM_OMIT_TEMPERATURE": "true",
        },
    },
    "claude_sonnet_4_6_litellm": {
        "record_slug": "claude_sonnet_4_6_litellm_temp0_top_p1_seed12345",
        "agent_backend": "aime_litellm",
        "agent_model_family": "claude",
        "agent_model_name": "Claude Sonnet 4.6",
        "agent_model_id": "claude-sonnet-4-6",
        "aime_litellm_base_url": "https://vip.yi-zhan.top/v1",
        "aime_litellm_host_header": "",
        "max_output_tokens": 4096,
        "env": {
            "LLM_BACKEND": "aime_litellm",
            "AIME_LITELLM_BASE_URL": "https://vip.yi-zhan.top/v1",
            "AIME_LITELLM_HOST_HEADER": "",
            "AIME_LITELLM_VERIFY_SSL": "true",
            "AIME_LITELLM_MODEL": "claude-sonnet-4-6",
            "AIME_LITELLM_MAX_RETRIES": "2",
            "AIME_LITELLM_REQUEST_DELAY_SEC": "2",
            "AIME_LITELLM_HTTP_READ_TIMEOUT_SEC": "300",
            "AIME_LITELLM_OMIT_TEMPERATURE": "true",
        },
    },
    "claude_opus_4_6_litellm": {
        "record_slug": "claude_opus_4_6_litellm_temp0_top_p1_seed12345",
        "agent_backend": "aime_litellm",
        "agent_model_family": "claude",
        "agent_model_name": "Claude Opus 4.6",
        "agent_model_id": "claude-opus-4-6",
        "aime_litellm_base_url": "https://vip.yi-zhan.top/v1",
        "aime_litellm_host_header": "",
        "max_output_tokens": 4096,
        "env": {
            "LLM_BACKEND": "aime_litellm",
            "AIME_LITELLM_BASE_URL": "https://vip.yi-zhan.top/v1",
            "AIME_LITELLM_HOST_HEADER": "",
            "AIME_LITELLM_VERIFY_SSL": "true",
            "AIME_LITELLM_MODEL": "claude-opus-4-6",
            "AIME_LITELLM_MAX_RETRIES": "2",
            "AIME_LITELLM_REQUEST_DELAY_SEC": "2",
            "AIME_LITELLM_HTTP_READ_TIMEOUT_SEC": "300",
            "AIME_LITELLM_OMIT_TEMPERATURE": "true",
        },
    },
    "claude_opus_4_6_aime_litellm": {
        "record_slug": "claude_opus_4_6_aime_litellm_temp0_top_p1_seed12345",
        "agent_backend": "aime_litellm",
        "agent_model_family": "claude",
        "agent_model_name": "Claude Opus 4.6 AIME Chat Completions",
        "agent_model_id": "claude-opus-4-6",
        "aime_litellm_base_url": "https://127.0.0.1:18443/litellm/v1",
        "aime_litellm_host_header": "aimemodeldev.myhexin.com",
        "max_output_tokens": 4096,
        "env": {
            "LLM_BACKEND": "aime_litellm",
            "AIME_LITELLM_BASE_URL": "https://127.0.0.1:18443/litellm/v1",
            "AIME_LITELLM_HOST_HEADER": "aimemodeldev.myhexin.com",
            "AIME_LITELLM_VERIFY_SSL": "false",
            "AIME_LITELLM_MODEL": "claude-opus-4-6",
            "AIME_LITELLM_API_STYLE": "chat_completions",
            "AIME_LITELLM_MAX_RETRIES": "2",
            "AIME_LITELLM_REQUEST_DELAY_SEC": "2",
            "AIME_LITELLM_HTTP_READ_TIMEOUT_SEC": "300",
            "AIME_LITELLM_OMIT_TEMPERATURE": "true",
        },
    },
    "claude_opus_4_6_aime_uuid_slow": {
        "record_slug": "claude_opus_4_6_aime_uuid_slow_temp0_top_p1_seed12345",
        "agent_backend": "aime_litellm",
        "agent_model_family": "claude",
        "agent_model_name": "Claude Opus 4.6 AIME UUID Slow",
        "agent_model_id": "4c4e1f81-2e5b-4f4b-a93e-aef382cf3732",
        "aime_litellm_base_url": "https://127.0.0.1:18443/litellm/v1",
        "aime_litellm_host_header": "aimemodeldev.myhexin.com",
        "max_output_tokens": 2048,
        "env": {
            "LLM_BACKEND": "aime_litellm",
            "AIME_LITELLM_BASE_URL": "https://127.0.0.1:18443/litellm/v1",
            "AIME_LITELLM_HOST_HEADER": "aimemodeldev.myhexin.com",
            "AIME_LITELLM_VERIFY_SSL": "false",
            "AIME_LITELLM_MODEL": "4c4e1f81-2e5b-4f4b-a93e-aef382cf3732",
            "AIME_LITELLM_API_STYLE": "chat_completions",
            "AIME_LITELLM_MAX_RETRIES": "5",
            "AIME_LITELLM_REQUEST_DELAY_SEC": "30",
            "AIME_LITELLM_HTTP_READ_TIMEOUT_SEC": "60",
            "AIME_LITELLM_OMIT_TEMPERATURE": "true",
        },
    },
    "claude_sonnet_4_6_aime_responses": {
        "record_slug": "claude_sonnet_4_6_aime_responses_temp0_top_p1_seed12345",
        "agent_backend": "aime_litellm",
        "agent_model_family": "claude",
        "agent_model_name": "Claude Sonnet 4.6 AIME Responses",
        "agent_model_id": "claude-sonnet-4-6",
        "aime_litellm_base_url": "https://127.0.0.1:18443/litellm/v1",
        "aime_litellm_host_header": "aimemodeldev.myhexin.com",
        "max_output_tokens": 4096,
        "env": {
            "LLM_BACKEND": "aime_litellm",
            "AIME_LITELLM_BASE_URL": "https://127.0.0.1:18443/litellm/v1",
            "AIME_LITELLM_HOST_HEADER": "aimemodeldev.myhexin.com",
            "AIME_LITELLM_VERIFY_SSL": "false",
            "AIME_LITELLM_MODEL": "claude-sonnet-4-6",
            "AIME_LITELLM_API_STYLE": "responses",
            "AIME_LITELLM_MAX_RETRIES": "2",
            "AIME_LITELLM_REQUEST_DELAY_SEC": "2",
            "AIME_LITELLM_HTTP_READ_TIMEOUT_SEC": "300",
            "AIME_LITELLM_OMIT_TEMPERATURE": "true",
        },
    },
    "claude_opus_4_6_aime_responses": {
        "record_slug": "claude_opus_4_6_aime_responses_temp0_top_p1_seed12345",
        "agent_backend": "aime_litellm",
        "agent_model_family": "claude",
        "agent_model_name": "Claude Opus 4.6 AIME Responses",
        "agent_model_id": "claude-opus-4-6",
        "aime_litellm_base_url": "https://127.0.0.1:18443/litellm/v1",
        "aime_litellm_host_header": "aimemodeldev.myhexin.com",
        "max_output_tokens": 4096,
        "env": {
            "LLM_BACKEND": "aime_litellm",
            "AIME_LITELLM_BASE_URL": "https://127.0.0.1:18443/litellm/v1",
            "AIME_LITELLM_HOST_HEADER": "aimemodeldev.myhexin.com",
            "AIME_LITELLM_VERIFY_SSL": "false",
            "AIME_LITELLM_MODEL": "claude-opus-4-6",
            "AIME_LITELLM_API_STYLE": "responses",
            "AIME_LITELLM_MAX_RETRIES": "2",
            "AIME_LITELLM_REQUEST_DELAY_SEC": "2",
            "AIME_LITELLM_HTTP_READ_TIMEOUT_SEC": "300",
            "AIME_LITELLM_OMIT_TEMPERATURE": "true",
        },
    },
    "claude_opus_4_7_aime_responses": {
        "record_slug": "claude_opus_4_7_aime_responses_temp0_top_p1_seed12345",
        "agent_backend": "aime_litellm",
        "agent_model_family": "claude",
        "agent_model_name": "Claude Opus 4.7 AIME Responses",
        "agent_model_id": "claude-opus-4-7",
        "aime_litellm_base_url": "https://127.0.0.1:18444/litellm/v1",
        "aime_litellm_host_header": "aimemodeldev.myhexin.com",
        "max_output_tokens": 4096,
        "env": {
            "LLM_BACKEND": "aime_litellm",
            "AIME_LITELLM_BASE_URL": "https://127.0.0.1:18444/litellm/v1",
            "AIME_LITELLM_HOST_HEADER": "aimemodeldev.myhexin.com",
            "AIME_LITELLM_VERIFY_SSL": "false",
            "AIME_LITELLM_MODEL": "claude-opus-4-7",
            "AIME_LITELLM_API_STYLE": "responses",
            "AIME_LITELLM_MAX_RETRIES": "2",
            "AIME_LITELLM_REQUEST_DELAY_SEC": "2",
            "AIME_LITELLM_HTTP_READ_TIMEOUT_SEC": "300",
            "AIME_LITELLM_OMIT_TEMPERATURE": "true",
            "AIME_LITELLM_OMIT_TOP_P": "true",
        },
    },
    "claude_opus_4_8_aime_messages": {
        "record_slug": "claude_opus_4_8_aime_messages_temp0_top_p1_seed12345",
        "agent_backend": "aime_litellm",
        "agent_model_family": "claude",
        "agent_model_name": "Claude Opus 4.8 AIME Messages",
        "agent_model_id": "claude-opus-4-8",
        "aime_litellm_base_url": "https://aimemodeldev.myhexin.com/litellm/v1",
        "aime_litellm_host_header": "",
        "max_output_tokens": 4096,
        "env": {
            "LLM_BACKEND": "aime_litellm",
            "AIME_LITELLM_BASE_URL": "https://aimemodeldev.myhexin.com/litellm/v1",
            "AIME_LITELLM_HOST_HEADER": "",
            "AIME_LITELLM_VERIFY_SSL": "true",
            "AIME_LITELLM_MODEL": "claude-opus-4-8",
            "AIME_LITELLM_API_STYLE": "messages",
            "AIME_LITELLM_MAX_RETRIES": "2",
            "AIME_LITELLM_REQUEST_DELAY_SEC": "2",
            "AIME_LITELLM_HTTP_READ_TIMEOUT_SEC": "300",
            "AIME_LITELLM_OMIT_TEMPERATURE": "true",
            "AIME_LITELLM_OMIT_TOP_P": "true",
        },
    },
    "gemini3pro_image_preview": {
        "record_slug": "gemini_3_pro_image_preview_temp0_top_p1_seed12345",
        "agent_backend": "aime_litellm",
        "agent_model_family": "gemini",
        "agent_model_name": "Gemini 3 Pro Image Preview",
        "agent_model_id": "gemini-3-pro-image-preview",
        "aime_litellm_base_url": "https://127.0.0.1:18443/litellm/v1",
        "aime_litellm_host_header": "aimemodeldev.myhexin.com",
        "max_output_tokens": 1024,
        "env": {
            "LLM_BACKEND": "aime_litellm",
            "AIME_LITELLM_BASE_URL": "https://127.0.0.1:18443/litellm/v1",
            "AIME_LITELLM_HOST_HEADER": "aimemodeldev.myhexin.com",
            "AIME_LITELLM_VERIFY_SSL": "false",
            "AIME_LITELLM_MODEL": "gemini-3-pro-image-preview",
            "AIME_LITELLM_MAX_RETRIES": "0",
            "AIME_LITELLM_REQUEST_DELAY_SEC": "0",
            "AIME_LITELLM_HTTP_READ_TIMEOUT_SEC": "90",
        },
    },
    "gemini31pro_preview": {
        "record_slug": "gemini_3_1_pro_preview_temp0_top_p1_seed12345",
        "agent_backend": "aime_litellm",
        "agent_model_family": "gemini",
        "agent_model_name": "Gemini 3.1 Pro Preview",
        "agent_model_id": "gemini-3.1-pro-preview",
        "aime_litellm_base_url": "https://vip.yi-zhan.top/v1",
        "aime_litellm_host_header": "",
        "max_output_tokens": 1024,
        "env": {
            "LLM_BACKEND": "aime_litellm",
            "AIME_LITELLM_BASE_URL": "https://vip.yi-zhan.top/v1",
            "AIME_LITELLM_HOST_HEADER": "",
            "AIME_LITELLM_VERIFY_SSL": "true",
            "AIME_LITELLM_MODEL": "gemini-3.1-pro-preview",
            "AIME_LITELLM_MAX_RETRIES": "0",
            "AIME_LITELLM_REQUEST_DELAY_SEC": "0",
            "AIME_LITELLM_HTTP_READ_TIMEOUT_SEC": "90",
        },
    },
    "gemini31flash_image_preview": {
        "record_slug": "gemini_3_1_flash_image_preview_temp0_top_p1_seed12345",
        "agent_backend": "aime_litellm",
        "agent_model_family": "gemini",
        "agent_model_name": "Gemini 3.1 Flash Image Preview",
        "agent_model_id": "gemini-3.1-flash-image-preview",
        "aime_litellm_base_url": "https://127.0.0.1:18443/litellm/v1",
        "aime_litellm_host_header": "aimemodeldev.myhexin.com",
        "max_output_tokens": 1024,
        "env": {
            "LLM_BACKEND": "aime_litellm",
            "AIME_LITELLM_BASE_URL": "https://127.0.0.1:18443/litellm/v1",
            "AIME_LITELLM_HOST_HEADER": "aimemodeldev.myhexin.com",
            "AIME_LITELLM_VERIFY_SSL": "false",
            "AIME_LITELLM_MODEL": "gemini-3.1-flash-image-preview",
            "AIME_LITELLM_MAX_RETRIES": "0",
            "AIME_LITELLM_REQUEST_DELAY_SEC": "0",
            "AIME_LITELLM_HTTP_READ_TIMEOUT_SEC": "90",
        },
    },
    "qwen35plus_litellm": {
        "record_slug": "qwen3_5_plus_temp0_top_p1_seed12345",
        "agent_backend": "aime_litellm",
        "agent_model_family": "qwen",
        "agent_model_name": "Qwen3.5 Plus",
        "agent_model_id": "qwen3.5-plus",
        "aime_litellm_base_url": "https://127.0.0.1:18443/litellm/v1",
        "aime_litellm_host_header": "aimemodeldev.myhexin.com",
        "max_output_tokens": 1024,
        "env": {
            "LLM_BACKEND": "aime_litellm",
            "AIME_LITELLM_BASE_URL": "https://127.0.0.1:18443/litellm/v1",
            "AIME_LITELLM_HOST_HEADER": "aimemodeldev.myhexin.com",
            "AIME_LITELLM_VERIFY_SSL": "false",
            "AIME_LITELLM_MODEL": "qwen3.5-plus",
            "AIME_LITELLM_MAX_RETRIES": "0",
            "AIME_LITELLM_REQUEST_DELAY_SEC": "0",
            "AIME_LITELLM_HTTP_READ_TIMEOUT_SEC": "90",
        },
    },
    "qwen36plus_litellm": {
        "record_slug": "qwen3_6_plus_temp0_top_p1_seed12345",
        "agent_backend": "aime_litellm",
        "agent_model_family": "qwen",
        "agent_model_name": "Qwen3.6 Plus",
        "agent_model_id": "qwen3.6-plus",
        "aime_litellm_base_url": "https://127.0.0.1:18443/litellm/v1",
        "aime_litellm_host_header": "aimemodeldev.myhexin.com",
        "max_output_tokens": 1024,
        "env": {
            "LLM_BACKEND": "aime_litellm",
            "AIME_LITELLM_BASE_URL": "https://127.0.0.1:18443/litellm/v1",
            "AIME_LITELLM_HOST_HEADER": "aimemodeldev.myhexin.com",
            "AIME_LITELLM_VERIFY_SSL": "false",
            "AIME_LITELLM_MODEL": "qwen3.6-plus",
            "AIME_LITELLM_MAX_RETRIES": "0",
            "AIME_LITELLM_REQUEST_DELAY_SEC": "0",
            "AIME_LITELLM_HTTP_READ_TIMEOUT_SEC": "90",
        },
    },
    "qwen3vl32b": {
        "record_slug": "qwen3_vl_32b_temp0_top_p1_seed12345",
        "agent_backend": "qwen3_vl_http",
        "agent_model_family": "qwen3_vl",
        "agent_model_name": "Qwen3-VL-32B-Instruct",
        "agent_model_id": "Qwen3-VL-32B-Instruct",
        "agent_model_size": "32b",
        "model_path": QWEN32_MODEL_PATH,
        "server_url": QWEN32_SERVER_URL,
        "server_script": EVAL_DIR / "qwen3_vl_server.py",
        "server_python": QWEN_PYTHON,
        "server_log_dir": EVAL_DIR / "qwen3_vl_server_logs",
        "server_log_prefix": "32b_pair",
        "cuda_visible_devices": LOCAL_VISION_CUDA_VISIBLE_DEVICES,
        "start_timeout": 1800,
        "max_pixels": 1280 * 28 * 28,
        "max_output_tokens": 1024,
        "env": {
            "LLM_BACKEND": "qwen3_vl_http",
            "QWEN3_VL_SERVER_URL": QWEN32_SERVER_URL,
            "QWEN3_VL_MODEL_PATH": str(QWEN32_MODEL_PATH),
            "QWEN3_VL_MODEL_SIZE": "32b",
            "QWEN3_VL_MODEL": "Qwen3-VL-32B-Instruct",
        },
    },
    "llama32vision90b": {
        "record_slug": "llama3_2_vision_90b_temp0_top_p1_seed12345",
        "agent_backend": "llama32_vision_http",
        "agent_model_family": "llama3_2_vision",
        "agent_model_name": "Llama-3.2-Vision-90B",
        "agent_model_id": "Llama-3.2-Vision-90B",
        "agent_model_size": "90b",
        "model_path": LLAMA32_90B_MODEL_PATH,
        "server_url": LLAMA32_90B_SERVER_URL,
        "server_script": EVAL_DIR / "llama32_vision_server.py",
        "server_python": LLAMA32_PYTHON,
        "server_log_dir": EVAL_DIR / "llama32_vision_server_logs",
        "server_log_prefix": "90b_pair",
        "cuda_visible_devices": LOCAL_VISION_CUDA_VISIBLE_DEVICES,
        "start_timeout": 3600,
        "max_output_tokens": 1024,
        "env": {
            "LLM_BACKEND": "llama32_vision_http",
            "LLAMA32_VISION_SERVER_URL": LLAMA32_90B_SERVER_URL,
            "LLAMA32_VISION_MODEL_PATH": str(LLAMA32_90B_MODEL_PATH),
            "LLAMA32_VISION_MODEL_SIZE": "90b",
            "LLAMA32_VISION_MODEL": "Llama-3.2-Vision-90B",
        },
    },
}


class LocalModelServerHandle:
    def __init__(self, process: subprocess.Popen[str] | None = None) -> None:
        self.process = process

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self.process.kill()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def benchmark_choices(raw: str) -> list[str]:
    if raw == "both":
        return ["official", "clean"]
    return [raw]


def model_choices(raw: str) -> list[str]:
    models = [item.strip() for item in raw.split(",") if item.strip()]
    unknown = [item for item in models if item not in MODEL_PRESETS]
    if unknown:
        raise RuntimeError(f"Unknown model preset(s): {', '.join(unknown)}")
    return models


def local_server_health_ok(server_url: str, *, model_path: Path | None = None) -> bool:
    import requests

    session = requests.Session()
    session.trust_env = False
    try:
        response = session.get(f"{server_url.rstrip('/')}/health", timeout=2)
        if response.status_code != 200:
            return False
        data = response.json()
        if not data.get("ok"):
            return False
        if model_path and str(model_path) != data.get("model_path"):
            return False
        return True
    except Exception:
        return False


def print_gpu_snapshot(devices: str) -> None:
    cmd = [
        "nvidia-smi",
        "--query-gpu=index,name,memory.used,memory.total",
        "--format=csv,noheader",
        "-i",
        devices,
    ]
    try:
        completed = subprocess.run(cmd, check=False, text=True, capture_output=True)
    except FileNotFoundError:
        print("[pair] nvidia-smi not found; skipping GPU snapshot")
        return
    if completed.returncode == 0 and completed.stdout.strip():
        print(f"[pair] GPU snapshot for {devices}:")
        print(completed.stdout.strip())
    elif completed.stderr.strip():
        print(f"[pair] GPU snapshot unavailable: {completed.stderr.strip()}")


def ensure_local_model_server(model_key: str) -> LocalModelServerHandle:
    preset = MODEL_PRESETS[model_key]
    if "server_script" not in preset:
        return LocalModelServerHandle()
    server_url = str(preset["server_url"]).rstrip("/")
    model_path = Path(preset["model_path"])
    if local_server_health_ok(server_url, model_path=model_path):
        print(f"[pair] Reusing {preset['agent_model_name']} server at {server_url}")
        return LocalModelServerHandle()

    server_python = Path(preset["server_python"])
    server_script = Path(preset["server_script"])
    if not server_python.exists():
        raise RuntimeError(f"Local model Python does not exist: {server_python}")
    if not server_script.exists():
        raise RuntimeError(f"Local model server script does not exist: {server_script}")
    if not model_path.exists():
        raise RuntimeError(f"Local model path does not exist: {model_path}")

    print_gpu_snapshot(str(preset["cuda_visible_devices"]))
    port = int(server_url.rsplit(":", 1)[-1])
    log_dir = Path(preset["server_log_dir"])
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{preset['server_log_prefix']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    cmd = [
        str(server_python),
        str(server_script),
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--model-path",
        str(model_path),
        "--model-size",
        str(preset["agent_model_size"]),
    ]
    if model_key == "qwen3vl32b":
        cmd.extend(["--max-pixels", str(preset["max_pixels"])])
    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = str(preset["cuda_visible_devices"])
    env.setdefault("TOKENIZERS_PARALLELISM", "false")
    print(f"[pair] Starting {preset['agent_model_name']} server at {server_url}")
    print(f"[pair] Local model server log: {log_path}")
    log_fh = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        cmd,
        cwd=str(REPO_ROOT),
        env=env,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        text=True,
    )
    log_fh.close()

    deadline = time.time() + int(preset["start_timeout"])
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"{preset['agent_model_name']} server exited with code {process.returncode}. "
                f"See log: {log_path}"
            )
        if local_server_health_ok(server_url, model_path=model_path):
            print(f"[pair] {preset['agent_model_name']} server ready: {server_url}")
            return LocalModelServerHandle(process)
        time.sleep(5)
    process.terminate()
    raise RuntimeError(
        f"{preset['agent_model_name']} server did not become ready within "
        f"{preset['start_timeout']}s. Log: {log_path}"
    )


def parse_task_overrides(raw: str | None) -> dict[str, str]:
    if not raw:
        return {}
    overrides: dict[str, str] = {}
    for chunk in raw.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "=" not in chunk:
            raise RuntimeError(f"Invalid task override chunk: {chunk}")
        scenario_name, task_spec = chunk.split("=", 1)
        scenario_name = scenario_name.strip()
        task_spec = task_spec.strip()
        if scenario_name not in SCENARIOS:
            raise RuntimeError(f"Unknown task override scenario: {scenario_name}")
        if not task_spec:
            raise RuntimeError(f"Empty task override for {scenario_name}")
        overrides[scenario_name] = task_spec
    return overrides


def parse_scenarios(raw: str | None) -> list[str]:
    if not raw:
        return list(SCENARIO_ORDER)
    requested = [item.strip() for item in raw.split(",") if item.strip()]
    unknown = [item for item in requested if item not in SCENARIOS]
    if unknown:
        raise RuntimeError(f"Unknown scenario(s): {', '.join(unknown)}")
    return [name for name in SCENARIO_ORDER if name in requested]


def count_jsonl(path: Path) -> int:
    return len(read_jsonl(path))


def benchmark_root(args: argparse.Namespace, benchmark: str) -> Path:
    override = getattr(args, f"{benchmark}_root", None)
    return Path(override) if override else BENCHMARK_DIRS[benchmark]


def benchmark_version_for(args: argparse.Namespace, benchmark: str) -> str:
    root = benchmark_root(args, benchmark)
    root_text = root.as_posix()
    if "benchmark_v2_open" in root_text:
        return "benchmark_v2_open_official140" if benchmark == "official" else "benchmark_v2_open_clean140"
    return "official_benchmark_v1" if benchmark == "official" else "clean_benchmark_v1"


def validate_task_files(benchmark: str, args: argparse.Namespace) -> None:
    root = benchmark_root(args, benchmark)
    for scenario_name, meta in SCENARIOS.items():
        path = root / meta["tasks_file"]
        found = count_jsonl(path)
        expected = int(meta["task_count"])
        if found != expected:
            raise RuntimeError(f"{benchmark} {scenario_name} expected {expected} tasks, found {found}: {path}")


def selected_action_from_submission(submission: dict[str, Any]) -> tuple[str, str]:
    return str(submission.get("selected_action_id", "")), str(submission.get("selected_action_label", ""))


def enrich_row(
    row: dict[str, Any],
    *,
    benchmark: str,
    scenario_name: str,
    model_key: str,
    model_metadata: dict[str, Any],
    record_dir: Path,
    benchmark_version: str,
) -> dict[str, Any]:
    payload = dict(row)
    payload["benchmark_version"] = benchmark_version
    payload["benchmark"] = benchmark
    payload["scenario"] = scenario_name
    payload["model_key"] = model_key
    payload["model_metadata"] = model_metadata
    submission = payload.get("submission") or {}
    selected_id, selected_label = selected_action_from_submission(submission)
    payload.setdefault("selected_action_id", selected_id)
    payload.setdefault("selected_action_label", selected_label)
    try:
        payload["record_dir"] = str(record_dir.resolve().relative_to(REPO_ROOT))
    except ValueError:
        payload["record_dir"] = str(record_dir.resolve())
    return payload


def is_transient_model_failure(row: dict[str, Any]) -> bool:
    if row.get("outcome") == "success":
        return False
    haystack = " ".join(
        [
            str(row.get("exception", "")),
            str(row.get("error_attribution", "")),
            json.dumps(row.get("trace", []), ensure_ascii=False),
        ]
    ).lower()
    markers = [
        "kimi k2.6 request failed",
        "transient http",
        "http 429",
        "http 502",
        "http 503",
        "http 504",
        "connection error",
        "timed out",
        "empty response",
        "empty final content",
        "llm_action_generation_error",
    ]
    return any(marker in haystack for marker in markers)


def summarize_rows(rows: list[dict[str, Any]], scenarios: list[str] | None = None) -> dict[str, Any]:
    counts = Counter(row.get("outcome", "unknown") for row in rows)
    by_scenario: dict[str, dict[str, Any]] = {}
    for scenario_name in scenarios or SCENARIO_ORDER:
        subset = [row for row in rows if row.get("scenario") == scenario_name]
        if not subset:
            continue
        scenario_counts = Counter(row.get("outcome", "unknown") for row in subset)
        by_scenario[scenario_name] = {
            "task_count": len(subset),
            "success_count": scenario_counts.get("success", 0),
            "success_rate": scenario_counts.get("success", 0) / len(subset),
            "outcome_counts": dict(scenario_counts),
        }
    return {
        "task_count": len(rows),
        "success_count": counts.get("success", 0),
        "success_rate": counts.get("success", 0) / len(rows) if rows else 0.0,
        "outcome_counts": dict(counts),
        "by_scenario": by_scenario,
    }


def write_summary(
    path: Path,
    rows: list[dict[str, Any]],
    *,
    benchmark: str,
    model_key: str,
    profile: str,
    scenarios: list[str] | None = None,
) -> None:
    scenario_list = scenarios or SCENARIO_ORDER
    summary = summarize_rows(rows, scenario_list)
    lines = [
        f"# {model_key} {benchmark} Benchmark Evaluation Summary",
        "",
        f"- Generated at: `{utc_now()}`",
        f"- Benchmark: `{benchmark}`",
        f"- Profile: `{profile}`",
        f"- Total tasks: `{summary['task_count']}`",
        f"- Success count: `{summary['success_count']}`",
        f"- Success rate: `{summary['success_rate']:.2%}`",
        f"- Outcome distribution: `{summary['outcome_counts']}`",
        "",
        "## By Scenario",
        "",
        "| Scenario | Task Count | Success | Success Rate | Outcomes |",
        "|---|---:|---:|---:|---|",
    ]
    for scenario_name in scenario_list:
        row = summary["by_scenario"].get(scenario_name)
        if row:
            lines.append(
                f"| {scenario_name} | {row['task_count']} | {row['success_count']} | "
                f"{row['success_rate']:.2%} | `{row['outcome_counts']}` |"
            )
    lines.extend(
        [
            "",
            "## Task-Level Results",
            "",
            "| Scenario | Slug | Task ID | Outcome | Error Attribution | Selected Action |",
            "|---|---|---|---|---|---|",
        ]
    )
    for row in rows:
        lines.append(
            f"| {row.get('scenario','')} | {row.get('slug','')} | {row.get('task_id','')} | "
            f"{row.get('outcome','')} | {row.get('error_attribution','')} | "
            f"{row.get('selected_action_label','')} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def model_metadata_for(model_key: str, args: argparse.Namespace) -> dict[str, Any]:
    preset = MODEL_PRESETS[model_key]
    effective_env = effective_model_env(model_key, args)
    metadata = {
        "agent_backend": preset["agent_backend"],
        "agent_model_family": preset["agent_model_family"],
        "agent_model_name": preset["agent_model_name"],
        "agent_model_id": preset["agent_model_id"],
        "max_output_tokens": effective_max_output_tokens(model_key, args),
        "generation_config": {
            "temperature": args.temperature,
            "top_p": args.top_p,
            "seed": args.seed,
        },
    }
    if model_key == "kimik26":
        metadata["kimik2_base_url"] = preset["kimik2_base_url"]
        metadata["generation_config"]["thinking"] = True
        metadata["retry_config"] = {
            "max_retries": 5,
            "request_delay_sec": 2.0,
            "read_timeout_sec": 900.0,
            "trust_env_proxy": False,
        }
    if preset["agent_backend"] == "aime_litellm":
        metadata["aime_litellm_base_url"] = effective_env.get(
            "AIME_LITELLM_BASE_URL",
            preset["aime_litellm_base_url"],
        )
        metadata["aime_litellm_host_header"] = effective_env.get(
            "AIME_LITELLM_HOST_HEADER",
            preset.get("aime_litellm_host_header"),
        )
        metadata["aime_litellm_verify_ssl"] = (
            effective_env.get("AIME_LITELLM_VERIFY_SSL", "true").lower() == "true"
        )
        metadata["aime_litellm_api_style"] = effective_env.get(
            "AIME_LITELLM_API_STYLE", "chat_completions"
        )
        metadata["aime_litellm_proxy_enabled"] = bool(
            effective_env.get("AIME_LITELLM_PROXY", "").strip()
        )
        metadata["retry_config"] = {
            "max_retries": int(effective_env.get("AIME_LITELLM_MAX_RETRIES", "5")),
            "request_delay_sec": float(effective_env.get("AIME_LITELLM_REQUEST_DELAY_SEC", "1")),
            "read_timeout_sec": float(effective_env.get("AIME_LITELLM_HTTP_READ_TIMEOUT_SEC", "900")),
        }
        extra_body_json = effective_env.get("AIME_LITELLM_EXTRA_BODY_JSON", "")
        if extra_body_json:
            metadata["aime_litellm_extra_body_json"] = extra_body_json
        if args.experiment_variant:
            metadata["experiment_variant"] = args.experiment_variant
        if args.thinking_budget_supported:
            metadata["thinking_budget_supported"] = args.thinking_budget_supported
    if preset["agent_backend"] in {"qwen3_vl_http", "llama32_vision_http"}:
        metadata["agent_model_size"] = preset["agent_model_size"]
        metadata["model_path"] = str(preset["model_path"])
        metadata["server_url"] = preset["server_url"]
        metadata["cuda_visible_devices"] = preset["cuda_visible_devices"]
    if args.extra_system_prompt:
        metadata["extra_system_prompt"] = args.extra_system_prompt
    if args.record_slug_suffix:
        metadata["record_slug_suffix"] = args.record_slug_suffix
    if args.policy_middleware:
        metadata["policy_middleware"] = args.policy_middleware
    return metadata


def record_slug_for(model_key: str, args: argparse.Namespace) -> str:
    return str(MODEL_PRESETS[model_key]["record_slug"]) + str(args.record_slug_suffix or "")


def effective_max_output_tokens(model_key: str, args: argparse.Namespace) -> int:
    if args.model_max_output_tokens is not None:
        return int(args.model_max_output_tokens)
    return int(MODEL_PRESETS[model_key]["max_output_tokens"])


def effective_model_env(model_key: str, args: argparse.Namespace) -> dict[str, str]:
    preset = MODEL_PRESETS[model_key]
    env = dict(preset["env"])
    if preset["agent_backend"] == "aime_litellm":
        if args.aime_base_url is not None:
            env["AIME_LITELLM_BASE_URL"] = args.aime_base_url
        if args.aime_model is not None:
            env["AIME_LITELLM_MODEL"] = args.aime_model
        if args.aime_host_header is not None:
            env["AIME_LITELLM_HOST_HEADER"] = args.aime_host_header
        if args.aime_verify_ssl is not None:
            env["AIME_LITELLM_VERIFY_SSL"] = args.aime_verify_ssl
        if args.aime_api_style is not None:
            env["AIME_LITELLM_API_STYLE"] = args.aime_api_style
        if args.aime_proxy is not None:
            env["AIME_LITELLM_PROXY"] = args.aime_proxy
        if args.aime_max_retries is not None:
            env["AIME_LITELLM_MAX_RETRIES"] = str(args.aime_max_retries)
        if args.aime_request_delay_sec is not None:
            env["AIME_LITELLM_REQUEST_DELAY_SEC"] = str(args.aime_request_delay_sec)
        if args.aime_read_timeout_sec is not None:
            env["AIME_LITELLM_HTTP_READ_TIMEOUT_SEC"] = str(args.aime_read_timeout_sec)
        if args.aime_extra_body_json is not None:
            env["AIME_LITELLM_EXTRA_BODY_JSON"] = args.aime_extra_body_json
        elif os.environ.get("AIME_LITELLM_EXTRA_BODY_JSON"):
            env["AIME_LITELLM_EXTRA_BODY_JSON"] = os.environ["AIME_LITELLM_EXTRA_BODY_JSON"]
    return env


def run_scenario(
    *,
    benchmark: str,
    scenario_name: str,
    model_key: str,
    record_dir: Path,
    profile: str,
    args: argparse.Namespace,
    model_metadata: dict[str, Any],
) -> list[dict[str, Any]]:
    meta = SCENARIOS[scenario_name]
    scenario_dir = record_dir / "_scenario_outputs" / scenario_name
    scenario_dir.mkdir(parents=True, exist_ok=True)
    runs_out = scenario_dir / "runs.jsonl"
    summary_out = scenario_dir / "summary.md"
    failures_out = scenario_dir / "failures.jsonl"
    submissions = record_dir / "submissions" / f"{scenario_name}.jsonl"
    screenshot_dir = record_dir / "screenshots" / scenario_name
    for path in [runs_out, summary_out, failures_out, submissions]:
        if path.exists():
            path.unlink()
    if screenshot_dir.exists():
        shutil.rmtree(screenshot_dir)
    task_spec = str(args.task_overrides.get(scenario_name) or (meta["dryrun_tasks"] if profile == "dryrun" else meta["full_tasks"]))
    tasks_file = benchmark_root(args, benchmark) / str(meta["tasks_file"])
    port = int(meta["ports"][benchmark]) + int(getattr(args, "port_offset", 0) or 0)
    cmd = [
        sys.executable,
        str(meta["runner"]),
        "--mode",
        "llm_agent",
        "--tasks",
        task_spec,
        "--tasks-file",
        str(tasks_file),
        "--base-url",
        f"http://127.0.0.1:{port}",
        "--submissions",
        str(submissions),
        "--runs-out",
        str(runs_out),
        "--summary-out",
        str(summary_out),
        "--failures-out",
        str(failures_out),
        "--screenshot-dir",
        str(screenshot_dir),
        "--max-steps",
        str(args.max_steps),
        "--max-output-tokens",
        str(effective_max_output_tokens(model_key, args)),
        "--temperature",
        str(args.temperature),
        "--top-p",
        str(args.top_p),
        "--seed",
        str(args.seed),
    ]
    env = os.environ.copy()
    env.update(effective_model_env(model_key, args))
    if args.extra_system_prompt:
        env["WEB_AGENT_EXTRA_SYSTEM_PROMPT"] = args.extra_system_prompt
        cmd.extend(["--extra-system-prompt", args.extra_system_prompt])
    if args.policy_middleware:
        env["WEB_AGENT_POLICY_MIDDLEWARE"] = args.policy_middleware
    print(f"[pair] {model_key}/{benchmark}/{scenario_name}: {task_spec}")
    completed = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        env=env,
        check=False,
        text=True,
        capture_output=True,
    )
    (scenario_dir / "stdout.log").write_text(completed.stdout or "", encoding="utf-8")
    (scenario_dir / "stderr.log").write_text(completed.stderr or "", encoding="utf-8")
    if completed.stdout:
        print(completed.stdout, end="" if completed.stdout.endswith("\n") else "\n")
    if completed.stderr:
        print(completed.stderr, file=sys.stderr, end="" if completed.stderr.endswith("\n") else "\n")
    rows = read_jsonl(runs_out)
    if completed.returncode != 0 and not rows:
        raise RuntimeError(
            f"{model_key}/{benchmark}/{scenario_name} failed before writing rows. "
            f"See {scenario_dir / 'stderr.log'}"
        )
    return [
        enrich_row(
            row,
            benchmark=benchmark,
            scenario_name=scenario_name,
            model_key=model_key,
            model_metadata=model_metadata,
            record_dir=record_dir,
            benchmark_version=benchmark_version_for(args, benchmark),
        )
        for row in rows
    ]


def write_group_readme(record_dir: Path, *, benchmark: str, model_key: str, profile: str, args: argparse.Namespace, model_metadata: dict[str, Any]) -> None:
    record_dir.mkdir(parents=True, exist_ok=True)
    (record_dir / "README.md").write_text(
        f"# {model_key} {benchmark} Evaluation Record\n\n"
        "This directory contains one browser-agent benchmark run with full per-task traces.\n\n"
        f"- Generated at: `{utc_now()}`\n"
        f"- Benchmark: `{benchmark}`\n"
        f"- Profile: `{profile}`\n"
        f"- Model: `{model_metadata}`\n"
        f"- Max steps: `{args.max_steps}`\n"
        f"- Screenshots: `screenshots/<scenario>/<slug>/step_XX.png`\n"
        f"- Runs: `runs.jsonl`\n"
        f"- Summary: `summary.md`\n"
        f"- Failures: `failures.jsonl`\n"
        f"- Transient failures: `transient_failures.jsonl`\n",
        encoding="utf-8",
    )


def run_group(model_key: str, benchmark: str, args: argparse.Namespace) -> list[dict[str, Any]]:
    model_metadata = model_metadata_for(model_key, args)
    record_dir = args.record_root / record_slug_for(model_key, args) / benchmark
    record_dir.mkdir(parents=True, exist_ok=True)
    for filename in ["runs.jsonl", "summary.md", "failures.jsonl", "transient_failures.jsonl", "run_config.json"]:
        path = record_dir / filename
        if path.exists():
            path.unlink()
    rows: list[dict[str, Any]] = []
    for scenario_name in args.scenario_list:
        rows.extend(
            run_scenario(
                benchmark=benchmark,
                scenario_name=scenario_name,
                model_key=model_key,
                record_dir=record_dir,
                profile=args.profile,
                args=args,
                model_metadata=model_metadata,
            )
        )
    write_jsonl(record_dir / "runs.jsonl", rows)
    failures = [row for row in rows if row.get("outcome") != "success"]
    transient = [row for row in failures if is_transient_model_failure(row)]
    write_jsonl(record_dir / "failures.jsonl", failures)
    write_jsonl(record_dir / "transient_failures.jsonl", transient)
    write_summary(
        record_dir / "summary.md",
        rows,
        benchmark=benchmark,
        model_key=model_key,
        profile=args.profile,
        scenarios=args.scenario_list,
    )
    run_config = {
        "generated_at": utc_now(),
        "benchmark": benchmark,
        "profile": args.profile,
        "model_key": model_key,
        "model_metadata": model_metadata,
        "max_steps": args.max_steps,
        "decoding_config": {"temperature": args.temperature, "top_p": args.top_p, "seed": args.seed},
        "task_files": {
            scenario_name: str((benchmark_root(args, benchmark) / SCENARIOS[scenario_name]["tasks_file"]).resolve().relative_to(REPO_ROOT))
            for scenario_name in args.scenario_list
        },
        "benchmark_version": benchmark_version_for(args, benchmark),
        "scenarios": args.scenario_list,
        "task_overrides": args.task_overrides,
        "extra_system_prompt": args.extra_system_prompt,
        "record_slug_suffix": args.record_slug_suffix,
    }
    (record_dir / "run_config.json").write_text(json.dumps(run_config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_group_readme(record_dir, benchmark=benchmark, model_key=model_key, profile=args.profile, args=args, model_metadata=model_metadata)
    print(f"[pair] wrote {record_dir / 'runs.jsonl'}")
    return rows


def pair_category(official: dict[str, Any] | None, clean: dict[str, Any] | None) -> str:
    official_success = bool(official and official.get("outcome") == "success")
    clean_success = bool(clean and clean.get("outcome") == "success")
    if official_success and clean_success:
        return "official_success_clean_success"
    if (not official_success) and clean_success:
        return "official_misleading_clean_success"
    if official_success and not clean_success:
        return "clean_regression"
    return "both_failed"


def write_pair_summary(all_rows: list[dict[str, Any]], *, record_root: Path) -> None:
    by_key: dict[tuple[str, str, str, str], dict[str, dict[str, Any]]] = {}
    for row in all_rows:
        key = (str(row.get("model_key")), str(row.get("scenario")), str(row.get("slug")), str(row.get("task_id")))
        by_key.setdefault(key, {})[str(row.get("benchmark"))] = row
    paired_rows: list[dict[str, Any]] = []
    for (model_key, scenario, slug, task_id), pair in sorted(by_key.items()):
        official = pair.get("official")
        clean = pair.get("clean")
        paired_rows.append(
            {
                "model_key": model_key,
                "scenario": scenario,
                "slug": slug,
                "task_id": task_id,
                "official_outcome": official.get("outcome") if official else None,
                "clean_outcome": clean.get("outcome") if clean else None,
                "official_selected_action_label": official.get("selected_action_label") if official else None,
                "clean_selected_action_label": clean.get("selected_action_label") if clean else None,
                "pair_category": pair_category(official, clean),
            }
        )
    write_jsonl(record_root / "paired_results.jsonl", paired_rows)
    lines = [
        "# Official/Clean Pair Evaluation Summary",
        "",
        f"- Generated at: `{utc_now()}`",
        f"- Paired rows: `{len(paired_rows)}`",
        "",
    ]
    for model_key in sorted({row["model_key"] for row in paired_rows}):
        subset = [row for row in paired_rows if row["model_key"] == model_key]
        official_success = sum(1 for row in subset if row.get("official_outcome") == "success")
        clean_success = sum(1 for row in subset if row.get("clean_outcome") == "success")
        counts = Counter(row["pair_category"] for row in subset)
        total = len(subset)
        lines.extend(
            [
                f"## {model_key}",
                "",
                f"- Official success rate: `{official_success}/{total} ({(official_success / total if total else 0):.2%})`",
                f"- Clean success rate: `{clean_success}/{total} ({(clean_success / total if total else 0):.2%})`",
                f"- Clean minus official success rate: `{((clean_success - official_success) / total if total else 0):.2%}`",
                f"- Pair categories: `{dict(counts)}`",
                "",
                "| Category | Count |",
                "|---|---:|",
            ]
        )
        for category, count in sorted(counts.items()):
            lines.append(f"| {category} | {count} |")
        lines.append("")
    (record_root / "pair_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate_clean_eval_pages(args: argparse.Namespace) -> None:
    # The shell apps default to eval mode. This check guards against accidentally
    # launching clean pages with reviewer-only UI in future runner changes.
    clean_root = benchmark_root(args, "clean")
    for scenario_name, meta in SCENARIOS.items():
        if count_jsonl(clean_root / meta["tasks_file"]) != int(meta["task_count"]):
            raise RuntimeError(f"Clean task count validation failed for {scenario_name}")


def run(args: argparse.Namespace) -> int:
    args.record_root.mkdir(parents=True, exist_ok=True)
    args.task_overrides = parse_task_overrides(args.task_overrides)
    if args.scenarios:
        args.scenario_list = parse_scenarios(args.scenarios)
    elif args.task_overrides:
        args.scenario_list = [name for name in SCENARIO_ORDER if name in args.task_overrides]
    else:
        args.scenario_list = parse_scenarios(args.scenarios)
    benchmarks = benchmark_choices(args.benchmark)
    models = model_choices(args.models)
    for benchmark in benchmarks:
        validate_task_files(benchmark, args)
    if "clean" in benchmarks:
        validate_clean_eval_pages(args)
    all_rows: list[dict[str, Any]] = []
    for model_key in models:
        server = ensure_local_model_server(model_key)
        try:
            for benchmark in benchmarks:
                all_rows.extend(run_group(model_key, benchmark, args))
        finally:
            server.stop()
    if set(benchmarks) == {"official", "clean"}:
        write_pair_summary(all_rows, record_root=args.record_root)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", choices=["official", "clean", "both"], default="both")
    parser.add_argument(
        "--models",
        default="gpt54,kimik26",
        help=(
            "Comma-separated model presets: gpt54,kimik26,kimi_k2_6_aime_litellm,"
            "kimi_k2_6_vip_litellm,"
            "gpt55_litellm,gpt56_sol_litellm,gemini3pro_image_preview,"
            "gemini31pro_preview,gemini31flash_image_preview,qwen35plus_litellm,qwen36plus_litellm,"
            "claude_haiku_4_5_litellm,claude_sonnet_4_6_litellm,claude_opus_4_6_litellm,"
            "claude_opus_4_6_aime_litellm,claude_opus_4_6_aime_uuid_slow,"
            "claude_sonnet_4_6_aime_responses,"
            "claude_opus_4_6_aime_responses,claude_opus_4_7_aime_responses,"
            "claude_opus_4_8_aime_messages,"
            "qwen3vl32b,llama32vision90b"
        ),
    )
    parser.add_argument("--profile", choices=["dryrun", "full"], default="dryrun")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--top-p", dest="top_p", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=12345)
    parser.add_argument("--max-steps", type=int, default=10)
    parser.add_argument(
        "--model-max-output-tokens",
        type=int,
        help="Optional per-model max output token override for scenario runners.",
    )
    parser.add_argument(
        "--aime-max-retries",
        type=int,
        help="Optional AIME LiteLLM max retry override.",
    )
    parser.add_argument(
        "--aime-request-delay-sec",
        type=float,
        help="Optional AIME LiteLLM delay between retryable requests.",
    )
    parser.add_argument(
        "--aime-read-timeout-sec",
        type=float,
        help="Optional AIME LiteLLM HTTP read timeout override.",
    )
    parser.add_argument(
        "--aime-extra-body-json",
        help="Optional JSON object to merge into AIME LiteLLM chat completion request bodies.",
    )
    parser.add_argument(
        "--aime-base-url",
        help="Optional AIME LiteLLM base URL override, without trailing /chat/completions.",
    )
    parser.add_argument(
        "--aime-model",
        help="Optional AIME LiteLLM model override.",
    )
    parser.add_argument(
        "--aime-host-header",
        help="Optional AIME LiteLLM Host header override. Use an empty string to clear it.",
    )
    parser.add_argument(
        "--aime-verify-ssl",
        choices=["true", "false"],
        help="Optional AIME LiteLLM SSL verification override.",
    )
    parser.add_argument(
        "--aime-api-style",
        choices=["chat_completions", "responses", "messages"],
        help="Optional AIME LiteLLM API style override.",
    )
    parser.add_argument(
        "--aime-proxy",
        help="Optional explicit AIME LiteLLM proxy URL, e.g. http://127.0.0.1:18889.",
    )
    parser.add_argument(
        "--experiment-variant",
        help="Optional experiment variant label recorded in model metadata.",
    )
    parser.add_argument(
        "--thinking-budget-supported",
        choices=["true", "false", "unknown"],
        help="Optional thinking-budget support marker recorded in model metadata.",
    )
    parser.add_argument("--scenarios", help="Optional comma-separated subset, e.g. environment35")
    parser.add_argument(
        "--task-overrides",
        help="Optional semicolon-separated scenario task specs, e.g. environment35=env032",
    )
    parser.add_argument(
        "--extra-system-prompt",
        help="Optional prompt text appended to the scenario runner system prompt.",
    )
    parser.add_argument(
        "--record-slug-suffix",
        default="",
        help="Optional suffix appended to each model record slug, e.g. _prompt_generic_warning.",
    )
    parser.add_argument(
        "--policy-middleware",
        help="Optional policy middleware enabled in scenario runners, e.g. chart_evidence_action_guard.",
    )
    parser.add_argument(
        "--port-offset",
        type=int,
        default=0,
        help="Optional offset added to scenario shell ports to avoid concurrent runner collisions.",
    )
    parser.add_argument("--record-root", type=Path, default=RECORD_ROOT)
    parser.add_argument(
        "--official-root",
        type=Path,
        help="Optional official task root override, e.g. benchmark_v2_open/splits/official140.",
    )
    parser.add_argument(
        "--clean-root",
        type=Path,
        help="Optional clean task root override, e.g. benchmark_v2_open/splits/clean140.",
    )
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
