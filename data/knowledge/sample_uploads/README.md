# Knowledge Base Sample Files (sample_uploads)

Generated: 2026-10-18 | Purpose: demonstration files prepared for the Knowledge Base upload feature, covering all 6 file extensions supported by the frontend.

## File List and Recommended Usage

| File | Type | Recommended kb_type | Recommended upload method | Verification result |
|---|---|---|---|---|
| `products_handbook_2026.md` | Markdown product handbook | `document` | **Agent tool import** (lossless) | 7 chunks, complete heading paths |
| `product_comparison_2026.csv` | Product comparison table | `table` | **Agent tool import (only viable option)** | 2 chunks; web upload fails |
| `claims_faq_2026.txt` | Claims FAQ, 14 Q&As | `qa` | **Agent tool import** (lossless) | 6 chunks |
| `policy_clauses_summary_2026.pdf` | Policy clauses summary (2 pages) | `document` | **Web upload** (OCR pipeline) | 2 pages rasterised correctly |
| `underwriting_guidelines_2026.html` | Underwriting guidelines (with tables) | `document` | **Web upload** (OCR pipeline) | 4 pages rasterised correctly |
| `sales_sop_2026.docx` | Sales SOP (with tables) | `document` | **Web upload** (OCR pipeline) | 5 pages rasterised correctly |

## Upload Method 1: Admin Web UI (PDF / HTML / DOCX)

1. Open the admin console in a browser and go to the "Knowledge Base" page (`/admin/knowledge`).
2. Click "New Knowledge Base", enter a name (e.g. "Product Library") and create the knowledge base.
3. Click the knowledge base card to open its document list, then click "Add Document".
4. Select the PDF / HTML / DOCX file in the file picker and confirm.
5. The document status progresses through `pending -> processing -> indexed`; OCR is slow, so refresh the document list to check the status.
6. On failure, check `documents.error_message` (e.g. a missing embedding API key causes PostgreSQL indexing to fail).

## Upload Method 2: Agent Tool admin_kb_import (MD / TXT / CSV)

In the Agent chat, instruct it to call the `admin_kb_import` tool with the knowledge base ID and a project-relative path, for example:

```
Import data/knowledge/sample_uploads/products_handbook_2026.md into the knowledge base <kb_id>
```

This path reads the text directly and reuses the same chunker (512 tokens / 50 overlap) and indexer; on PostgreSQL it also generates 1536-dimensional embeddings. Re-importing a file with the same name is rejected (this is the normal deduplication logic).

## Important Notes

- **CSV cannot be uploaded via the web UI**: the backend rasteriser opens files with PyMuPDF, which does not support `.csv` (it throws a FileDataError in practice and the document becomes `failed`); import CSVs with `admin_kb_import` instead.
- **MD / TXT can also be rasterised via the web UI**, but they go through a lossy "render to image, then OCR" pipeline; for text files, prefer the Agent tool import for zero content loss.
- **PostgreSQL ingestion requires embeddings**: the indexer calls OpenRouter `text-embedding-3-small` (1536 dimensions); make sure `OPENROUTER_API_KEY` in `.env` is valid, otherwise the document is marked `failed` at the indexing stage.
- Chunking parameters are controlled by `.env`: `RAG_CHUNK_SIZE=512`, `RAG_CHUNK_OVERLAP=50`, consistent with the defaults in the knowledge base records.
- On web upload, the original file is also saved to `admin/data/kb/{kb_id}/`, which does not affect this directory.
