

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

