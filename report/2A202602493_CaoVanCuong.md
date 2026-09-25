# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
|---|---|
| Họ và tên | Cao Văn Cường |
| MSSV | 2A202602493 |
| Khóa/Lớp | K4 — K4-L3-DAY10 |
| Tên nhóm | TAC |
| Vai trò chính | RAG & Vector Index Specialist |
| Repository | https://github.com/caovancuong611/K4-Day10-TAC |
| Ngày hoàn thành | 2026-09-25 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
|---|---|---|---|---|
| Embedding | `retrieval/embeddings.py` | `text_for_embedding` | Vector MiniLM chuẩn hóa | Hoàn thành |
| Chroma index | `retrieval/index.py` | Clean/corrupted/repaired dataframe | 3 persistent collections | Hoàn thành |
| Retrieval/QA | `retrieval/qa.py` | Query và top-k documents | Answer, contexts, retrieved DOI | Hoàn thành |
| Retrieval artifacts | `data/chroma/`, `data/embeddings/` | Indexed documents | Persistent DB và manifests | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
|---|---|---|
| Smoke test semantic retrieval | Pipeline integration | Query `machine learning` trả đúng 2 kết quả |
| Đối chiếu ba collection | Evaluation/repair | Mỗi collection baseline/corrupted/repaired có 24 vectors |

## 3. Kết quả theo vai trò

| Nhiệm vụ | File/artifact | Kết quả bàn giao | Cách xác minh |
|---|---|---|---|
| Xây dựng document/metadata contract | `LocalEmbeddingIndex._build_documents` | DOI, title, published, author/category/summary trong metadata | Đọc embedding manifests |
| Build persistent Chroma | `LocalEmbeddingIndex.build` | Cosine collections tái tạo idempotent | `collection.count()` |
| Hỗ trợ API checkpoint | `build_from_clean`, `semantic_search` | Lệnh smoke test chạy đúng | Top-k trả 2 documents |
| Exact lookup và multi-hop | `retrieval/qa.py` | Ưu tiên title match, ghép hai tài liệu | Baseline Token F1 1.0 |

Output tiêu biểu là ba collection `papers-baseline`, `papers-corrupted`, `papers-repaired`, mỗi collection có 24 vectors nhưng giữ riêng trạng thái để phép so sánh không bị ghi đè.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Clean text phải được biến thành vector có thể truy vấn ngữ nghĩa, lưu bền vững và có metadata đủ để trả lời câu hỏi. Đồng thời ba trạng thái dữ liệu phải được cô lập để đo suy giảm và phục hồi chính xác.

### Cách triển khai

`MiniLMEmbeddings` dùng `sentence-transformers/all-MiniLM-L6-v2` và normalize embeddings. Mỗi row tạo một `record_id` gồm DOI và chỉ số để Chroma chấp nhận cả dữ liệu duplicate trong thí nghiệm. Collection dùng cosine distance; trước mỗi lần build, collection cùng tên bị xóa và tạo lại để tránh ghost vectors. Search chuyển distance thành similarity score và trả `SearchResult`. QA ưu tiên exact title/DOI, sau đó kết hợp semantic retrieval; câu multi-hop ghép evidence từ hai exact documents.

### Input, output và contract

| Thành phần | Mô tả |
|---|---|
| Input | Dataframe có `paper_id`, `title`, `text_for_embedding` và metadata |
| Output | Chroma collection, embedding manifest, danh sách `SearchResult` |
| Module phụ thuộc | Cleaning schema, sentence-transformers, ChromaDB |
| Module sử dụng output | QA và `evaluation.metrics` |
| Điều kiện lỗi | Model chưa cache, collection chưa build, dataframe rỗng, metadata không phải scalar |

### Cách xác minh

```bash
python -c "from core.config import load_settings; from retrieval.index import LocalEmbeddingIndex; s=load_settings(); i=LocalEmbeddingIndex(s,'papers-baseline').build_from_clean(); print(len(i.semantic_search('machine learning',2)), i.collection.count())"
```

