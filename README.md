# ComicFlow

ComicFlow là xưởng sản xuất truyện tranh tự động sử dụng **LangGraph**, **9Router**, FastAPI và React. Người dùng chỉ cần gửi một yêu cầu duy nhất; các agent tự lập kế hoạch, viết kịch bản, thiết kế nhân vật, tạo ảnh, kiểm duyệt, dàn trang và xuất PDF.

## Chức năng chính

- Một lệnh đầu vào duy nhất để tạo toàn bộ truyện tranh.
- 6 agent lõi tự phối hợp và giao việc cho nhau.
- List kết hợp workflow, task, subtask, dependency và lịch sản xuất.
- Testing từng đầu ra ngay khi hoàn thành, không cần đợi toàn bộ dự án.
- Ảnh từng trang được kiểm ngay sau khi Họa sĩ tạo xong.
- Tin nhắn chỉ hiển thị sản phẩm thuộc đúng công việc đó.
- Tự giao lại đúng agent khi Kiểm duyệt phát hiện lỗi nghiêm trọng.
- Tạm dừng, can thiệp, duyệt nội dung, tiếp tục hoặc dừng hẳn dự án.
- Quản lý agent bổ sung và model riêng của từng agent.
- Quản lý model mặc định của 9Router ở cấp toàn hệ thống.
- URL riêng cho trang chủ, từng dự án và từng chức năng; tải lại trang không mất vị trí.
- Tạo ảnh bìa, ảnh từng trang, bóng thoại và PDF hoàn chỉnh.

## Workflow

```text
Yêu cầu người dùng
        │
        ▼
       PM
        │
        ▼
    Biên kịch
        │
        ▼
Thiết kế nhân vật
        │
        ▼
     Họa sĩ ──► Testing từng ảnh/trang
        │               │
        ▼               └── Chưa đạt ──► trả đúng agent sửa
   Kiểm duyệt
        │
        ▼
Biên tập & dàn trang ──► Testing từng trang sau dàn
        │
        ▼
       PDF
```

Mỗi task hoặc sản phẩm đi qua hai trạng thái chính:

```text
Đang làm → Testing → Hoàn tất
                 └→ Chưa đạt → giao lại agent phụ trách
```

## 6 agent mặc định

| Agent | Trách nhiệm |
|---|---|
| **PM** | Phân tích yêu cầu, khóa phạm vi, lập task/subtask, dependency và lịch sản xuất. |
| **Biên kịch** | Viết mở–thắt–cao trào–kết–bài học, chia trang và viết lời thoại đầy đủ ý. |
| **Thiết kế nhân vật** | Tạo hồ sơ nhân vật, khóa phong cách, anchor cố định và ảnh tham chiếu. |
| **Họa sĩ** | Ghép prompt từ kịch bản/anchor, tạo bìa và từng trang, chừa vùng đặt bóng thoại. |
| **Kiểm duyệt** | Kiểm tra từng đầu ra, an toàn độ tuổi, tính nhất quán và trả lỗi về đúng agent. |
| **Biên tập & dàn trang** | Gắn bóng thoại, hoàn thiện bìa và ghép PDF từ nội dung đã đạt kiểm duyệt. |

Biên tập không thực hiện quality gate tổng thể. Việc kiểm duyệt thuộc trách nhiệm của agent **Kiểm duyệt**.

## Yêu cầu môi trường

- Windows 10 hoặc 11.
- Python 3.11 trở lên.
- Node.js 20 trở lên.
- 9Router đang chạy tại `http://localhost:20128/v1` hoặc một địa chỉ tương thích OpenAI API.

## Cài đặt lần đầu

### 1. Cài backend

Mở Terminal PowerShell:

```powershell
Set-Location 'D:\Truyen_tranh'
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

### 2. Cài frontend

```powershell
Set-Location 'D:\Truyen_tranh\frontend'
npm install
```

### 3. Cấu hình môi trường

Tạo file `.env` từ `.env.example`, sau đó cấu hình:

```env
NINE_ROUTER_BASE_URL=http://localhost:20128/v1
NINE_ROUTER_API_KEY=your-api-key
NINE_ROUTER_MODELS=cx/gpt-5.6-sol,ag/gemini-3.8-flash-medium,gc/gemini-3-pro-preview
NINE_ROUTER_IMAGE_MODEL=ag/gemini-3-pro-image-preview

