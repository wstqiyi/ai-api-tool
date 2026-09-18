# -*- coding: utf-8 -*-
"""
支持任何 OpenAI 兼容接口（DeepSeek / Kimi / 通义 / 豆包 / 智谱 / OpenAI ...），
只要改 LLM_BASE_URL 和 LLM_MODEL 两个环境变量。

用法：
    # Windows PowerShell
    $env:LLM_API_KEY="sk-xxxxxxxx"
    python meeting_to_actions.py sample_meeting.txt
    python meeting_to_actions.py sample_meeting.txt -o actions.json
    python meeting_to_actions.py sample_meeting.txt --dry-run   # 只打印请求，不真的调用
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-chat"
TIMEOUT_SECONDS = 60
MAX_ATTEMPTS = 3
RETRY_STATUS = {429, 500, 502, 503, 504}

SYSTEM_PROMPT = """你是一个会议纪要助理，负责从会议记录中提取行动项。

必须遵守：
1. 只输出 JSON，不要输出任何解释文字，不要使用 markdown 代码块。
2. JSON 结构固定为：
{
  "summary": "一句话说明这场会议在讨论什么",
  "actions": [
    {
      "owner": "负责人姓名，未提到就写 待定",
      "task": "要做的事，动词开头，不超过 30 字",
      "due": "截止时间，未提到就写 待定",
      "priority": "high / medium / low",
      "evidence": "会议记录里支撑这条的原话片段"
    }
  ],
  "risks": ["识别出的风险或悬而未决的问题"]
}
3. 只提取会议记录里真实出现的内容，绝对不要编造人名、时间或任务。
4. 如果没有任何明确行动项，actions 返回空数组。
"""

SCRIPT_DIR = Path(__file__).resolve().parent


# --------------------------------------------------------------------------
# 配置
# --------------------------------------------------------------------------
def load_dotenv(path: Path) -> dict:
    """读取同目录下的 .env，格式为 KEY=VALUE，仅做最简解析。"""
    values: dict = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def resolve_config(args) -> dict:
    dotenv = load_dotenv(SCRIPT_DIR / ".env")

    def pick(key: str, default: str = "") -> str:
        # 环境变量优先于 .env，方便临时切换
        return os.environ.get(key) or dotenv.get(key) or default

    return {
        "api_key": pick("LLM_API_KEY"),
        "base_url": args.base_url or pick("LLM_BASE_URL", DEFAULT_BASE_URL),
        "model": args.model or pick("LLM_MODEL", DEFAULT_MODEL),
        "price_in": float(pick("LLM_PRICE_IN", "0") or 0),
        "price_out": float(pick("LLM_PRICE_OUT", "0") or 0),
    }


# --------------------------------------------------------------------------
# 调用大模型
# --------------------------------------------------------------------------
def build_payload(text: str, model: str) -> dict:
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        "temperature": 0.2,
        "stream": False,
    }


def call_llm(text: str, cfg: dict, dry_run: bool = False) -> tuple:
    """返回 (content, usage, elapsed_seconds)。dry_run 时不发请求。"""
    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    payload = build_payload(text, cfg["model"])
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    if dry_run:
        print("[dry-run] POST", url)
        print("[dry-run] 请求体预览：")
        print(json.dumps(payload, ensure_ascii=False, indent=2)[:600])
        return "", {}, 0.0

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg['api_key']}",
    }

    last_error = "未知错误"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        started = time.time()
        try:
            request = urllib.request.Request(url, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                data = json.loads(response.read().decode("utf-8"))
            elapsed = time.time() - started
            content = data["choices"][0]["message"]["content"]
            return content, data.get("usage") or {}, elapsed

        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "ignore")[:300]
            last_error = f"HTTP {exc.code} {detail}"
            if exc.code in RETRY_STATUS and attempt < MAX_ATTEMPTS:
                wait = 2 ** attempt
                print(f"  [重试 {attempt}/{MAX_ATTEMPTS - 1}] {last_error}，{wait}s 后重试")
                time.sleep(wait)
                continue
            if exc.code == 401:
                raise SystemExit("鉴权失败（401）：请检查 LLM_API_KEY 是否正确、是否已过期。") from exc
            raise SystemExit(f"接口返回错误：{last_error}") from exc

        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = f"网络异常：{exc}"
            if attempt < MAX_ATTEMPTS:
                wait = 2 ** attempt
                print(f"  [重试 {attempt}/{MAX_ATTEMPTS - 1}] {last_error}，{wait}s 后重试")
                time.sleep(wait)
                continue
            raise SystemExit(f"请求失败：{last_error}") from exc

    raise SystemExit(f"请求失败：{last_error}")


# --------------------------------------------------------------------------
# 解析与校验模型返回
# --------------------------------------------------------------------------
def extract_json(text: str) -> dict:
    """模型偶尔会带 ```json 包裹或前后废话，这里做一次容错提取。"""
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        raise SystemExit(f"模型没有返回可解析的 JSON，原文片段：{text[:200]}")
    try:
        return json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise SystemExit(f"JSON 解析失败：{exc}") from exc


def validate(result: dict) -> list:
    """做最低限度的结构校验，避免把残缺结果当成功。"""
    problems = []
    actions = result.get("actions")
    if not isinstance(actions, list):
        return ["actions 字段不是数组，无法逐条校验"]
    for index, item in enumerate(actions, 1):
        if not isinstance(item, dict):
            problems.append(f"第 {index} 条行动项不是对象")
            continue
        for key in ("owner", "task", "due"):
            if not item.get(key):
                problems.append(f"第 {index} 条行动项缺少 {key}")
    return problems


# --------------------------------------------------------------------------
# 输出
# --------------------------------------------------------------------------
def display_width(text: str) -> int:
    """中文按两个字符宽度计算，保证表格对齐。"""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def pad(text: str, width: int) -> str:
    text = str(text)
    return text + " " * max(0, width - display_width(text))


def render(result: dict, usage: dict, elapsed: float, cfg: dict) -> None:
    actions = result.get("actions") or []
    risks = result.get("risks") or []

    print("\n===== 会议主题 =====")
    print(result.get("summary", "（未返回）"))

    print(f"\n===== 行动项 {len(actions)} 条 =====")
    if actions:
        rows = [(a.get("owner", "-"), a.get("task", "-"), a.get("due", "-"), a.get("priority", "-")) for a in actions]
        widths = [max(display_width(r[i]) for r in rows + [("负责人", "任务", "截止时间", "优先级")]) for i in range(4)]
        header = ("负责人", "任务", "截止时间", "优先级")
        print("  ".join(pad(header[i], widths[i]) for i in range(4)))
        print("-" * (sum(widths) + 6))
        for row in rows:
            print("  ".join(pad(row[i], widths[i]) for i in range(4)))
        print("\n支撑原文：")
        for action in actions:
            print(f"  · {action.get('evidence', '（无）')}")
    else:
        print("（没有识别到行动项）")

    if risks:
        print(f"\n===== 风险与待决 {len(risks)} 条 =====")
        for risk in risks:
            print(f"  · {risk}")

    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    print("\n===== 调用信息 =====")
    print(f"  模型        {cfg['model']}")
    print(f"  耗时        {elapsed:.2f}s")
    print(f"  Token 用量  输入 {prompt_tokens} / 输出 {completion_tokens}")
    if cfg["price_in"] or cfg["price_out"]:
        cost = prompt_tokens / 1e6 * cfg["price_in"] + completion_tokens / 1e6 * cfg["price_out"]
        print(f"  预估成本    ¥{cost:.4f}（单价来自 LLM_PRICE_IN / LLM_PRICE_OUT）")


# --------------------------------------------------------------------------
# 入口
# --------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="把会议记录转成结构化行动项（大模型 API 示例工具）")
    parser.add_argument("input", nargs="?", default="sample_meeting.txt", help="会议记录文本文件，默认 sample_meeting.txt")
    parser.add_argument("-o", "--output", default="actions.json", help="结构化结果保存路径，默认 actions.json")
    parser.add_argument("--dry-run", action="store_true", help="只打印将要发送的请求，不真的调用接口")
    parser.add_argument("--base-url", default="", help="覆盖 LLM_BASE_URL")
    parser.add_argument("--model", default="", help="覆盖 LLM_MODEL")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cfg = resolve_config(args)

    source = Path(args.input)
    if not source.is_absolute():
        source = SCRIPT_DIR / source if (SCRIPT_DIR / args.input).exists() else Path.cwd() / args.input
    if not source.exists():
        print(f"找不到输入文件：{source}")
        return 1

    text = source.read_text(encoding="utf-8").strip()
    if not text:
        print("输入文件是空的。")
        return 1

    print(f"输入文件    {source}")
    print(f"字符数      {len(text)}")

    if not cfg["api_key"] and not args.dry_run:
        print("\n还没有配置 LLM_API_KEY。")
        print("PowerShell 里执行：$env:LLM_API_KEY=\"sk-xxxxxxxx\"")
        print("或者把 .env.example 复制成 .env 并填入 Key。")
        return 1

    content, usage, elapsed = call_llm(text, cfg, dry_run=args.dry_run)
    if args.dry_run:
        print("\n[dry-run] 未发送请求。")
        return 0

    result = extract_json(content)
    problems = validate(result)
    if problems:
        print("\n结果结构有问题（仍然会保存，方便你排查）：")
        for problem in problems:
            print(f"  · {problem}")

    render(result, usage, elapsed, cfg)

    target = Path(args.output)
    if not target.is_absolute():
        target = Path.cwd() / target
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结构化结果已保存到 {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
