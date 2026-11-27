# Kho Vận DSS – Web localhost có Trợ lý AI (Nhóm 10)

Web hỗ trợ ra quyết định dự báo nhu cầu & tối ưu tồn kho trên dữ liệu Olist, chạy bằng Python trên máy của bạn.

## Chạy
1. Cài Python 3.8 trở lên (không cần cài thêm thư viện nào).
2. Mở thư mục này và chạy:
   - Windows: bấm đúp `run_windows.bat` (hoặc `python app.py`)
   - macOS / Linux: `./run_mac_linux.sh` (hoặc `python3 app.py`)
3. Trình duyệt tự mở http://localhost:8000. Đổi cổng: `python app.py --port 8080`. Dừng: Ctrl+C.

## Chức năng
- 6 phân hệ: Tổng quan & Cảnh báo, Dự báo & Nhập hàng, What-If, Rủi ro giao hàng (SHAP), Seller Intelligence, Báo cáo khuyến nghị.
- **Trợ lý AI** (nút "Hỏi trợ lý" góc phải dưới hoặc mục "Trợ lý AI" ở menu):
  - Tra cứu: danh mục cần nhập gấp, lượng nhập/vốn, tồn kho, SS/ROP của từng danh mục.
  - What-If bằng câu hỏi: "Nếu lead time 2 tuần, mức phục vụ 99% thì nước hoa nhập bao nhiêu?"
  - Rủi ro: "Đơn nào rủi ro cao?", "đơn 43bdbd9dc0", "Bang nào giao trễ nhiều nhất?"
  - Seller: "Seller nào xử lý chậm?", "seller hay hủy đơn", "các cụm seller"
  - Mô hình & thuật ngữ: "Mô hình nào tốt nhất?", "AUC là gì?", "ROP tính thế nào?"
  - Câu trả lời có nút mở thẳng phân hệ liên quan (ví dụ mở What-If đã điền sẵn kịch bản).

## Hai chế độ trợ lý
| Chế độ | Khi nào | Cách hoạt động |
|---|---|---|
| Offline (mặc định) | Không có API key | Bộ máy hiểu câu hỏi tiếng Việt (có/không dấu), tra cứu trực tiếp kết quả mô hình |
| LLM | Có key trong `.env` | Ẩn danh PII (email, SĐT, mã định danh) → gửi câu hỏi + dữ kiện tra cứu được cho Claude/LLM → trả lời tự nhiên; lỗi thì tự quay về offline |

Bật LLM: copy `.env.example` thành `.env` và điền `ANTHROPIC_API_KEY` (hoặc `OPENAI_API_KEY` + `OPENAI_BASE_URL`).
Mỗi câu hỏi được ghi nhật ký (đã ẩn danh) vào `logs/audit_log.jsonl`.

## Cấu trúc
```
app.py              máy chủ web (http.server) + API: /api/data, /api/chat, /api/assistant/status
assistant.py        trợ lý: hiểu câu hỏi, tính SS/ROP/What-If, ẩn danh PII, gọi LLM, fallback
data/dashboard_data.json   kết quả mô hình (dự báo, đề xuất nhập, rủi ro + SHAP, cụm Seller)
static/index.html   giao diện (dashboard + khung chat)
frontend/, build_frontend.py   mã nguồn giao diện; chạy build_frontend.py khi sửa giao diện
```
Lưu ý: tồn kho hiện tại là số mô phỏng (Olist không có dữ liệu tồn kho); tiền tệ BRL.
