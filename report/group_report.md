# Group Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin bài nộp

| Thông tin | Nội dung |
|---|---|
| Khóa/Lớp | K4 — K4-L3-DAY10 |
| Tên nhóm | TAC |
| Repository | https://github.com/caovancuong611/K4-Day10-TAC |
| Ngày hoàn thành | 2026-09-25 |

### Thành viên và phân công

| STT | Họ và tên | MSSV | Vai trò chính | Module/deliverable sở hữu |
|---:|---|---|---|---|
| 1 | Chu Phúc Anh | 2A202602370 | Data Foundation & Pipeline Lead | `core/config.py`, `ingestion/`, `pipelines/`, clean/corruption artifacts |
| 2 | Cao Văn Cường | 2A202602493 | RAG & Vector Index Specialist | `retrieval/index.py`, `retrieval/qa.py`, ChromaDB và embedding manifests |
| 3 | Lê Văn Tài | 2A202602464 | Observability & Evaluation Lead | `observability/`, `evaluation/`, quality/evaluation reports |

## 2. Tóm tắt kết quả

Nhóm TAC đã hoàn thiện pipeline dữ liệu end-to-end cho hệ thống RAG sử dụng dữ liệu bài báo Crossref. Pipeline hỗ trợ hai chế độ lấy dữ liệu: gọi API khi cần làm mới và tự động dùng snapshot offline khi API hoặc mạng không khả dụng. Toàn bộ 24 bản ghi được chuẩn hóa DOI, tiêu đề, JATS/XML, tác giả, chuyên ngành và ngày xuất bản; sau đó được tính `age_days`, khử trùng lặp và ghép thành `text_for_embedding`. Dữ liệu sạch vượt qua Quality Gate Great Expectations 1.x và được nạp vào ChromaDB bằng mô hình `sentence-transformers/all-MiniLM-L6-v2`.

Baseline đạt Retrieval Hit Rate 1.0 và Mean Token F1 1.0 trên bộ 5 câu hỏi cố định. Bộ thử thách tiêm đủ 6 dạng lỗi: mất bản ghi mới, summary rỗng, text noise, title bị cắt, ngày cũ và duplicate. Sau corruption, Quality Gate chuyển sang FAIL, stale ratio tăng từ 4.17% lên 33.33%, Retrieval Hit Rate giảm còn 0.6 và Token F1 còn 0.4. Repair từ raw snapshot đưa cả hai metric trở lại 1.0 và Quality Gate trở lại PASS. Giới hạn hiện tại là corpus chỉ có 24 bản ghi; Ragas chưa chạy và LLM Judge trong artifacts dùng heuristic fallback do evaluator bên ngoài không khả dụng trong lần xác minh.

## 3. Kiến trúc và luồng dữ liệu

### Luồng end-to-end

```text
Crossref API hoặc snapshot offline
    -> data/raw/crossref_response.json
    -> parse thành PaperRecord
    -> cleaning, age_days, text_for_embedding
    -> Great Expectations 1.x + Freshness SLA
    -> MiniLM embedding + ChromaDB
    -> benchmark 5 câu + baseline metrics
    -> tiêm 6 corruption scenarios
    -> quality/retrieval suy giảm
    -> repair từ raw snapshot
    -> re-index, re-evaluate và comparison report
```

### Trách nhiệm của từng khối

| Khối | Input | Xử lý chính | Output/artifact | Owner |
|---|---|---|---|---|
| Ingestion | Crossref API/snapshot | Retry, fallback, chuẩn hóa DOI/JATS/date | `data/raw/` | Chu Phúc Anh |
| Cleaning | `PaperRecord` | Normalize, deduplicate, tính `age_days`, ghép embedding text | `data/clean/` | Chu Phúc Anh |
| Embedding/index | Clean dataframe | MiniLM embedding, tạo 3 Chroma collections | `data/chroma/`, `data/embeddings/` | Cao Văn Cường |
| Evaluation | Clean data và Chroma index | Tạo 5 loại câu hỏi, retrieval hit, Token F1, judge | `data/eval/`, `data/results/` | Lê Văn Tài |
| Observability | Dataframe clean/corrupted/repaired | GX 1.x expectations và freshness SLA | `data/quality/` | Lê Văn Tài |
| Corruption/repair | Clean dataframe/raw records | Tiêm 6 lỗi, tái tạo sạch từ raw | `corruption_log.json`, repaired artifacts | Chu Phúc Anh |
| Orchestration/report | Tất cả module | Chạy đúng thứ tự, fail gate, tổng hợp bằng chứng | `data/reports/` | Chu Phúc Anh và Lê Văn Tài |

