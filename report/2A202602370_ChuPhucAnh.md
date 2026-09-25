# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
|---|---|
| Họ và tên | Chu Phúc Anh |
| MSSV | 2A202602370 |
| Khóa/Lớp | K4 — K4-L3-DAY10 |
| Tên nhóm | TAC |
| Vai trò chính | Data Foundation & Pipeline Lead |
| Repository | https://github.com/caovancuong611/K4-Day10-TAC |
| Ngày hoàn thành | 2026-09-25 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
|---|---|---|---|---|
| Raw ingestion | `crossref.py` | Crossref API hoặc snapshot | 24 `PaperRecord`, raw artifacts | Hoàn thành |
| Cleaning/data model | `cleaning.py` | Danh sách `PaperRecord` | Clean CSV/JSON, `age_days`, embedding text | Hoàn thành |
| Corruption/repair | `corruption.py`, `corruption_flow.py` | Clean dataframe và raw records | 6 corruption scenarios, repaired data | Hoàn thành |
| Pipeline integration | `core/config.py`, `phase1.py` | Settings và các module con | Pipeline baseline end-to-end | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
|---|---|---|
| Thống nhất schema và artifact paths | RAG và Observability | `paper_id`, `text_for_embedding`, `age_days` dùng nhất quán |
| Chạy tích hợp corruption–repair | Cao Văn Cường, Lê Văn Tài | Ba trạng thái dùng cùng test set và có đủ metrics |

## 3. Kết quả theo vai trò

| Nhiệm vụ | File/artifact | Kết quả bàn giao | Cách xác minh |
|---|---|---|---|
| Parse và fallback Crossref | `src/ingestion/crossref.py`, `data/raw/` | 24 records, DOI/date/JATS chuẩn hóa | Lệnh checkpoint ingestion |
| Tạo clean dataframe | `src/ingestion/cleaning.py`, `data/clean/` | 24 dòng unique, đủ embedding text | Lệnh checkpoint cleaning |
| Tiêm lỗi có kiểm soát | `corruption.py`, `corruption_log.json` | Đủ 6 scenarios, output 24 dòng | `scenario_count=6` |
| Điều phối repair | `corruption_flow.py` | Quality `FAIL → PASS`, metrics phục hồi | `corruption_report.md` |

Output tiêu biểu là `data/clean/papers_clean.json`: chứa 24 DOI duy nhất, `published` chuẩn ISO, `age_days` và nội dung embedding theo đúng contract 5 phần.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Nguồn Crossref có cấu trúc trường không hoàn toàn đồng nhất và có thể không truy cập được trong phòng lab. Dữ liệu phải được chuẩn hóa nhưng vẫn bảo toàn raw lineage, sau đó ghép các module thành pipeline có thể chạy lại và repair mà không sửa tay dữ liệu bẩn.

### Cách triển khai

Parser nhận title dạng chuỗi/danh sách, chuẩn hóa DOI, ghép tên tác giả, loại HTML/JATS và thử nhiều trường ngày của Crossref. Chế độ live sử dụng retry cho 429/5xx; khi lỗi mạng/API/JSON, pipeline đọc snapshot offline. Cleaning parse ngày về UTC, tính `age_days`, deduplicate theo `paper_id` và ghép 5 phần của `text_for_embedding`. Corruption chọn dòng theo thứ tự `paper_id` ổn định, ghi log từng lỗi. Repair đọc lại raw records và chạy lại toàn bộ cleaning/index/evaluation.

### Input, output và contract

| Thành phần | Mô tả |
|---|---|
| Input | Crossref JSON hoặc `data/raw/crossref_response.json` |
| Output | `PaperRecord`, clean dataframe, corrupted/repaired dataframe |
| Module phụ thuộc | `core.config`, `core.utils` |
| Module sử dụng output | Observability, retrieval index, evaluation |
| Điều kiện lỗi | 429/mất mạng, DOI/title/date thiếu, record trùng, artifact thiếu |

### Cách xác minh

```bash
python -c "from core.config import load_settings; from ingestion.crossref import fetch_source_records; s=load_settings(); print(len(fetch_source_records(s)))"
python script/run_phase1.py
python script/run_corruption_flow.py
```

