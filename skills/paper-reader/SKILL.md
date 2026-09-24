---
name: paper-reader
description: Systematically read and analyze academic papers, producing structured Chinese notes (one-line summary, problem, method, contributions, experiments, limitations, relation to prior work) and answering follow-up questions. Use when the user asks to read, summarize, explain, or critique a research paper. Do not use for non-academic text or generic document summaries.
---

# 论文阅读助手 (Paper Reader)

用一套固定流程帮助用户阅读、理解、批判学术论文。默认用中文输出，关键术语保留英文原文（括号标注）。

## 流程

### 1. 获取论文内容

先判断用户提供了什么：

- **PDF 文件路径**：提取文本。按顺序尝试环境里可用的工具：`pdftotext`、Python（`pypdf` 或 `PyMuPDF`/`fitz`）、或其他 PDF 工具。都不可用时，请用户粘贴文本或提供可访问的版本。
- **网址 / DOI / arXiv 号 / 标题**：抓取元数据和摘要。全文可公开获取时读取全文；受付费墙限制时基于摘要分析，并明确告诉用户「本次仅基于摘要」。
- **直接粘贴的文本**：直接使用。

内容较长时，先定位摘要、引言、方法、实验、结论等关键部分再作答；不要跳过方法与实验。

### 2. 判断阅读模式

- **速读**：快速概览。给出一句话总结 + 一段简短说明。
- **精读（默认）**：输出下方完整笔记模板。
- **批判阅读**：精读笔记 + 按 [references/critical-reading.md](references/critical-reading.md) 的清单逐项评估。
- **问答**：用户针对某个具体部分（公式、图表、术语、实验）提问。精确回答，并指出出自哪一节。
- **对比**：多篇论文。给出对比表格 + 每篇短摘要。

模式不明显时默认精读，并简短提示其它模式。

### 3. 输出结构化笔记

精读时使用以下模板，每节保持简洁，贴合用户的理解水平：

1. **一句话总结** —— 一句话说清：解决什么问题、用了什么方法、得到什么结果。
2. **研究问题与动机** —— 要解决的问题及其重要性。
3. **方法 / 核心思路** —— 关键想法与技术路线；对不直观的部分加以解释。
4. **主要贡献** —— 简洁列出新意之处。
5. **实验与结论** —— 实验设置、关键结果，以及结果是否支撑论点。
6. **局限与不足** —— 作者自己声明的局限，加上你注意到的（如基线偏弱、评估面窄、假设过强）。
7. **与相关工作的关系** —— 与前人工作的区别与继承关系。
8. **关键术语**（仅在有用时）—— 解释不熟悉的术语。
9. **值得跟进**（可选）—— 开放问题、复现要点、后续论文。

### 4. 主动提供保存笔记

展示笔记后，主动询问是否保存为 Markdown 文件（例如工作目录下 `notes/<论文简称>.md`）。未经用户同意不要写文件。

## 约束

- 明确区分「作者声称」与「我的评估」，关键处分别标注。
- 仅基于摘要分析时，必须说明，且不得臆造方法或结果。
- 不得编造引用或数据；不确定就明说。
- 关键术语保留英文原文，与中文对照。

## 参考

- 批判阅读清单见 [references/critical-reading.md](references/critical-reading.md)。