## 4. Cách tái hiện kết quả

### Cấu hình không chứa secret

| Biến/cấu hình | Giá trị sử dụng |
|---|---|
| `LLM_PROVIDER` | `gemini` (artifacts hiện tại dùng judge fallback) |
| `LLM_MODEL` | `gemini-2.5-flash` |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` |
| Số lượng Crossref records | 24 |
| Retrieval `top_k` | 4 |
| Freshness threshold | 180 ngày; stale ratio tối đa 25% |
| Random seed | Không dùng; lựa chọn corruption theo thứ tự `paper_id` ổn định |

Không lưu API key hoặc nội dung `.env` trong báo cáo và repository.

### Lệnh cài đặt

```bash
python -m pip install -e .
```

### Lệnh chạy

```bash
python script/run_phase1.py
python script/run_corruption_flow.py
```

### Kết quả tái hiện

| Lệnh | Trạng thái | Thời điểm chạy gần nhất | Bằng chứng |
|---|---|---|---|
| Baseline pipeline | Thành công | 2026-09-25 | `baseline_metrics.json`, `phase1_report.md` |
| Corruption flow | Thành công | 2026-09-25 | `corruption_log.json`, `corruption_report.md` |

## 5. Ingestion, cleaning và data contract

### Nguồn dữ liệu

| Thuộc tính | Giá trị |
|---|---|
| Source | `https://api.crossref.org/works` hoặc `data/raw/crossref_response.json` |
| Query/filter | `agentic retrieval augmented generation large language model`; `has-abstract:true` và cửa sổ 180 ngày khi gọi live |
| Thời điểm xử lý gần nhất | 2026-09-25 |
| Số record nhận được | 24 |
| Retry/backoff | 3 lần, backoff factor 1 giây cho 429/5xx; fallback snapshot khi lỗi mạng/API/JSON |

### Raw và clean schema

| Trường | Kiểu dữ liệu | Bắt buộc? | Ý nghĩa | Xử lý khi thiếu/sai |
|---|---|---|---|---|
| `paper_id` | string | Có | DOI chuẩn hóa, khóa duy nhất | Bỏ record thiếu DOI; lowercase và bỏ prefix URL/`doi:` |
| `title` | string | Có | Tiêu đề bài báo | Bỏ record thiếu; normalize khoảng trắng |
| `summary` | string | Có theo Quality Gate | Abstract/tóm tắt | Bỏ HTML/JATS; GX yêu cầu tối thiểu 30 ký tự |
| `authors` | list[string] | Không | Danh sách tác giả | Ghép given/family; fallback `Unknown` khi rỗng |
| `categories` | list[string] | Không | Chuyên ngành | Deduplicate; fallback `Uncategorized` |
| `published` | ISO date | Có | Ngày xuất bản | Thử nhiều trường Crossref; bỏ record không parse được |
| `age_days` | integer | Có | Tuổi dữ liệu tại ngày chạy | Tính `(run_date - published).days` |
| `text_for_embedding` | string | Có | Nội dung đưa vào MiniLM | Ghép đủ Title, Authors, Published, Categories, Summary |

### Quy tắc cleaning

| Quy tắc | Quality dimension | Record bị tác động | Cách xác minh |
|---|---|---:|---|
| Chuẩn hóa khoảng trắng và bỏ JATS/XML | Validity | 24 abstracts được chuẩn hóa | Không còn chuỗi `<jats:` trong clean JSON |
| Chuẩn hóa DOI và khử trùng lặp | Uniqueness | 0 duplicate trong baseline | `paper_id.is_unique=True`; GX PASS |
| Parse ngày ISO và tính `age_days` | Timeliness | 24 | Cột `published`, `age_days` trong clean CSV |
| Ghép `text_for_embedding` 5 phần | Completeness | 24 | Mỗi dòng có đủ 5 nhãn nội dung |

`paper_id` được dùng làm document identity xuyên suốt raw, clean, test set và Chroma metadata. `age_days` phục vụ Freshness SLA, còn `text_for_embedding` giữ cấu trúc thống nhất để embedding có đủ ngữ cảnh.

