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
- Kết quả kiểm duyệt chưa đạt không làm dự án chuyển sang `failed`; PM tự giao vòng sửa.
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

Biên tập không thực hiện quality gate tổng thể. Việc kiểm duyệt thuộc trách nhiệm của agent **Kiểm duyệt**. Kế hoạch và lịch do PM tạo không đi qua Testing; PM là bộ phận điều phối, không phải đối tượng kiểm duyệt.

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

Kiểm duyệt áp dụng chính sách mặc định là **Đạt**. Chỉ file hỏng/thiếu, nội dung không an toàn theo tuổi, sai nghiêm trọng kịch bản đã khóa hoặc thay đổi ngoại hình nhân vật mới bị trả lại. Khi bị trả lại, workflow vẫn chạy và PM tự giao vòng sửa cho đúng agent. Sau giới hạn vòng sửa, hệ thống lưu cảnh báo và tiếp tục thay vì làm dự án `failed`.

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

Workflow luôn giữ nguyên 6 lane: PM, Biên kịch, Thiết kế nhân vật, Họa sĩ, Kiểm duyệt và Biên tập. Agent được thêm không tạo một bước workflow mới; nó trở thành worker có **tên riêng** trong lane cùng vai trò.

### Năm vai trò có thể chọn

PM là đầu mối điều phối duy nhất nên không thể tạo thêm. Khi thêm agent, người dùng chọn một trong 5 vai trò:

| Vai trò | Cách agent mới hỗ trợ |
|---|---|
| **Biên kịch** | Tạo đề xuất cấu trúc, cảnh và rủi ro song song; Biên kịch chính tổng hợp bản cuối để giữ mạch truyện. |
| **Thiết kế nhân vật** | Chia các ảnh tham chiếu nhân vật cho nhiều agent tạo đồng thời, dùng chung style và anchor. |
| **Họa sĩ** | Chia các trang theo vòng tròn cho nhiều Họa sĩ tạo ảnh đồng thời. |
| **Kiểm duyệt** | Phân phối từng sản phẩm Testing cho các agent Kiểm duyệt đang bật. |
| **Biên tập & dàn trang** | Chia các trang cần ghép tranh và đoạn kể; Biên tập chính ghép PDF cuối. |

### Quản lý theo tên và vai trò

Mỗi agent có một `id` riêng, tên hiển thị và vai trò chuẩn hóa. List, lịch, tin nhắn, artifact và tiến độ hiển thị theo dạng:

```text
An · Họa sĩ
Mai · Kiểm duyệt
Linh · Biên tập & dàn trang
```

Workflow vẫn chỉ hiển thị một lane Họa sĩ, nhưng khi mở lane sẽ thấy subtask của từng người:

```text
Họa sĩ
├── Sáng · Họa sĩ mặc định: bìa, trang 1, 3, 5
└── An · Họa sĩ hỗ trợ: trang 2, 4, 6
```

Một lane chỉ hoàn tất khi mọi worker đã hoàn thành phần việc và các sản phẩm liên quan đã vượt qua Testing.

### Chạy song song

- Thiết kế nhân vật, Họa sĩ và Biên tập có thể xử lý nhiều file/trang đồng thời.
- Số yêu cầu ảnh đồng thời được giới hạn để tránh gây quá tải cho 9Router.
- Kết quả được ghép lại theo số trang, không phụ thuộc agent nào hoàn thành trước.
- Tất cả Họa sĩ dùng chung kịch bản, `style_lock`, character anchor và setting anchor.
- Mỗi ảnh hoàn thành được đưa vào Testing ngay, không chờ toàn bộ worker.
- Nếu chỉ có agent mặc định, hệ thống hoạt động tuần tự tương thích như trước.

### Thêm một agent

Khi tạo dự án mới, màn hình tạo dự án luôn hiển thị 6 agent mặc định và cho phép chọn model chính riêng cho từng agent mặc định. Người dùng còn có thể thêm trước tối đa 10 agent hỗ trợ và chọn model chính ngay trong biểu mẫu của từng agent; Họa sĩ và Thiết kế nhân vật còn có lựa chọn model ảnh. Các cấu hình được lưu trước khi workflow khởi động để PM có thể đưa tên của từng agent vào task/subtask ngay từ kế hoạch đầu tiên.

Biểu mẫu tạo agent gồm:

- **Tên agent:** danh tính hiển thị trong dự án.
- **Vai trò:** chọn từ 5 vai trò cố định.
- **Hướng dẫn và kỹ năng:** ưu tiên, phong cách hoặc ràng buộc riêng.
- **Màu nhận diện:** dùng trong List và lịch.
- **Model chính, fallback và temperature:** cấu hình riêng cho worker.
- **Model ảnh:** xuất hiện khi chọn Thiết kế nhân vật hoặc Họa sĩ.

Sau khi dự án khởi động, chỉ có thể thêm agent khi dự án ở trạng thái **Tạm dừng**. Agent được thêm sau khi dự án đã đi qua lane tương ứng sẽ tham gia khi workflow quay lại lane đó hoặc ở lần sản xuất tiếp theo; nó không tự thay đổi sản phẩm đã hoàn tất.

### Đổi tên, bật, tắt và xóa

- Có thể đổi tên agent hỗ trợ; task/subtask của agent được đồng bộ lại theo tên mới.
- Tạm ngưng agent để PM không giao thêm việc ở lần chạy tiếp theo.
- Kích hoạt lại để agent tham gia worker pool của vai trò.
- Xóa agent sẽ xóa work item chưa thực hiện của agent đó, nhưng không xóa artifact đã tạo trước đó.
- Chỉ thao tác **thêm agent mới** yêu cầu dự án ở trạng thái **Tạm dừng**.
- Đổi model, đổi tên, bật/tắt và xóa agent hỗ trợ có thể thực hiện mà không cần tạm dừng dự án.
- 6 agent mặc định chỉ cho phép thay đổi model; không thể đổi tên, tắt hoặc xóa.

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
