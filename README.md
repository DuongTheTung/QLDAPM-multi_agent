# ComicFlow — xưởng truyện tranh multi-agent

ComicFlow nhận **một yêu cầu duy nhất** rồi tự điều phối 5 agent LangGraph để tạo kịch bản, hồ sơ nhân vật, ảnh tham chiếu, bìa, các trang truyện có bóng thoại và PDF hoàn chỉnh.

## 5 agent

1. **PM** — phân tích brief, tạo lịch và workflow, theo dõi/re-assign lỗi.
2. **Biên kịch** — tạo cấu trúc mở–thắt–cao trào–kết–bài học, chia trang và viết lời thoại.
3. **Thiết kế nhân vật** — khóa style, character/bối cảnh anchors và tạo ảnh tham chiếu.
4. **Họa sĩ** — tạo prompt và ảnh bìa/trang, giữ vùng trống cho bóng thoại.
5. **Biên tập & dàn trang** — quality gate, yêu cầu sửa lỗi nghiêm trọng, gắn bóng thoại và xuất PDF.

## Chạy bằng terminal

Yêu cầu: Python 3.11+, Node 20+ và 9Router đang chạy tại `http://localhost:20128/v1`.

Tạo `.env` từ `.env.example`, sau đó điền `NINE_ROUTER_API_KEY` và model ảnh. Mở terminal thứ nhất:

```cmd
cd /d D:\Truyen_tranh
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e .
.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

Mở terminal thứ hai:

```cmd
cd /d D:\Truyen_tranh\frontend
npm install
npm run dev
```

Dashboard: `http://localhost:5173`. API docs: `http://localhost:8000/docs`.

## Điều khiển workflow và sửa lỗi

Biên tập trả `PASS` hoặc `REVISE`. `REVISE` bắt buộc chỉ rõ `writer`, `designer` hoặc `artist`; LangGraph tạo ticket, gán đúng agent và chạy lại các bước phụ thuộc. Sau `MAX_REVISIONS`, dự án chuyển sang `needs_attention` thay vì lặp vô hạn.

- Dự án `running` hoặc `queued` có nút **Dừng**. Backend hủy task đang chạy và lưu trạng thái `stopped`.
- Dự án `failed`, `needs_attention` hoặc `stopped` có nút **Tiếp tục** để chạy từ stage an toàn gần nhất.
- Dự án đã dừng, lỗi hoặc hoàn tất có nút thùng rác. Sau khi xác nhận, hệ thống xóa cả bản ghi SQLite và thư mục artifact.

## Quản lý agent theo dự án

Mỗi dự án luôn có 5 agent lõi: PM, Biên kịch, Thiết kế nhân vật, Họa sĩ và Biên tập & dàn trang. Tab **Agent** cho phép thêm tối đa 10 agent chuyên gia với tên, vai trò, màu nhận diện và hướng dẫn riêng; agent bổ sung có thể được tạm ngưng, kích hoạt lại hoặc xóa.

Agent bổ sung chạy sau bước lập kế hoạch để tư vấn theo đúng chuyên môn. Kết quả tư vấn được đưa vào trạng thái LangGraph và chuyển cho các agent lõi; nếu một chuyên gia gặp lỗi, hệ thống ghi nhận rồi tiếp tục workflow lõi.

Khi dàn trang, ComicFlow dò vùng ít chi tiết để đặt 1–2 bóng thoại. Trang có từ 3 lượt thoại trở lên dùng dialogue rail riêng phía trên artwork để tránh che nhân vật. Biên kịch được yêu cầu viết câu đầy đủ ý, thường từ 7–22 từ; quality gate trả lại Biên kịch nếu tỷ lệ câu cụt vượt ngưỡng.

## Cấu trúc

```text
backend/app/agents/       5 agent và prompt riêng
backend/app/workflow.py   StateGraph, routing và vòng lặp QA
backend/app/services/     9Router, ảnh, dàn trang PDF
frontend/src/             dashboard React
backend/data/             SQLite + artifact runtime (không commit)
```

## Lưu ý bảo mật

Không commit `.env`. Nếu API key đã được chia sẻ công khai hoặc trong lịch sử chat, hãy rotate key trước khi dùng production.