APP_HOST=127.0.0.1
APP_PORT=8000
FRONTEND_ORIGIN=http://localhost:5173
MAX_REVISIONS=3
LLM_TIMEOUT_SECONDS=180
```

Thứ tự trong `NINE_ROUTER_MODELS` là:

```text
Model chính → fallback 1 → fallback 2
```

Hệ thống chỉ chuyển sang model tiếp theo khi model trước gặp lỗi quota, token hoặc rate limit.

## Chạy dự án

Mở hai cửa sổ Terminal PowerShell riêng biệt.

### Terminal 1 — Backend

```powershell
Set-Location 'D:\Truyen_tranh'; .\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

### Terminal 2 — Frontend

```powershell
Set-Location 'D:\Truyen_tranh\frontend'; npm run dev
```

Sau khi khởi động:

- Dashboard: `http://localhost:5173`
- API: `http://localhost:8000`
- API docs: `http://localhost:8000/docs`

> Với PowerShell cũ, không dùng `cd /d` hoặc `&&`. Hãy dùng `Set-Location` và dấu `;` như các lệnh phía trên. Đường dẫn đúng là `D:\Truyen_tranh`, không phải `D:\Truyen\_tranh`.

## Các đường dẫn giao diện

| Màn hình | URL |
|---|---|
| Trang chủ | `/` |
| Quản lý model 9Router | `/models` |
| Tổng quan dự án | `/projects/{project_id}/overview` |
| List + Workflow | `/projects/{project_id}/list` |
| Lịch sản xuất | `/projects/{project_id}/schedule` |
| Giao tiếp | `/projects/{project_id}/messages` |
| Quản lý agent | `/projects/{project_id}/agents` |
| Sản phẩm | `/projects/{project_id}/artifacts` |

Có thể tải lại trang hoặc sử dụng nút Back/Forward của trình duyệt mà vẫn giữ đúng dự án và chức năng đang mở.

## List, workflow và Testing

Tab **List** kết hợp danh sách công việc và workflow theo kiểu Plane/Jira:

- Task chính và subtask cụ thể cho từng agent.
- Dependency giữa các công việc.
- Pipeline theo thứ tự sản xuất.
- Tìm kiếm và lọc theo trạng thái.
- Các trạng thái: `Sẵn sàng`, `Đang làm`, `Testing`, `Chờ duyệt`, `Bị chặn`, `Hoàn tất`.
- PM và agent cập nhật task/subtask tự động.

Khi một đầu ra hoàn thành:

1. Task chuyển sang `Testing`.
2. Agent Kiểm duyệt kiểm tra nội dung hoặc file ảnh.
3. Nếu đạt, task chuyển sang `Hoàn tất`.
4. Nếu có lỗi nghiêm trọng, hệ thống tạo ticket và giao lại agent sở hữu đầu ra.
5. Lỗi nhỏ được ghi chú nhưng vẫn cho đạt.

Ví dụ: Họa sĩ tạo xong ảnh trang 4 thì ảnh trang 4 được kiểm ngay, không cần đợi tạo xong toàn bộ truyện.

## Giao tiếp và sản phẩm theo từng tin nhắn

Mỗi sự kiện sản xuất liên kết bằng `artifact_ids` với đúng sản phẩm được tạo trong bước đó.

Ví dụ:

- Tin nhắn “Hoàn thành ảnh trang 4” chỉ hiển thị ảnh trang 4.
- Tin nhắn “Hoàn thành ảnh bìa” chỉ hiển thị ảnh bìa.
- Tin nhắn “PDF đã sẵn sàng” chỉ hiển thị PDF.

Khi dự án đang chạy, nội dung tin nhắn chỉ được xem. Muốn chỉnh sửa hoặc giao agent làm lại, cần bấm **Tạm dừng** trước.

## Tạm dừng, can thiệp và duyệt nội dung

- **Tạm dừng:** chờ agent kết thúc bước an toàn hiện tại rồi lưu trạng thái.
- **Tiếp tục:** chạy tiếp từ checkpoint gần nhất.
- **Dừng hẳn:** dừng dự án đang chạy để có thể xóa.
- **Can thiệp:** khi dự án đã tạm dừng, mở tin nhắn và giao đúng agent xử lý lại.
- **Duyệt nội dung:** có thể bật cho Kịch bản, Thiết kế nhân vật, Minh họa và PDF cuối.
- **Yêu cầu sửa:** ghi phản hồi và chọn agent cần xử lý.

Không có chức năng thay ảnh thủ công. Khi ảnh chưa đạt, agent Thiết kế nhân vật hoặc Họa sĩ sẽ tự tạo lại.

## Bóng thoại và lời thoại