- **Kết quả mong đợi:** 2 search results và collection count 24.
- **Kết quả thực tế:** `2 24`.
- **Artifact/log:** `data/chroma/`, `data/embeddings/papers_embeddings.json`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Cần so sánh clean, corrupted và repaired mà không để lần build sau ghi đè lần trước.
- **Các phương án:** Dùng một collection và rebuild liên tục; hoặc dùng ba collection tách biệt.
- **Phương án chọn:** Ba collection persistent riêng biệt.
- **Lý do:** Giữ provenance rõ ràng, dễ kiểm tra count/metadata và tránh trộn vector giữa các trạng thái.
- **Bằng chứng:** Chroma liệt kê đủ `papers-baseline`, `papers-corrupted`, `papers-repaired`, mỗi collection 24 vectors.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng:** Lần đầu tải MiniLM bị treo/lỗi kết nối `WinError 10013`, model chưa có trong local cache.
- **Bước tái hiện:** Khởi tạo `SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')` trên môi trường hạn chế mạng.
- **Nguyên nhân gốc:** Cơ chế tải Xet/CDN không hoạt động trong môi trường kiểm thử.
- **Cách xử lý:** Tải các file model cần thiết qua HTTP thường, lưu Hugging Face cache và tái sử dụng offline.
- **Cách xác minh:** Bật offline mode, build Chroma và semantic search vẫn trả 2 kết quả.
- **Điều học được:** Artifact model/cache cũng là dependency cần quản lý để pipeline có thể tái hiện offline.

## 7. Hiểu biết về luồng end-to-end

Dữ liệu Crossref sau cleaning tạo một document có DOI ổn định và nội dung embedding 5 phần. MiniLM biến document thành vector, Chroma lưu vector cùng metadata. Evaluation query Chroma, so retrieved DOI với `ground_truth_doc_ids` để tính hit rate; câu trả lời được so với ground truth bằng Token F1/judge. Quality Gate kiểm tra tính hợp lệ của dataframe, còn freshness kiểm tra tuổi nội dung. Giữ nguyên test set giúp metric giữa ba collection so sánh trực tiếp. Repair thành công khi collection repaired được dựng từ raw đã làm sạch, Quality Gate PASS và retrieval/answer metrics trở lại baseline.

## 8. Phân tích kết quả

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét |
|---|---:|---:|---:|---|
| `retrieval_hit_rate` | 1.0 | 0.6 | 1.0 | Vector corpus bẩn mất 40% retrieval hits |
| `mean_token_f1` | 1.0 | 0.4 | 1.0 | Retrieved/metadata sai làm answer lệch ground truth |
| `judge_accuracy` | 1.0 | 0.4 | 1.0 | Phục hồi cùng repaired index |
| `mean_judge_score` | 5.0 | 2.6 | 5.0 | Judge fallback vẫn phản ánh degradation |
| Quality Gate | PASS | FAIL | PASS | Index không nên promote khi gate FAIL |
| Freshness | FRESH | STALE | FRESH | Stale metadata cũng ảnh hưởng câu hỏi thời gian |

1. Drop/noise/truncated title → semantic/exact retrieval suy giảm → hit rate còn 0.6 và F1 còn 0.4.
2. Re-embed dữ liệu sạch từ raw → repaired collection không còn nội dung lỗi → hit rate và F1 trở về 1.0.

Nhóm corruption ảnh hưởng rõ nhất đến RAG là mất record kết hợp noise/title/summary lỗi. Một kết quả cần lưu ý là duplicate không làm count thay đổi vì số dòng drop được bù lại; Chroma vẫn index 24 records, nhưng quality và tính đa dạng context đã sai.

## 9. Điều học được và hướng cải thiện

1. Collection rebuild phải idempotent để tránh ghost vectors.
2. Metadata contract quan trọng không kém vector vì QA dùng metadata để trích đáp án.
3. Vector count đúng không chứng minh corpus có chất lượng hoặc coverage đúng.

Nếu có thêm thời gian, tôi sẽ đánh giá thêm nhiều `top_k`, đo latency/index size và so sánh MiniLM với một embedding model khác trên cùng test set.

## 10. Cam kết của thành viên

- [ ] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [ ] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [ ] Mọi kết luận đều có artifact hoặc metric để đối chiếu.
- [ ] Tôi không ghi hoàn thành cho phần chưa được kiểm chứng.
- [ ] Báo cáo không chứa secret.
- [ ] Báo cáo không sao chép nguyên văn báo cáo thành viên khác.

**Họ và tên:** Cao Văn Cường  
**Ngày xác nhận:** 2026-09-25