- **Kết quả mong đợi:** 24 raw/clean records; baseline PASS; corrupted FAIL; repaired PASS.
- **Kết quả thực tế:** Đúng 24 records; pipeline chạy thành công và repair phục hồi metrics.
- **Artifact/log:** `data/raw/`, `data/clean/`, `data/results/corruption_log.json`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Pipeline cần chạy được cả khi Crossref quá tải hoặc phòng lab mất mạng.
- **Các phương án:** Bắt buộc gọi live API; hoặc dùng dual-mode với snapshot bảo toàn từ trước.
- **Phương án chọn:** Dual-mode, live chỉ khi `REFRESH_SOURCE=1`, còn lại dùng snapshot.
- **Lý do:** Tăng reproducibility, giảm phụ thuộc mạng và vẫn giữ khả năng lấy dữ liệu mới.
- **Bằng chứng:** Cùng snapshot tạo lại đúng 24 clean records và repaired metrics bằng baseline.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng:** Các lệnh checkpoint tham chiếu `settings.paths.test_set_json`, `build_from_clean()` và `semantic_search()` nhưng skeleton chưa cung cấp đầy đủ contract này.
- **Bước tái hiện:** Chạy các lệnh checkpoint CP2 trên starter code.
- **Nguyên nhân gốc:** Tên thuộc tính/phương thức giữa tài liệu và skeleton không đồng nhất.
- **Cách xử lý:** Bổ sung alias đường dẫn và phối hợp bổ sung compatibility methods trong vector index.
- **Cách xác minh:** Smoke test trả đúng 2 tài liệu và pipeline Phase 1 thoát với quality `True`.
- **Điều học được:** Contract liên module phải được kiểm tra bằng chính lệnh nghiệm thu, không chỉ bằng unit logic riêng lẻ.

## 7. Hiểu biết về luồng end-to-end

Crossref JSON được giữ nguyên làm raw lineage, parse thành `PaperRecord`, làm sạch và tính tuổi dữ liệu. Quality Gate kiểm tra schema/nội dung trước khi clean text được MiniLM biến thành vector và lưu trong ChromaDB. Test set lưu câu hỏi, đáp án và DOI ground truth; retrieval hit kiểm tra DOI có xuất hiện trong top-k, còn Token F1 đo câu trả lời. Quality checks phát hiện completeness/uniqueness/volume, trong khi freshness đo tỷ lệ bài quá 180 ngày. Cùng test set phải dùng cho ba trạng thái để phép so sánh không bị đổi đề. Repair thành công khi dữ liệu tái tạo từ raw vượt Quality Gate và các metrics quay về baseline.

## 8. Phân tích kết quả

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét |
|---|---:|---:|---:|---|
| `retrieval_hit_rate` | 1.0 | 0.6 | 1.0 | Mất record và nhiễu làm giảm coverage |
| `mean_token_f1` | 1.0 | 0.4 | 1.0 | Nội dung/date/title lỗi làm sai đáp án |
| `judge_accuracy` | 1.0 | 0.4 | 1.0 | Phục hồi hoàn toàn sau repair |
| `mean_judge_score` | 5.0 | 2.6 | 5.0 | Judge hiện dùng heuristic fallback |
| Quality Gate | PASS | FAIL | PASS | Duplicate và summary rỗng bị phát hiện |
| Freshness | FRESH | STALE | FRESH | Stale ratio 4.17% → 33.33% → 4.17% |

1. Corruption làm mất/biến dạng dữ liệu → Quality/Freshness FAIL → Hit Rate và Token F1 giảm.
2. Repair từ raw snapshot → khôi phục schema/nội dung → Quality PASS và metrics trở lại baseline.

Stale date làm freshness thay đổi rõ nhất, còn blank summary và title/noise ảnh hưởng trực tiếp đến answer quality. Kết quả đáng chú ý là số dòng corrupted vẫn bằng 24 do drop được bù bằng duplicate; vì vậy chỉ kiểm tra row count là chưa đủ, cần uniqueness và freshness.

## 9. Điều học được và hướng cải thiện

1. Raw preservation là điều kiện để repair có thể tái lập và đáng tin cậy.
2. Row count đúng không đồng nghĩa dữ liệu đúng; cần nhiều quality dimensions.
3. Dữ liệu sai có thể làm RAG trả lời sai mà pipeline vẫn chạy bình thường.

Nếu có thêm thời gian, tôi sẽ bổ sung pytest cho parser/fallback/cleaning và kiểm tra idempotency bằng hash của clean artifacts sau nhiều lần chạy.

## 10. Cam kết của thành viên

- [ ] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [ ] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [ ] Mọi kết luận đều có artifact hoặc metric để đối chiếu.
- [ ] Tôi không ghi hoàn thành cho phần chưa được kiểm chứng.
- [ ] Báo cáo không chứa secret.
- [ ] Báo cáo không sao chép nguyên văn báo cáo thành viên khác.

**Họ và tên:** Chu Phúc Anh  
**Ngày xác nhận:** 2026-09-25

