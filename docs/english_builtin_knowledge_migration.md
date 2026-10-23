# 内置知识库英文化与双语检索改造说明

## 1. 目标

对以下三个检索工具涉及的内置知识库进行英文化改造：

- `search_competition_rules`
- `search_best_practice`
- `search_sales_scripts`

改造完成后必须满足：

1. 本地 Markdown 正文、标题和数据库中的 `DocumentChunk.content`、章节元数据及 embedding 对应内容全部为英文。
2. 用户仍可使用中文或英文查询；两种语言应命中同一份英文知识内容。
3. Markdown 结构、业务含义、数值、日期、门槛、竞赛代码和文件名保持不变。
4. `keyword` 与 `vector` 两种检索模式均可正常工作。
5. 数据库中不得残留旧的中文 chunk 或旧 embedding。

## 2. 文件范围

需翻译以下文件，文件名不得修改：

```text
data/knowledge/sales_scripts.md
data/knowledge/best_practices.md
data/knowledge/competition_*.md
data/knowledge/mdrt_rules.md
data/knowledge/cot_rules.md
data/knowledge/competitions/*.md
```

翻译时必须保持：

- Markdown 标题层级及 `#`、`##` 等标记；
- 表格结构、列数及字段对应关系；
- 列表层级和内容顺序；
- 数字、金额、百分比、日期、期限和资格门槛；
- `AG25035` 等竞赛或公告代码；
- 文件名及目录结构。

`best_practices.md` 和 `sales_scripts.md` 当前通过 `content.split("\n## ")` 切分章节，因此二级标题必须继续采用标准的 `## Title` 格式。

## 3. 双语关键词改造

### 3.1 竞赛规则

修改 `COMP_FILE_MAP`：

- 保留现有中文查询别名；
- 增加对应英文别名；
- 中英文别名指向同一组、文件名不变的英文 Markdown。

示例：

```python
COMP_FILE_MAP = {
    "mdrt": ["competitions/AG25035.md", "mdrt_rules.md"],
    "million dollar round table": ["competitions/AG25035.md", "mdrt_rules.md"],
    "百萬圓桌": ["competitions/AG25035.md", "mdrt_rules.md"],
}
```

### 3.2 最佳实践与销售话术

不要再用同一组关键词同时匹配“用户查询”和“英文文档内容”。应将两者拆分：

```python
TOPIC_RULES = {
    "average_case_size": {
        "query_aliases": [
            "件均", "保費偏低", "case size", "average premium",
        ],
        "document_terms": [
            "average case size", "average premium", "premium per policy",
        ],
    },
}
```

匹配流程应为：

1. 使用中英文 `query_aliases` 判断用户意图；
2. 仅使用英文 `document_terms` 匹配英文 Markdown 章节；
3. 返回英文章节内容。

`TOPIC_KEYWORDS` 和 `SCENARIO_KEYWORDS` 均应按此原则调整。工具描述和参数示例也应补充中英文示例，以便模型稳定选择工具并生成正确参数。

## 4. 数据库重新同步

不得手工删除 `Document`、`DocumentChunk`、FTS 或 embedding 数据。

保持文件名不变后，现有 `sync_builtin_knowledge` 会根据 `source_sha256` 检测内容变化，并自动：

1. 删除旧 `DocumentChunk`；
2. 清理 SQLite FTS 记录；
3. 对英文 Markdown 重新分块；
4. 写入英文 content 和英文章节元数据；
5. 在 PostgreSQL 环境重新生成并写入 embedding；
6. 更新文档及知识库状态和计数。

部署时应先备份目标数据库，再显式执行：

```powershell
python scripts/sync_builtin_knowledge.py
```

虽然 API 默认通过 `BUILTIN_KNOWLEDGE_AUTO_SYNC=1` 在启动时同步，但迁移时必须显式执行并检查输出及日志。若修改文件名，旧文档可能成为孤立记录，因此本次改造禁止修改文件名。

## 5. 向量检索要求

中文查询需要匹配英文 embedding，因此 embedding 模型必须具备可靠的中英跨语言语义能力。

必须分别验证：

- 英文查询 → 英文 chunk；
- 中文查询 → 同一英文 chunk；
- 相似度阈值下可稳定获得结果；
- 返回的 `content`、`section_title`、`source_path` 和 citation 一致。

若当前模型的跨语言效果不达标，应优先更换为支持中英文的 embedding 模型并重建全部 embeddings；备选方案是在生成查询向量前增加受控的中文到英文查询转换。不得保留中文知识 chunk 作为补偿。

## 6. 测试要求

### 6.1 关键词检索

为每个工具增加成对测试：

- 英文查询能够命中预期英文文件或章节；
- 中文查询能够命中相同英文文件或章节；
- 返回正文为英文；
- source、章节数量及原有输出结构不变。

现有中文用例不得直接删除，应保留为双语兼容性回归测试，并补充对应英文用例。

### 6.2 向量检索

在 PostgreSQL + pgvector 环境验证：

- 三个工具的中英文查询均可命中；
- 新 chunk 的 embedding 非空；
- 不再返回旧中文 content；
- `section_title` 能正确映射英文 Markdown 章节；
- 相同文件或章节的重复结果得到正确去重。

### 6.3 同步幂等性

连续执行两次同步：

1. 第一次应报告文件已重新同步并生成新 chunks；
2. 第二次应报告文件未变化；
3. 两次执行后文档和 chunk 数量不得继续增长；
4. 不得出现同文件名的重复 `Document`。

## 7. 数据验收标准

迁移完成后必须确认：

- 所有目标 Markdown 的内容均为英文；
- 三个内置知识库的 `DocumentChunk.content` 不包含中文正文；
- `chunk_metadata.section_title`、`heading_path` 为英文；
- `source_sha256` 与当前英文文件一致；
- 所有目标文档状态均为 `indexed`；
- PostgreSQL 中所有目标 chunk 的 embedding 均非空；
- 数据库中不存在旧中文 chunk、重复文档或孤立 FTS 记录；
- 中英文 keyword 查询均通过；
- 中英文 vector 查询均通过；
- 项目现有知识检索与回归测试全部通过。

## 8. 建议实施顺序

```text
1. 备份目标数据库
2. 翻译 Markdown，保持文件名和结构不变
3. 增加中英文查询别名，并拆分 query_aliases/document_terms
4. 更新工具描述、参数示例和自动化测试
5. 显式运行 sync_builtin_knowledge
6. 检查英文 chunks、metadata、embeddings 和重复数据
7. 执行中英文 keyword/vector 验收测试
8. 重启服务并完成全量回归测试
```

本次改造仅处理知识内容英文化和双语查询兼容，不改变现有检索工具的对外名称、参数结构及返回数据结构。
