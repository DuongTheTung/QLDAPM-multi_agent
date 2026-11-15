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
- Tạo ảnh bìa, ảnh từng trang, khối văn bản kể chuyện và PDF hoàn chỉnh.

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
| **Biên kịch** | Viết mở–thắt–cao trào–kết–bài học, chia trang và viết đoạn kể đầy đủ ý. |
| **Thiết kế nhân vật** | Tạo hồ sơ nhân vật, khóa phong cách, anchor cố định và ảnh tham chiếu. |
| **Họa sĩ** | Ghép prompt từ kịch bản/anchor và tạo bìa, từng trang không chứa chữ. |
| **Kiểm duyệt** | Kiểm tra từng đầu ra, an toàn độ tuổi, tính nhất quán và trả lỗi về đúng agent. |
| **Biên tập & dàn trang** | Đặt tranh và đoạn kể ở hai vùng riêng, hoàn thiện bìa và ghép PDF. |

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

## Dàn tranh và nội dung kể chuyện

- Mỗi trang có một đoạn kể hoàn chỉnh khoảng 60–110 từ, phù hợp độ tuổi.
- Tranh nằm ở cột bên trái, đoạn kể nằm trong cột riêng bên phải.
- Chữ không được vẽ hoặc chồng trực tiếp lên tranh nên không thể che nhân vật.
- Lời nhân vật, nếu có, được lồng tự nhiên trong đoạn kể bằng dấu ngoặc kép.
- Trang sau dàn tranh và chữ tiếp tục được đưa qua Testing.

## Quản lý agent

Mỗi dự án có hai nhóm agent:

| Nhóm | Chức năng | Có thể xóa? |
|---|---|---|
| **6 agent lõi** | Trực tiếp tạo sản phẩm: PM, Biên kịch, Thiết kế nhân vật, Họa sĩ, Kiểm duyệt, Biên tập & dàn trang. | Không |
| **Agent bổ sung** | Đóng vai chuyên gia tư vấn cho một dự án cụ thể trước khi sản xuất nội dung. | Có |

Một dự án có thể có tối đa 10 agent bổ sung. Agent bổ sung **không thay thế agent lõi** và không trực tiếp viết lại kịch bản, tạo ảnh, duyệt sản phẩm hoặc xuất PDF.

### Agent bổ sung làm gì?

Khi tạo agent, người dùng xác định ba thông tin quan trọng:

- **Tên:** tên hiển thị trong List, lịch và phần giao tiếp.
- **Vai trò:** lĩnh vực mà agent chịu trách nhiệm tư vấn, ví dụ lịch sử Việt Nam, tâm lý trẻ em hoặc giáo dục khoa học.
- **Hướng dẫn làm việc:** quy định cụ thể agent phải kiểm tra, điều cần khuyến nghị và điều phải tránh.

Mỗi agent bổ sung đọc:

- Yêu cầu ban đầu của người dùng.
- Kế hoạch sản xuất do PM tạo.
- Vai trò và hướng dẫn riêng đã được cấu hình.

Sau đó agent trả về ba nhóm thông tin:

```text
Khuyến nghị có thể thực hiện
Rủi ro cần tránh
Ghi chú bàn giao cho các agent lõi
```

Kết quả tư vấn được lưu vào trạng thái dự án và được đưa vào ngữ cảnh làm việc của **Biên kịch**, **Thiết kế nhân vật** và **Họa sĩ**. Các agent lõi vẫn chịu trách nhiệm cuối cùng đối với sản phẩm của mình.

### Agent bổ sung hoạt động ở thời điểm nào?

```text
PM lập kế hoạch
      │
      ▼
Các agent bổ sung lần lượt tư vấn
      │
      ▼
Biên kịch → Thiết kế nhân vật → Họa sĩ → Kiểm duyệt → Dàn trang
```

- Các agent bổ sung chạy sau PM và trước Biên kịch.
- Nếu có nhiều agent bổ sung, hệ thống gọi lần lượt từng agent và thu thập tất cả kết quả.
- Task tư vấn xuất hiện trong List và lịch; kịch bản phụ thuộc vào việc hoàn tất các task tư vấn này.
- Nếu một agent bổ sung gặp lỗi model, hệ thống ghi lại lỗi, bỏ qua tư vấn đó và tiếp tục workflow lõi. Agent tùy chọn không làm hỏng toàn bộ dự án.
- Agent được thêm hoặc bật lại chỉ tham gia khi workflow **đi qua giai đoạn tư vấn lần tiếp theo**. Nó không tự sửa những sản phẩm đã hoàn thành trước đó.

### Ví dụ agent bổ sung

| Vai trò | Nhiệm vụ nên giao |
|---|---|
| **Cố vấn lịch sử Việt Nam** | Kiểm tra niên đại, trang phục, kiến trúc, cách xưng hô và chi tiết văn hóa. |
| **Chuyên gia tâm lý trẻ em** | Kiểm tra thông điệp, mức độ đáng sợ, cách giải quyết xung đột theo độ tuổi. |
| **Cố vấn giáo dục khoa học** | Kiểm tra kiến thức khoa học và đề xuất cách giải thích dễ hiểu. |
| **Cố vấn văn hóa địa phương** | Kiểm tra phong tục, địa danh, biểu tượng và tránh mô tả sai lệch. |
| **Chuyên gia hài hước** | Đề xuất tình huống vui phù hợp độ tuổi nhưng không thay đổi cốt truyện trực tiếp. |

Ví dụ cấu hình:

```text
Tên: An
Vai trò: Cố vấn lịch sử Việt Nam
Hướng dẫn: Kiểm tra trang phục, kiến trúc, cách xưng hô và các chi tiết lịch sử.
Chỉ nêu lỗi có bằng chứng; ưu tiên đề xuất ngắn để Biên kịch và Họa sĩ áp dụng.
```

### Các thao tác trong tab Agent

Trong tab **Agent**, có thể:

- Thêm agent bổ sung với tên, vai trò, hướng dẫn và màu nhận diện.
- Tạm ngưng agent để agent không tham gia lần tư vấn tiếp theo.
- Kích hoạt lại agent đã tạm ngưng.
- Xóa agent bổ sung khỏi dự án. Việc xóa không xóa ngược những tư vấn đã được dùng trong sản phẩm cũ.
- Chọn model chính từ danh sách 9Router.
- Chọn nhiều model fallback.
- Chọn model ảnh cho hai agent lõi Thiết kế nhân vật hoặc Họa sĩ.
- Điều chỉnh temperature.

Agent lõi chỉ cho phép thay đổi cấu hình model; không thể đổi vai trò, tắt hoặc xóa. Agent bổ sung có thể quản lý đầy đủ.

### Cách agent sử dụng model

Thứ tự gọi model của một agent:

```text
Model riêng của agent → fallback riêng → fallback toàn hệ thống
```

- **Model chính:** model được gọi đầu tiên cho agent đó.
- **Fallback riêng:** chỉ được gọi khi model chính hết quota, token hoặc gặp lỗi định tuyến phù hợp.
- **Fallback toàn hệ thống:** lớp dự phòng cuối từ trang quản lý model 9Router.
- **Temperature thấp:** kết quả ổn định, phù hợp kiểm tra dữ kiện.
- **Temperature cao:** nhiều ý tưởng hơn, phù hợp tư vấn sáng tạo.

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
