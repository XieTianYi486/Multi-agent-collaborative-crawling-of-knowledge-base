# 评测集与实验（毕业论文第 6 章数据源）

本目录包含劳动用工合规问答系统的评测数据集与评测脚本，用于毕业论文的实验章节。

## 文件说明

| 文件 | 说明 |
|---|---|
| `qa_dataset.json` | 74 道评测题：工时休假 12、工资社保 12、劳动合同 10、解雇保护 10、工伤 4、争议处理 6、企业制度 6（密级2）、案例咨询 4（密级3）、拒答无关 6、多轮指代 4 |
| `run_eval.py` | 评测脚本：检索质量（Recall/MRR/nDCG）+ 端到端（LLM 判分/引用正确率/拒答统计） |
| `results/` | 评测结果 JSON 输出（自动生成，已 gitignore） |

## 黄金标注方法

黄金 chunk 不存 chunk_id（数据重灌后 ID 会变化），采用运行时判定：

- `doc`：文档名精确匹配
- `chapter`（可选）：章节名子串匹配
- `must_contain`（可选）：chunk 正文必须包含全部子串（通常为"第X条 + 关键短语"）

## 分级运行

| 级别 | 前置条件 | 命令 | 产出 |
|---|---|---|---|
| L1 检索（离线） | 无（seed 完成即可） | `python eval/run_eval.py --retrievers bm25` | BM25 的 HitRate/Recall/MRR/nDCG |
| L2 全配置对比 | DASHSCOPE_API_KEY | `python eval/run_eval.py --retrievers all` | 五配置对比：BM25 / Dense / Hybrid / +Rerank / +Rewrite |
| L3 端到端 | DASHSCOPE_API_KEY | `python eval/run_eval.py --mode e2e --sample-size 40` | 答案正确率（LLM judge 0~2 分）、法条引用正确率 exact/partial、拒答准确率、平均延迟 |

> 注意：向量/混合检索依赖 embedding API 调用（非 LLM），所以"无 Key 可跑检索评估"严格指 BM25 一路；e2e 建议抽样 30~40 题控制配额。

## 实验矩阵（论文第 6 章表格）

1. **检索对比实验**：BM25 vs Dense vs Hybrid vs Hybrid+Rerank vs Hybrid+Rerank+Rewrite，指标 HitRate@5、Recall@5/10、MRR@10、nDCG@10
2. **消融实验**：重排开关（Hybrid vs Hybrid+Rerank）、查询改写开关（Hybrid+Rerank vs Hybrid+Rerank+Rewrite，重点看"多轮指代"子集）
3. **密级过滤实验**：同一批题分别以 `--security-level 1` 与 `--security-level 3` 运行，验证"案例咨询/企业制度"题仅在高密级可召回
4. **端到端评测**：LLM judge 答案正确率、法条引用正确率（exact=引用集合与标准完全一致 / partial=至少命中一条）、拒答准确率（应拒答题的拒答率 + 正常题的误拒率）

## 数据集维护

- 法规题目的 `must_contain` 以官方文本为准；若更换语料后某题 Recall 恒为 0，先检查语料中该条文是否缺失或措辞差异，再修正标注。
- 新增题目时遵守 `tests/test_eval_dataset.py` 的 schema 校验。