## 6. Evaluation setup

| Thành phần | Cấu hình thực tế |
|---|---|
| Số câu hỏi | 5 |
| `question_type` | `summary`, `authors`, `date`, `category`, `multi_hop` |
| Ground-truth document ID | DOI từ cột `paper_id` của clean dataframe |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` |
| Vector store/collection | ChromaDB cosine: `papers-baseline`, `papers-corrupted`, `papers-repaired` |
| Retrieval `top_k` | 4 |
| LLM provider/model | Cấu hình Gemini 2.5 Flash; artifacts dùng heuristic judge fallback |
| Test set dùng chung | `data/eval/test_set.json` |

Cùng một test set và ground truth được tái sử dụng cho cả ba trạng thái để thay đổi metric chỉ phản ánh thay đổi của dữ liệu/index, không bị nhiễu bởi việc đổi câu hỏi hoặc đáp án.

## 7. Kết quả baseline

### Artifact checklist

| Artifact | Đường dẫn | Trạng thái | Ghi chú |
|---|---|---|---|
| Raw response/records | `data/raw/` | Có | 24 records |
| Cleaned dataset | `data/clean/` | Có | CSV và JSON, 24 dòng |
| Embedding manifest/index | `data/embeddings/`, `data/chroma/` | Có | Collection baseline 24 vectors |
| Evaluation set | `data/eval/test_set.json` | Có | 5 loại câu hỏi |
| Baseline metrics | `data/results/baseline_metrics.json` | Có | Cùng test set với corruption/repair |
| Quality/freshness | `data/quality/` | Có | Baseline PASS/FRESH |
| Baseline report | `data/reports/phase1_report.md` | Có | Báo cáo Markdown |

### Baseline metrics

| Metric | Giá trị | Diễn giải |
|---|---:|---|
| `retrieval_hit_rate` | 1.0 | Cả 5 câu đều lấy được ít nhất một ground-truth document |
| `mean_token_f1` | 1.0 | Câu trả lời trùng khớp ground truth ở mức token |
| `judge_accuracy` | 1.0 | 5/5 câu được heuristic judge đánh giá đúng |
| `mean_judge_score` | 5.0/5 | Mức điểm trung bình tối đa trên baseline |
| Ragas | N/A | Bị skip; chỉ chạy khi đặt `RUN_RAGAS=1` |

## 8. Data quality và freshness

### Quality checks

| Check | Dimension | Ngưỡng/kỳ vọng | Baseline | Bằng chứng |
|---|---|---|---|---|
| Row count | Volume | 5–5000 | PASS, 24 | `baseline_quality_report.json` |
| Required values | Completeness | `paper_id`, `title`, `text_for_embedding` không null/rỗng | PASS, 0 unexpected | Cùng report |
| Unique DOI | Uniqueness | `paper_id` duy nhất | PASS, 0 duplicate | Cùng report |
| Summary length | Completeness | Tối thiểu 30 ký tự | PASS, 0 unexpected | Cùng report |

### Freshness

| Thuộc tính | Giá trị |
|---|---|
| Freshness được đo tại | Clean dataframe, cột `age_days` |
| Timestamp mới nhất | 2026-07-22 |
| Ngưỡng freshness | `age_days > 180`; stale ratio không vượt 25% |
| Trạng thái baseline | FRESH |
| Lý do | 1/24 bản ghi stale, tương đương 4.17% |

## 9. Corruption scenarios và repair

| Corruption | Cách tạo | Record tác động | Signal kỳ vọng/thực tế | Cách repair |
|---|---|---:|---|---|
| Drop latest records | Bỏ 20% bản ghi mới nhất | 5 | Mất coverage; hit rate giảm | Tạo lại từ raw snapshot |
| Blank summary | Thay summary bằng chuỗi rỗng | 3 | Summary-length expectation FAIL | Parse và clean lại raw |
| Inject text noise | Thêm token rác lặp lại | 3 | Embedding/retrieval bị nhiễu | Tạo lại embedding text |
| Truncate title | Cắt còn tối đa 7 ký tự | 3 | Exact lookup/semantic context suy giảm | Khôi phục title từ raw |
| Stale date | Lùi published 5 năm | 7 | Stale ratio 33.33%, Freshness FAIL | Parse lại ngày nguồn |
| Duplicate rows | Nhân đôi hàng | 5 | 10 giá trị unexpected, Unique FAIL | Deduplicate theo DOI |

Corruption log tồn tại tại `data/results/corruption_log.json`, ghi đủ 6 loại, số lượng và các DOI bị tác động. Repair không sửa trực tiếp dữ liệu bẩn mà xây dựng lại dataframe từ `crossref_records.json`, chạy lại cleaning, quality gate, embedding và evaluation; vì vậy nguồn phục hồi là raw snapshot đáng tin cậy và quy trình có tính idempotent.

## 10. So sánh baseline, corrupted và repaired

| Metric/signal | Baseline | Corrupted | Repaired | Thay đổi | Mức phục hồi | Nhận xét |
|---|---:|---:|---:|---:|---:|---|
| `retrieval_hit_rate` | 1.0 | 0.6 | 1.0 | -0.4 | 100% | Mất/noisy documents làm giảm retrieval coverage |
| `mean_token_f1` | 1.0 | 0.4 | 1.0 | -0.6 | 100% | Summary/date/title lỗi làm câu trả lời sai |
| `judge_accuracy` | 1.0 | 0.4 | 1.0 | -0.6 | 100% | Heuristic judge phản ánh suy giảm answer quality |
| `mean_judge_score` | 5.0 | 2.6 | 5.0 | -2.4 | 100% | Điểm phục hồi hoàn toàn sau repair |
| Quality Gate | PASS | FAIL | PASS | Fail uniqueness và summary | Hoàn toàn | Gate chặn dữ liệu bẩn trước serving |
| Freshness | FRESH | STALE | FRESH | 4.17% → 33.33% | Hoàn toàn | Repair đưa stale ratio về 4.17% |

1. Tiêm duplicate, blank summary, stale date và nhiễu embedding → uniqueness/summary/freshness chuyển sang FAIL → Retrieval Hit Rate giảm 0.4 và Token F1 giảm 0.6.
2. Xây dựng lại từ raw snapshot → loại duplicate, phục hồi summary/date/text → Quality/Freshness trở lại PASS/FRESH và toàn bộ metric trở về baseline.

## 11. Vấn đề tích hợp quan trọng

- **Triệu chứng:** Skeleton sử dụng giao diện chưa khớp lệnh checkpoint; GX syntax cũ và `LocalEmbeddingIndex` thiếu `build_from_clean`/`semantic_search` khiến pipeline không chạy xuyên suốt.
- **Nguyên nhân:** API Great Expectations 1.x và contract giữa module đã thay đổi so với skeleton ban đầu.
- **Cách xử lý:** Dùng ephemeral GX context với `data_sources.add_pandas`, bổ sung compatibility methods, thống nhất `test_set_json` và schema `type/question_type`.
- **Cách xác minh:** Chạy hai script end-to-end; baseline quality `True`, semantic search trả 2 kết quả, corruption flow thoát với repaired quality `True`.

## 12. Giới hạn và hướng cải thiện

| Giới hạn hiện tại | Ảnh hưởng | Hướng cải thiện có thể kiểm chứng |
|---|---|---|
| Corpus 24 bài và 5 câu benchmark | Chưa đại diện nhiều chủ đề và phân bố thực tế | Mở rộng corpus/test set, báo cáo metric theo từng question type |
| LLM evaluator bên ngoài không khả dụng trong lần chạy | Judge artifacts dùng heuristic fallback | Chạy lại với Gemini được cấp quyền và so sánh agreement với heuristic |
| Ragas đang tắt mặc định | Chưa có faithfulness/context precision/recall | Đặt `RUN_RAGAS=1`, lưu và đối chiếu thêm các metric |
| Corruption được tiêm theo batch cố định | Chưa đo độ nhạy theo cường độ lỗi | Chạy nhiều mức corruption ratio và vẽ degradation curve |

## 13. Checklist trước khi nộp

- [x] Thông tin nhóm và repository chính xác.
- [x] Phân công khớp với module, artifact và kết quả thực tế.
- [x] Lệnh tái hiện đã được chạy lại trên phiên bản dùng để báo cáo.
- [x] Baseline, corrupted và repaired dùng cùng evaluation set.
- [x] Bảng metrics khớp với các file trong `data/results/`.
- [x] Quality/freshness conclusions khớp với `data/quality/`.
- [x] Các đường dẫn báo cáo và artifact truy cập được.
- [x] Mỗi thành viên có một báo cáo vai trò riêng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
