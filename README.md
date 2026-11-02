# Fake news detection (VI + EN): khung dự án ngày 1

## Cài đặt
```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Quy trình ngày 1-4
1. Sửa `user_agent` (email thật) trong `config/sources.yaml`.
2. Với mỗi nguồn: mở trình duyệt kiểm tra trang + `robots.txt`, rồi lấy sitemap:
   `python -m src.crawl sitemaps vnexpress_real`
3. Điền `sitemaps` / `listing_pages` / `article_regex`, đặt `enabled: true`.
4. **Thử nhỏ trước**: `python -m src.crawl run --only vnexpress_real --max 20`
   rồi mở `data/parsed/vnexpress_real.jsonl` xem text có sạch không (không dính menu, quảng cáo).
5. Ổn thì chạy full trên PC (để chạy đêm): `python -m src.crawl run`. Dừng/chạy lại thoải mái.
6. Làm sạch + dedupe: `python -m src.clean build`
7. Chia tập (sau dedupe): `python -m src.clean split --ood_domains <domain_nguồn_để_riêng>`

## Hướng dẫn chi tiết Bước 5, 6, 7 và Ngày 3

### Bước 5: Chạy Crawl trên PC & Cách kiểm tra
- **Chạy tất cả nguồn đã bật**:
  ```bash
  python -m src.crawl run
  ```
  *(Có thể bấm `Ctrl + C` để dừng bất kỳ lúc nào và gõ lại lệnh trên để chạy tiếp, code đã tự động lưu cache HTML và bỏ qua bài đã parse).*
- **Chạy riêng từng nguồn nếu muốn**:
  ```bash
  python -m src.crawl run --only dantri_real
  python -m src.crawl run --only vnexpress_real
  python -m src.crawl run --only tuoitre_giathat
  python -m src.crawl run --only tingia_vi
  ```
- **Cách kiểm tra xem crawl có ổn không**:
  1. Đếm số dòng bài viết đã crawl được trong thư mục `data/parsed/`:
     ```powershell
     Get-ChildItem data/parsed/*.jsonl | ForEach-Object { "$($_.Name): $((Get-Content $_.FullName | Measure-Object -Line).Lines) bài" }
     ```
  2. Xem file log `data/raw/manifest.jsonl` để đảm bảo phần lớn URL có trạng thái `ok` (không bị `blocked_by_robots` hay `http_403`).

### Khi nào chuyển sang Bước 6 & 7?
- **Điều kiện cần**:
  1. Đã crawl xong các bài thật (`real`) từ các trang báo.
  2. **Tạo file claim tin giả tự động từ các bài debunk** (không cần làm tay):
     Chạy công cụ tự động trích xuất claim đã tích hợp sẵn:
     ```bash
     python -m src.extract_claims --input data/parsed/tuoitre_giathat.jsonl --out data/parsed/claims_tuoitre.jsonl
     python -m src.extract_claims --input data/parsed/tingia_vi.jsonl --out data/parsed/claims_tingia.jsonl
     ```
     *(Lệnh trên dùng thuật toán Heuristic Regex, chạy offline 100%, không tốn token LLM).*
  3. Khi đã có các file `claims_*.jsonl` trong `data/parsed/`, bạn chuyển sang Bước 6 & 7.

- **Thực hiện Bước 6 & 7**:
  ```bash
  # Bước 6: Làm sạch văn bản, cắt bỏ dấu hiệu nhận diện tên báo, dedupe bài trùng lặp
  python -m src.clean build

  # Bước 7: Chia tập train (70%) / val (15%) / test (15%)
  python -m src.clean split
  ```

### Giải thích Bước tiếp theo (Ngày 3)
1. **Mục tiêu Ngày 3**: Xây dựng mô hình Baseline đơn giản (TF-IDF + Logistic Regression) để kiểm tra chất lượng dữ liệu và phát hiện hiện tượng "học vẹt" (shortcut learning / data leakage).
2. **Hiện tượng điểm cao giả (Leakage)**: 
   - Nếu chạy Logistic Regression mà đạt F1 ~ 99% - 100% ngay từ đầu, mô hình chưa chắc đã học được "bản chất tin giả", mà có thể đang phân biệt dựa trên dấu vết nguồn (ví dụ bài thật có chữ *"Dân trí"*, *"VnExpress"*, *"TP.HCM"*, còn tin giả không có).
3. **Cách xử lý**:
   - Trích xuất top các từ/cụm từ có trọng số (weights) cao nhất của Logistic Regression.
   - Nếu thấy các token rác/tên báo xuất hiện ở top đặc trưng, mở `src/clean.py` và thêm regex tương ứng vào danh sách `SOURCE_PATTERNS_CI` để lọc sạch hơn, sau đó chạy lại `clean build` -> `clean split`.
