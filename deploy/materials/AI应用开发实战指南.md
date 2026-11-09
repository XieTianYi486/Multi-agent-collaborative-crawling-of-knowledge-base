# AI 应用开发实战指南：RAG 与 LangChain

> 本文是「视频专区 · AI 应用开发」栏目的配套学习资料，梳理从技术选型、RAG 全链路到评测上线的工程要点，并给出可直接改写的 LangChain 最小示例。

## 一、先选对技术路径

| 方案 | 解决什么问题 | 成本 | 适用场景 |
| --- | --- | --- | --- |
| Prompt 工程 | 模型本身会，只是不会按你的格式输出 | 最低 | 改写、分类、抽取、格式化 |
| RAG（检索增强） | 模型不知道你的私有知识 | 中 | 制度问答、设备手册、课程资料 |
| 微调（Fine-tune） | 需要固定风格、固定任务或领域表达 | 高 | 专业术语风格、结构化生成 |

判断顺序：先问"知识在不在模型里"，不在就用 RAG；再问"行为是否要固化"，需要固化才考虑微调。绝大多数教学知识库场景，RAG 已经够用。

## 二、RAG 全链路拆解

```
文档解析 → 清洗 → 分块 → 向量化 → 建索引
                                  ↓
用户提问 → 查询改写 → 混合召回 → 重排 → 组装 Prompt → 生成 → 引用溯源
```

各环节的常见坑：

1. **解析**：PDF 扫描件没有文本层，需要 OCR；表格直接转文本会错行，最好保留结构。
2. **清洗**：页眉页脚、导航栏、广告、重复段落都要去掉，否则会污染检索结果。
3. **分块**：块太大检索不精准，块太小丢上下文。优先按标题层级切，再按长度兜底。
4. **向量化**：同一个知识库必须使用同一嵌入模型与维度，换模型需要全量重建索引。
5. **召回**：只做向量召回容易漏掉型号、编号等关键词，建议向量 + BM25 混合。
6. **重排**：把融合后的候选交给重排序模型，取前 3~5 条送进 Prompt，可显著降噪。
7. **生成**：Prompt 中明确"只依据资料回答，资料不足就说不知道"。
8. **溯源**：返回来源文档名、章节、页码与原文链接，便于人工核对。

## 三、分块与检索参数建议

| 参数 | 常见取值 | 说明 |
| --- | --- | --- |
| chunk_size | 300~600 token | 中文技术文档 512 左右较稳 |
| chunk_overlap | 30~80 token | 保留跨段语义，避免句子被截断 |
| 向量召回 Top-K | 15~30 | 太小容易漏，太大增加重排负担 |
| BM25 Top-K | 15~30 | 与向量召回取并集后融合 |
| 融合后候选 | 40~60 | 送重排的候选池 |
| 重排后入 Prompt | 3~5 | 控制上下文长度与噪声 |

融合常用 RRF（倒数排名融合）：对两路结果按名次加权，不依赖分数量纲，工程上稳定。

## 四、引用溯源与幻觉抑制

1. 检索结果携带 `document_id`、标题、章节、页码，生成时编号为 `[来源1]`、`[来源2]`。
2. Prompt 明确约束："如果资料中没有答案，请直接说明未找到，不要编造"。
3. 回答末尾固定输出资料参考声明。
4. 对高风险问题（政策、金额、安全操作）要求给出原文片段，便于人工复核。
5. 建立"未命中问题"日志，定期把高频未命中问题补进知识库。

## 五、LangChain 最小示例

以下示例使用 OpenAI 兼容接口（可指向本地 vLLM 或云端服务），完成"检索 + 生成"的最小闭环，实际项目可替换为项目自有的向量库与重排器。

```python
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

# 1. 模型与嵌入：base_url 指向 vLLM / DashScope 等 OpenAI 兼容服务
llm = ChatOpenAI(
    model="qwen-rag",
    base_url="http://localhost:8000/v1",
    api_key="EMPTY",
    temperature=0.1,
    max_tokens=768,
)
embeddings = OpenAIEmbeddings(
    model="text-embedding-v2",
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

# 2. 建索引：真实项目中由文档解析与分块流水线产出 chunks
chunks = ["ESP32 默认日志波特率为 115200。", "ESP-IDF 使用 idf.py build 构建工程。"]
vectorstore = FAISS.from_texts(chunks, embeddings)
retriever = vectorstore.as_retriever(search_kwargs={"k": 4})

# 3. Prompt：要求只依据资料回答并给出引用
prompt = ChatPromptTemplate.from_messages([
    ("system", "你是教学知识库助手。只依据【资料】回答；资料不足时回答“资料中未找到相关内容”。"),
    ("human", "【资料】\n{context}\n\n【问题】\n{question}"),
])

def format_docs(docs):
    return "\n\n".join(f"[来源{i + 1}] {d.page_content}" for i, d in enumerate(docs))

chain = (
    {"context": retriever | format_docs, "question": RunnablePassthrough()}
    | prompt
    | llm
    | StrOutputParser()
)

print(chain.invoke("ESP32 的日志波特率是多少？"))
```

工程化时需要注意：

1. 检索与生成分开埋点，分别记录耗时，便于定位慢在哪一步。
2. 流式输出（SSE）提升首字体验，但引用来源要等检索完成后一次性返回。
3. 对检索结果做密级过滤，避免越权内容进入上下文。
4. 缓存高频问题的答案，但要带版本号，知识库更新后失效。

## 六、怎么判断做得好不好

1. **建评测集**：准备 50~100 条真实问题，覆盖常见问法、同义改写、无答案问题。
2. **看召回**：Recall@K 是否把正确片段召回；有标准答案的题目可人工标注。
3. **看回答**：答案正确率、引用是否正确、是否出现编造。
4. **看拒答**：无答案问题是否稳定回答"未找到"，而不是硬编。
5. **看性能**：首字延迟、总耗时、单次成本。
6. **线上闭环**：用户点赞/点踩、未命中日志、人工抽检。

## 七、上线检查清单

- [ ] 文档解析、分块、向量维度三者一致，重建索引有脚本可复现
- [ ] 向量检索与 BM25 均可用，融合与重排参数经过评测确定
- [ ] Prompt 含拒答约束与引用格式要求
- [ ] 来源信息完整（文档名、章节、页码、原文链接）
- [ ] 密级与角色权限过滤在检索层生效
- [ ] 问答日志、耗时、来源、反馈均已记录
- [ ] 密钥通过环境变量注入，不写入代码仓库

## 八、配套视频清单

- 2026版 LangChain 教程，快速入门、Agent 智能体与 RAG 项目实战：<https://www.bilibili.com/video/BV1rv7A6oEeP>
- RAG 工作机制详解——一个高质量知识库背后的技术全流程：<https://www.bilibili.com/video/BV1JLN2z4EZQ>
- RAG 知识库搭建系统教程，手把手搭建私有知识库：<https://www.bilibili.com/video/BV1otokBpENn>

> 视频版权归 B 站原作者所有，本站仅做教学索引。
