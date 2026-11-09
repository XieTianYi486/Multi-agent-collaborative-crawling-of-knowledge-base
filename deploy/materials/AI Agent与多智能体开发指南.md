# AI Agent 与多智能体开发指南

> 本文是「视频专区 · AI Agent」栏目的配套学习资料，从单个 Agent 的基本构成讲起，到多智能体架构模式、通信机制、失败模式与落地建议，帮助你在看完视频后能把思路落成可运行的代码。

## 一、Agent 是什么

Agent 可以理解为"让大模型在循环中自主决定下一步动作"的工程结构，通常包含四个部分：

1. **模型（LLM）**：负责理解任务、推理与生成动作。
2. **规划（Planning）**：把目标拆成步骤，决定先做什么后做什么。
3. **工具（Tools）**：搜索、数据库查询、文件读写、代码执行、业务 API。
4. **记忆（Memory）**：短期对话上下文、长期任务状态与历史经验。

与普通问答的区别：普通问答一次生成即结束；Agent 会"想一步 → 调工具 → 看结果 → 再想"，直到完成或达到步数上限。

## 二、工具调用的设计要点

工具是 Agent 能力边界，也是最容易出问题的地方。

| 设计项 | 建议 |
| --- | --- |
| 工具描述 | 用一句话说明"什么时候用"，比参数说明更重要 |
| 参数结构 | 使用严格的 JSON Schema，必填项与枚举写清楚 |
| 幂等性 | 写操作要支持幂等键，避免重试造成重复提交 |
| 超时与重试 | 每个工具单独设置超时，失败返回结构化错误 |
| 权限 | 按用户身份限制可调用工具，危险操作需二次确认 |
| 返回长度 | 工具返回结果做截断与摘要，避免撑爆上下文 |

## 三、单 Agent 的最小循环

```python
import json

def run_agent(llm, tools, user_query, max_steps=8):
    messages = [
        {"role": "system", "content": "你可以调用工具完成任务；信息足够时直接给出最终答案。"},
        {"role": "user", "content": user_query},
    ]
    for step in range(max_steps):
        reply = llm.chat(messages, tools=tools)   # 模型选择直接回答或调用工具
        if reply.tool_call is None:
            return reply.content                 # 没有工具调用即视为完成
        name, args = reply.tool_call["name"], json.loads(reply.tool_call["arguments"])
        if name not in tools:
            messages.append({"role": "tool", "content": f"未知工具: {name}"})
            continue
        try:
            result = tools[name](**args)         # 执行工具
        except Exception as exc:
            result = f"工具执行失败: {exc}"
        messages.append({"role": "assistant", "content": "", "tool_calls": [reply.tool_call]})
        messages.append({"role": "tool", "content": str(result)[:2000]})
    return "已达到最大步数，任务未完成，请缩小问题范围后重试。"
```

关键护栏：

1. 必须设置 `max_steps`，否则模型可能无限调用工具。
2. 工具异常要转成可读文本回填，而不是直接中断整个任务。
3. 工具结果截断到固定长度，防止上下文膨胀。
4. 写操作类工具在执行前做权限校验与确认。

## 四、多智能体的三种常见架构

| 架构 | 结构 | 优点 | 适用场景 |
| --- | --- | --- | --- |
| 顺序式（Sequential） | A 的输出交给 B，再交给 C | 简单、可预测、易调试 | 固定流程：检索 → 撰写 → 审核 |
| 层级式（Hierarchical） | 主管 Agent 拆解任务并分派给子 Agent | 分工清晰、适合复杂任务 | 报告生成、跨系统任务编排 |
| 协作式（Collaborative） | 多个 Agent 共享状态、互相评审 | 质量高、可交叉验证 | 方案评审、复杂推理、内容校对 |

落地建议：

1. 优先顺序式。大多数业务用"检索 Agent → 生成 Agent → 校验 Agent"就能解决。
2. 只有任务确实需要动态分工时才上层级式，编排复杂度会明显上升。
3. 协作式适合对质量要求高的场景，但要控制轮次与成本，避免"互相客气"式空转。

## 五、通信与状态管理

多智能体最容易失控的地方是状态。推荐做法：

1. **结构化消息**：Agent 之间传递 JSON，字段包含 `task`、`context`、`result`、`status`、`citations`。
2. **共享黑板**：用一个任务状态对象记录已完成步骤、中间产物与待办，所有 Agent 读写同一份状态。
3. **消息总线**：解耦 Agent，便于替换与单独测试；但要定义好消息顺序与超时。
4. **上下文隔离**：子 Agent 只接收与自身任务相关的上下文，不要把全量历史传给每个 Agent。

## 六、典型失败模式与应对

| 失败模式 | 表现 | 应对 |
| --- | --- | --- |
| 死循环 | 反复调用同一工具 | 步数上限、重复调用检测、连续失败退出 |
| 工具幻觉 | 调用不存在的工具或编造参数 | 工具白名单、参数校验、错误回填 |
| 上下文膨胀 | 越到后面越慢、越容易跑偏 | 工具结果截断、历史摘要、状态外置 |
| 成本失控 | token 消耗远超预算 | 每任务预算上限、缓存、模型分级 |
| 责任不清 | 多 Agent 互相等待或重复劳动 | 明确角色与交接条件，状态机驱动 |
| 越权操作 | 调用了不该调用的工具 | 工具级权限、危险操作二次确认 |

## 七、可观测性与评测

1. **Trace**：记录每次 Agent 的输入、模型输出、工具调用、耗时与 token 消耗。
2. **步骤日志**：按任务 ID 串联多个 Agent 的步骤，便于回放。
3. **成功率与步数**：统计任务完成率、平均步数、工具失败率。
4. **成本看板**：按任务、按 Agent 统计调用成本。
5. **回归评测**：固定一批任务作为基准，每次改 Prompt 或工具后重跑。

## 八、最小多智能体示例（顺序式）

```python
def sequential_pipeline(query):
    research = research_agent.run(f"检索与问题相关的资料：{query}")      # 只负责找资料
    draft = writer_agent.run(f"基于资料撰写回答：\n{research}")          # 只负责写
    review = reviewer_agent.run(f"检查回答是否忠于资料，指出问题：\n{draft}")  # 只负责审
    if "通过" not in review:
        draft = writer_agent.run(f"按审核意见修订：\n{review}\n原文：\n{draft}")
    return {"answer": draft, "review": review, "sources": research.get("sources", [])}
```

这个结构的价值在于职责单一、每一步都可单独测试，出问题时很容易定位是检索、写作还是审核环节。

## 九、落地建议

1. 先用单 Agent 把流程跑通，确认 Prompt 与工具稳定，再拆多 Agent。
2. 每个 Agent 只暴露必要的工具，权限最小化。
3. 所有 Agent 输出都要求结构化，避免下游靠自然语言猜。
4. 给每个任务设置步数与成本上限，超限则优雅失败并提示用户。
5. 保留人工兜底入口：Agent 失败时转工单或转人工。

## 十、配套视频清单

- 挑战 12 分钟搞定，多智能体（Multi-Agent）架构：<https://www.bilibili.com/video/BV11p6wB2EmX>
- 【Google Cloud 官方】3 种多智能体架构模式全解析：<https://www.bilibili.com/video/BV18m4p6XEDy>
- 从零实现自己的 Agent 第十一期：多 Agent 协作：<https://www.bilibili.com/video/BV1VqHM6iEXn>

> 视频版权归 B 站原作者所有，本站仅做教学索引。
