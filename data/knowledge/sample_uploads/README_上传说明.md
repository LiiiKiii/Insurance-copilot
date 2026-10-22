# 知识库示例文件（sample_uploads）

生成日期：2026-10-18　|　用途：为知识库（Knowledge Base）上传功能准备的演示文件，覆盖前端支持的全部 6 种扩展名。

## 文件清单与推荐用法

| 文件 | 类型 | 建议 kb_type | 推荐上传方式 | 验证结果 |
|---|---|---|---|---|
| `products_handbook_2026.md` | Markdown 产品手册 | `document` | **Agent 工具导入**（无损） | 7 个分块，标题路径完整 |
| `product_comparison_2026.csv` | 产品对比表 | `table` | **Agent 工具导入（唯一可行）** | 2 个分块；网页上传会失败 |
| `claims_faq_2026.txt` | 理赔问答 14 则 | `qa` | **Agent 工具导入**（无损） | 6 个分块 |
| `policy_clauses_summary_2026.pdf` | 保单条款摘要（2 页） | `document` | **网页上传**（OCR 流水线） | 2 页光栅化正常 |
| `underwriting_guidelines_2026.html` | 核保指引（含表格） | `document` | **网页上传**（OCR 流水线） | 4 页光栅化正常 |
| `sales_sop_2026.docx` | 销售 SOP（含表格） | `document` | **网页上传**（OCR 流水线） | 5 页光栅化正常 |

## 上传方法一：管理后台网页（PDF / HTML / DOCX）

1. 浏览器打开管理后台 →「知识库」页面（`/admin/knowledge`）。
2. 点击「新建知识库」，填写名称（例如「产品资料库」），创建知识库。
3. 点击该知识库卡片进入文档列表 →「添加文档」。
4. 在文件选择框选中 PDF / HTML / DOCX 文件并确认。
5. 文档状态依次为 `pending → processing → indexed`；OCR 较慢，可在文档列表刷新查看状态。
6. 失败时查看 `documents.error_message`（例如缺少 embedding API Key 会导致 PostgreSQL 索引失败）。

## 上传方法二：Agent 工具 admin_kb_import（MD / TXT / CSV）

在 Agent 对话中指示其调用 `admin_kb_import` 工具，参数为知识库 ID 和项目相对路径，例如：

```
把 data/knowledge/sample_uploads/products_handbook_2026.md 导入到知识库 <kb_id>
```

该路径直接读取文本，复用同一套切块器（512 token / 50 重叠）与索引器；在 PostgreSQL 上会同步生成 1536 维 embedding。
同名文件重复导入会被拒绝（属正常防重逻辑）。

## 重要注意事项

- **CSV 不能走网页上传**：后端光栅化器用 PyMuPDF 打开文件，不支持 `.csv`（实测抛 FileDataError，文档会变 `failed`）；CSV 请用 `admin_kb_import` 导入。
- **MD / TXT 虽然网页上传也能光栅化**，但会经过「渲染成图片再 OCR」的有损路径；文本文件请优先用 Agent 工具导入，内容零损耗。
- **PostgreSQL 入库需要 embedding**：索引器会调用 OpenRouter `text-embedding-3-small`（1536 维），请确认 `.env` 中 `OPENROUTER_API_KEY` 有效，否则文档在 index 阶段标记 `failed`。
- 切块参数由 `.env` 控制：`RAG_CHUNK_SIZE=512`、`RAG_CHUNK_OVERLAP=50`，与知识库记录中的默认值一致。
- 原始文件在网页上传时会另存一份到 `admin/data/kb/{kb_id}/`，与本目录互不影响。
