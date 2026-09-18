# 会议记录转行动项工具

把一段会议记录丢给大模型，输出结构化的行动项清单（负责人 / 任务 / 截止时间 / 优先级 / 支撑原文）和风险列表。

**零第三方依赖，只用 Python 标准库。** 不需要 pip install，配好 Key 就能跑。

---

## 为什么选这个场景

它一次性覆盖了「能读懂 API 文档、跑通 Demo、做简单开发」这条加分项的全部要点：

- 会读 API 文档：请求体、鉴权头、超时、限流错误码、token 用量字段
- 会做结构化输出：让模型稳定返回 JSON，并做容错解析和字段校验
- 会做工程兜底：失败重试、超时控制、错误提示、dry-run 调试
- 有真实价值：会议纪要是每个团队都有的高频痛点，面试官一秒能听懂

---

## 目录结构

```
ai-api-tool/
├── meeting_to_actions.py   主程序
├── sample_meeting.txt      示例会议记录
├── .env.example            配置模板，复制成 .env 使用
└── README.md
```

---

## 快速开始

**第 1 步**，配置 Key。二选一：

```powershell
# 方式一：临时环境变量
$env:LLM_API_KEY="sk-xxxxxxxx"
```

```powershell
# 方式二：复制 .env.example 为 .env，填好 Key（推荐，不用每次设）
Copy-Item .env.example .env
```

**第 2 步**，先 dry-run 看一眼将要发送的请求，确认没问题：

```powershell
python meeting_to_actions.py sample_meeting.txt --dry-run
```

**第 3 步**，正式运行，结果会同时打印到终端并存成 JSON：

```powershell
python meeting_to_actions.py sample_meeting.txt -o actions.json
```

换成自己的会议记录：

```powershell
python meeting_to_actions.py 我的会议.txt -o 我的行动项.json
```

---

## 常用参数

| 参数 | 说明 |
|---|---|
| `input` | 会议记录文本文件，默认 `sample_meeting.txt` |
| `-o, --output` | 结构化结果保存路径，默认 `actions.json` |
| `--dry-run` | 只打印将要发送的请求，不真的调用接口 |
| `--base-url` | 临时覆盖 `LLM_BASE_URL` |
| `--model` | 临时覆盖 `LLM_MODEL` |

---

## 支持的模型

任何 OpenAI 兼容接口都能直接用，改两个环境变量即可。常见平台：

| 平台 | LLM_BASE_URL |
|---|---|
| DeepSeek | `https://api.deepseek.com/v1` |
| 阿里通义（兼容模式） | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| 月之暗面 Kimi | `https://api.moonshot.cn/v1` |
| 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4` |
| 火山方舟（豆包） | `https://ark.cn-beijing.volces.com/api/v3` |
| OpenAI | `https://api.openai.com/v1` |

具体模型名称和计费单价请以各家官方文档为准。

---

## 输出示例

终端会打印这样的表格（示意，实际内容以模型返回为准）：

```
===== 会议主题 =====
对齐会员续费活动的优化方案，重点解决新用户首月流失问题。

===== 行动项 5 条 =====
负责人  任务                        截止时间   优先级
--------------------------------------------------------
王茜    输出新手任务引导方案          9月25日前  high
陈默    排查新手任务埋点覆盖情况      本周五     high
李珊    完成新手引导页面改版          待定       medium
张磊    确定引导页的放置位置          周三前     medium
王茜    每周五输出续费率周报          每周五     medium

支撑原文：
  · 我建议做一个新手任务引导，先把首月激活率提上来。这个方案我在 9 月 25 号之前可以写出来。

===== 风险与待决 1 条 =====
  · 测试环境只有一套，活动和引导改版可能抢资源，需要提前排期

===== 调用信息 =====
  模型        deepseek-chat
  耗时        4.21s
  Token 用量  输入 512 / 输出 386
```

同时生成 `actions.json`，结构固定，方便直接接到飞书多维表格或任务系统：

```json
{
  "summary": "对齐会员续费活动的优化方案",
  "actions": [
    {
      "owner": "王茜",
      "task": "输出新手任务引导方案",
      "due": "9月25日前",
      "priority": "high",
      "evidence": "我建议做一个新手任务引导……"
    }
  ],
  "risks": ["测试环境只有一套，活动和引导改版可能抢资源"]
}
```

---

## 设计要点

**结构化输出**　System Prompt 里把 JSON 结构写死，并明确要求「只输出 JSON、不要 markdown 代码块、不要编造」。同时用 `extract_json()` 做容错，即使模型加了 ```json 包裹或前后废话也能正确提取。

**结果校验**　`validate()` 会检查 actions 是否为空数组、每条是否缺字段。校验不过时打印问题清单但仍然保存结果，方便对比排查，而不是直接抛异常。

**失败重试**　遇到 429、5xx 或网络异常时指数退避重试，最多 3 次。401 直接给出「Key 可能无效或过期」的明确提示，不重试。

**可观测**　每次调用都打印耗时、输入输出 token 数和预估成本。单价通过环境变量配置，换成自己的模型时改两个数字即可。

**可调试**　`--dry-run` 不发请求只打印请求体，调 Prompt 时不用反复烧 token。

---

## 面试怎么讲这一条

一句话版本：

> 做了一个会议记录转行动项的小工具，调用大模型 API 做结构化输出，支持 DeepSeek / Kimi / 通义等多家兼容接口，零依赖只用标准库，内置重试、超时、结果校验和 token 成本统计，实测把一份 40 分钟会议的整理时间从 15 分钟压到 10 秒。

可能的追问和准备好的答案：

| 追问 | 回答要点 |
|---|---|
| 模型返回的不是合法 JSON 怎么办 | 三层兜底：Prompt 约束 → 正则剥离代码块 → 截取首尾大括号重新解析；再看校验结果决定是否重试 |
| 怎么防止模型编造内容 | Prompt 里要求每条行动项必须附会议原话作为 evidence，并在校验环节检查；宁可返回空数组 |
| 长会议记录超出上下文怎么办 | 当前版本限定了输入长度，扩展方向是先分段抽取再聚合去重 |
| 成本是多少 | 一次典型调用约 900 token，按配置的单价直接算出单次成本 |

---

## 可以继续做的扩展

1. 接飞书多维表格 API，把结果直接写入任务表，形成完整闭环
2. 加一个简单的网页界面（Streamlit 或纯 HTML + FastAPI）
3. 做成批量模式，一次处理整个文件夹的历史会议记录
4. 加评测集：准备 20 份会议记录，人工标注正确答案，统计行动项召回率