- Biên kịch được yêu cầu viết câu tự nhiên, đầy đủ ý, thường dài 7–22 từ.
- Mỗi trang thường có 1–3 lượt thoại để tránh che tranh.
- Khi dàn trang, hệ thống ưu tiên vùng ít chi tiết và vùng trống do Họa sĩ chuẩn bị.
- Trang nhiều lời thoại sử dụng vùng thoại riêng để hạn chế đè lên nhân vật.
- Trang sau dàn thoại tiếp tục được đưa qua Testing.

## Quản lý agent

Mỗi dự án có 6 agent lõi không thể xóa. Có thể thêm tối đa 10 agent chuyên gia để tư vấn theo một vai trò riêng.

Trong tab **Agent**, có thể:

- Thêm, bật, tắt hoặc xóa agent bổ sung.
- Chọn model chính từ danh sách 9Router.
- Chọn nhiều model fallback.
- Chọn model ảnh cho Thiết kế nhân vật hoặc Họa sĩ.
- Điều chỉnh temperature.

Thứ tự gọi model của một agent:

```text
Model riêng của agent → fallback riêng → fallback toàn hệ thống
```

## Quản lý model 9Router toàn hệ thống

Mở `http://localhost:5173/models` hoặc chọn **Model 9Router** ở thanh bên.

Trang này cho phép:

- Đồng bộ catalog model trực tiếp từ 9Router.
- Chọn model chính.
- Thêm hoặc xóa model fallback.
- Thay đổi thứ tự fallback.
- Chọn model tạo ảnh mặc định.
- Lưu cấu hình cho toàn bộ dự án.

Cấu hình được lưu trong SQLite và vẫn tồn tại sau khi khởi động lại backend. API key chỉ được sử dụng ở backend và không gửi ra giao diện.

## Xóa dự án

- Dự án đang chạy phải được **Dừng hẳn** trước khi xóa.
- Khi xác nhận xóa, backend xóa bản ghi SQLite và toàn bộ artifact của riêng dự án.
- Không thể khôi phục sau khi xóa.

## Dữ liệu và sản phẩm

```text
backend/data/comicflow.db       Cơ sở dữ liệu SQLite
backend/data/artifacts/         Ảnh, JSON, contact sheet và PDF
```

Các thư mục runtime đã được đưa vào `.gitignore` và không nên commit.

## Kiểm tra dự án

### Backend

```powershell
Set-Location 'D:\Truyen_tranh'
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check backend tests
```

### Frontend

```powershell
Set-Location 'D:\Truyen_tranh\frontend'
npm run build
```

## Cấu trúc thư mục

```text
backend/
  app/
    agents/           6 agent lõi và agent tư vấn
    services/         9Router, tạo ảnh và dàn trang PDF
    db.py             SQLite, task, Testing, artifact và audit
    main.py           FastAPI và API điều khiển dự án
    workflow.py       LangGraph routing và vòng lặp sửa lỗi
  data/               dữ liệu runtime

frontend/
  src/
    App.tsx           dashboard và định tuyến giao diện
    api.ts            kết nối FastAPI
    styles.css        giao diện và hiệu ứng Live Production
```

## Xử lý lỗi thường gặp

### PowerShell báo `&& is not a valid statement separator`

Dùng dấu `;`:

```powershell
Set-Location 'D:\Truyen_tranh\frontend'; npm run dev
```

### Không kết nối được 9Router

Kiểm tra:

- 9Router có đang chạy tại `NINE_ROUTER_BASE_URL` không.
- `NINE_ROUTER_API_KEY` đã được cấu hình chưa.
- Model đã chọn có xuất hiện trong trang `/models` không.
- Model ảnh có hỗ trợ tạo ảnh không.

### Cổng 8000 hoặc 5173 đang được sử dụng

Đóng tiến trình cũ đang chạy trên cổng đó, sau đó chạy lại backend hoặc frontend.

### Dự án ở trạng thái `failed`

Mở dự án, xem lỗi và tin nhắn Testing gần nhất, sau đó bấm **Tiếp tục từ bước này**. Nếu cần chỉnh nội dung trước, hãy tạm dừng dự án và giao lại đúng agent.

## Bảo mật

- Không commit file `.env`.
- Không ghi API key thật vào README hoặc mã nguồn.
- Nếu API key từng bị chia sẻ công khai, hãy thu hồi và tạo key mới.
- Chỉ mở backend ra mạng bên ngoài khi đã thêm xác thực và giới hạn quyền truy cập.
