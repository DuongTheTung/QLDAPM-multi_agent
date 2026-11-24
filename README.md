# ComicFlow

ComicFlow là hệ thống sản xuất truyện tranh tự động theo mô hình đa agent, xây dựng bằng **LangGraph**, **9Router**, **FastAPI** và **React**. Người dùng chỉ cần nhập một yêu cầu duy nhất; hệ thống tự lập kế hoạch, viết kịch bản, thiết kế nhân vật, tạo tranh, kiểm duyệt, dàn trang và xuất PDF.

Phiên bản hiện tại có 6 agent mặc định, hỗ trợ thêm agent theo vai trò, chạy song song, theo dõi tiến độ thực, can thiệp thủ công và duyệt nội dung ngay trong luồng giao tiếp.

## Chức năng chính

- Tạo trọn bộ truyện tranh từ một yêu cầu đầu vào.
- 6 agent mặc định tự giao việc, kiểm tra và phản hồi cho nhau.
- Thêm agent hỗ trợ cho 5 vai trò chuyên môn; PM luôn là agent điều phối duy nhất.
- Chia việc song song giữa các agent cùng vai trò để rút ngắn thời gian xử lý.
- Theo dõi task, subtask, dependency, trạng thái và lịch sản xuất trong **List**.
- Kiểm tra từng đầu ra ngay sau khi hoàn thành, không đợi toàn bộ dự án.
- Duyệt thủ công riêng cho kịch bản, thiết kế nhân vật, minh họa và PDF cuối.
- Tạm dừng để sửa nội dung hoặc yêu cầu agent làm lại; tiếp tục từ điểm lưu an toàn.
- Tiếp tục dự án từ bước lỗi nếu hệ thống không thể tự phục hồi.
- Dừng hẳn dự án trước khi xóa dự án đang chạy.
- Chọn model cho từng agent khi tạo dự án hoặc thay đổi trong lúc dự án đang chạy.
- Quản lý chuỗi model mặc định của 9Router ở cấp toàn hệ thống.
- Giao diện luồng trực tiếp thể hiện rõ trạng thái gửi, nhận, xử lý, kiểm duyệt và hoàn thành.
- Xuất ảnh bìa, ảnh từng trang, trang truyện đã dàn và PDF hoàn chỉnh.

## Kiến trúc sản xuất

```text
Yêu cầu người dùng
        │
        ▼
       PM ── lập kế hoạch, task, subtask và lịch
        │
        ▼
   Biên kịch ── kịch bản chia theo trang
        │
        ▼
Thiết kế nhân vật ── hồ sơ, khóa phong cách, ảnh tham chiếu
        │
        ▼
     Họa sĩ ── bìa và ảnh từng trang
        │
        ▼
Biên tập & dàn trang ── ghép tranh với khối văn bản riêng
        │
        ▼
       PDF ── PM xác nhận hoàn thành
```

Agent **Kiểm duyệt** là một luồng kiểm tra độc lập, không phải công đoạn sản xuất thay cho các agent khác:

```text
Đầu ra thuộc phần không bật duyệt thủ công
        └─► Kiểm duyệt tự động từng đơn vị
                ├─ ĐẠT ─► tiếp tục
                └─ CHƯA ĐẠT ─► trả đúng agent sửa

Sản phẩm thuộc phần đã bật duyệt thủ công
        └─► Bỏ qua Kiểm duyệt tự động ─► chuyển cho người dùng
                                                ├─ Duyệt ─► khóa sản phẩm, đi tiếp
                                                └─ Làm lại ─► trả agent được chỉ định
```

Khi một phần đã được người dùng duyệt, Kiểm duyệt không kiểm tra lại và không được yêu cầu agent sửa phần đó. Riêng minh họa đã được người dùng duyệt sẽ chuyển thẳng sang Biên tập & dàn trang.

## 6 agent mặc định

| Agent | Trách nhiệm |
|---|---|
| **PM** | Phân tích yêu cầu, khóa phạm vi, tạo task/subtask, dependency, lịch và điều phối toàn bộ dự án. |
| **Biên kịch** | Viết cốt truyện có mở–thắt–cao trào–kết–bài học, chia trang và viết đoạn kể đầy đủ, phù hợp lứa tuổi. |
| **Thiết kế nhân vật** | Tạo hồ sơ nhân vật, khóa phong cách, tạo mô tả cố định cho nhân vật/bối cảnh và ảnh tham chiếu. Không vẽ trang truyện. |
| **Họa sĩ** | Ghép prompt từ kịch bản và mô tả đã khóa, tạo ảnh bìa và từng trang. Không đổi kịch bản hoặc ngoại hình nhân vật. |
| **Kiểm duyệt** | Kiểm tra từng đầu ra, độ an toàn theo tuổi, tính nhất quán và mức trung thành với kịch bản; trả lỗi nghiêm trọng về đúng agent. |
| **Biên tập & dàn trang** | Đặt tranh và văn bản kể ở hai vùng riêng, hoàn thiện bìa, dàn từng trang và ghép PDF. Không tự viết lại hoặc vẽ lại. |

Chính sách kiểm duyệt mặc định là **cho đạt**. Chỉ lỗi nghiêm trọng như thiếu/hỏng file, nội dung không an toàn, sai kịch bản đã khóa hoặc thay đổi ngoại hình nhân vật mới bị trả lại. Lỗi nhỏ được ghi chú nhưng không làm dừng tiến trình.

## Cách trình bày truyện

ComicFlow không dùng bóng thoại đè lên tranh. Mỗi trang hoàn chỉnh được bố trí theo dạng:

- Một vùng dành riêng cho hình minh họa.
- Một vùng dành riêng cho đoạn văn kể chuyện.
- Ảnh gốc không chứa chữ, ký tự, watermark hoặc bóng thoại.
- Văn bản được dàn ngoài ảnh để không che nhân vật và vẫn kể đủ diễn biến.

## Duyệt nội dung theo yêu cầu

Có thể bật duyệt thủ công cho một hoặc nhiều phần:

| Phần duyệt | Agent tạo sản phẩm | Sau khi người dùng duyệt |
|---|---|---|
| Kịch bản | Biên kịch | Khóa kịch bản và chuyển sang Thiết kế nhân vật. |
| Thiết kế nhân vật | Thiết kế nhân vật | Khóa hồ sơ, phong cách và ảnh tham chiếu. |
| Minh họa | Họa sĩ | Bỏ qua kiểm duyệt tự động của phần minh họa và chuyển thẳng sang dàn trang. |
| Bản truyện hoàn chỉnh | Biên tập & dàn trang | PM hoàn tất dự án. |

Ví dụ: chỉ bật duyệt **Thiết kế nhân vật**, **Minh họa** và **Bản cuối**:

1. Kịch bản được Kiểm duyệt tự động kiểm tra.
2. Thiết kế nhân vật chuyển thẳng cho người dùng duyệt.
3. Bộ minh họa chuyển thẳng cho người dùng duyệt, không qua Kiểm duyệt tự động.
4. Minh họa đã duyệt không bị Kiểm duyệt kiểm tra lại.
5. Biên tập dàn trang và PDF cuối tiếp tục chờ người dùng duyệt.

Trong tab **Giao tiếp**, bấm vào tin nhắn để xem đúng nội dung hoặc sản phẩm của công việc đó. Khi dự án chưa tạm dừng, người dùng chỉ có quyền xem hoặc duyệt. Muốn sửa trực tiếp hay giao agent làm lại, cần tạm dừng dự án trước.

## Tiến độ theo thời gian thực

Tiến độ không còn được nội suy từ tiến độ chung của dự án. Backend lưu phần trăm riêng cho từng agent và cập nhật theo đơn vị công việc thực tế:

- PM và Biên kịch cập nhật theo các mốc lập kế hoạch, tạo nội dung và lưu kết quả.
- Thiết kế nhân vật cập nhật theo từng ảnh tham chiếu.
- Họa sĩ cập nhật theo prompt, bìa và từng trang ảnh được tạo/kiểm tra.
- Kiểm duyệt cập nhật theo từng đầu ra đang kiểm tra.
- Biên tập cập nhật theo bìa, từng trang dàn và bước tạo PDF.
- Agent hỗ trợ có tiến độ riêng, không dùng chung phần trăm với agent lõi.

Frontend đồng bộ định kỳ nên thẻ agent sẽ tăng dần theo số đầu ra thực tế. Tiến độ này phản ánh các mốc mà hệ thống quan sát được; thời gian chờ một lần gọi model hoặc tạo ảnh không thể hiện phần trăm token nội bộ của nhà cung cấp.

## Giao diện quản lý

### Trang chủ

- Hiển thị các dự án gần đây.
- Tạo dự án mới từ một yêu cầu tiếng Việt.
- Chọn model cho 6 agent mặc định.
- Thêm trước các agent hỗ trợ và chọn model riêng cho từng agent.
- Nếu không chọn dự án, hệ thống luôn trở về giao diện trang chủ.

### Luồng trực tiếp

- Dùng hình robot 2D trung tính cho các agent.
- Chỉ hiển thị các agent đang phối hợp hoặc đang làm việc.
- Phân biệt rõ: đang gửi, đang nhận, đã bàn giao, đã nhận, đang làm, đang kiểm duyệt, chờ bạn duyệt và hoàn thành.
- Khi một lượt giao tiếp kết thúc, agent gửi không còn nhiệm vụ sẽ rời khỏi tín hiệu; chỉ agent đang xử lý còn hiển thị.
- Phân biệt rõ **tạm dừng** và **dừng hẳn** dự án.

### Đội sản xuất

- Sắp xếp theo thứ tự: PM → Biên kịch → Thiết kế nhân vật → Họa sĩ → Kiểm duyệt → Biên tập & dàn trang.
- Agent hỗ trợ đứng cạnh agent cùng vai trò.
- Hiển thị tên, vai trò, trạng thái và tiến độ thực của từng agent.
- Tên được ưu tiên; vai trò chỉ là thông tin phụ để tránh lặp nội dung.

### List và lịch

- Task và subtask cụ thể do PM lập.
- Dependency và thứ tự xử lý giữa các công việc.
- Trạng thái: chờ, đang làm, kiểm duyệt/chờ duyệt, hoàn tất hoặc cần làm lại.
- Lịch sản xuất đồng bộ với cùng task/subtask của PM.

### Giao tiếp

- Theo dõi lịch sử trao đổi giữa các agent.
- Mỗi tin nhắn chỉ mở sản phẩm thuộc đúng công việc đó, ví dụ ảnh trang 4 chỉ hiện ảnh trang 4.
- Nội dung có cấu trúc được trình bày thành văn bản dễ đọc thay cho JSON thô.
- Duyệt hoặc yêu cầu làm lại ngay tại tin nhắn đang chờ duyệt.
- Khi dự án đã tạm dừng, có thể chỉnh nội dung và gửi yêu cầu can thiệp cho agent.

### Sản phẩm

- Hiển thị ảnh tham chiếu, ảnh bìa, từng trang, kết quả kiểm duyệt và PDF.
- Mỗi sản phẩm kèm tên agent thực hiện; vai trò được hiển thị nhẹ hơn khi cần.
- Có thể mở hoặc tải từng file độc lập.

## Quản lý agent

Mỗi dự án luôn có 6 agent lõi và không thể xóa các agent này. Có thể thêm agent hỗ trợ thuộc một trong 5 vai trò:

- Biên kịch
- Thiết kế nhân vật
- Họa sĩ
- Kiểm duyệt
- Biên tập & dàn trang

PM chia đơn vị công việc cho các agent cùng vai trò. Ví dụ, nếu có hai Họa sĩ thì các trang được phân bổ giữa hai agent và có thể tạo song song; mỗi agent vẫn dùng cùng kịch bản, style lock và anchor đã khóa để giữ tính nhất quán.

Quy tắc quản lý:

- Chỉ được **thêm agent mới** khi dự án đang tạm dừng hoặc khi cấu hình dự án mới.
- Có thể đổi tên, hướng dẫn, trạng thái và model của agent mà không cần tạm dừng.
- Chỉ agent bổ sung mới có thể bị xóa; 6 agent lõi được bảo vệ.
- Có thể chọn model chính, chuỗi model dự phòng, model ảnh và nhiệt độ cho từng agent.
- Khi thêm nhiều agent cùng vai trò, PM tự chia công việc; agent không tự thay đổi phạm vi vai trò.

## Quản lý model 9Router

Chuỗi model mặc định:

```text
cx/gpt-5.6-sol
ag/gemini-3.8-flash-medium
gc/gemini-3-pro-preview
```

Model đầu tiên là model chính. Hệ thống chỉ chuyển sang model tiếp theo khi gặp lỗi hạn mức, hết token hoặc giới hạn tần suất; không chuyển model chỉ vì lỗi nội dung thông thường.

Trang `/models` cho phép:

- Đồng bộ danh sách model từ 9Router.
- Chọn và sắp xếp chuỗi model mặc định.
- Chọn model tạo ảnh.
- Lưu cấu hình cho các dự án mới.

Model riêng của agent được ưu tiên hơn cấu hình toàn hệ thống.

## Yêu cầu môi trường

- Windows 10 hoặc Windows 11.
- Python 3.11 trở lên.
- Node.js 20 trở lên.
- 9Router đang chạy tại `http://localhost:20128/v1` hoặc một địa chỉ tương thích OpenAI API.

Dự án chạy trực tiếp bằng terminal, không yêu cầu Docker và không dùng file `.ps1`.

## Cài đặt lần đầu

### 1. Cài backend

Mở một cửa sổ PowerShell:

```powershell
Set-Location 'D:\Truyen_tranh'
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
```

### 2. Cài frontend

Mở terminal tại thư mục dự án:

```powershell
Set-Location 'D:\Truyen_tranh\frontend'
npm install
```

### 3. Tạo cấu hình môi trường

```powershell
Set-Location 'D:\Truyen_tranh'
Copy-Item '.env.example' '.env'
```

Mở `.env` và thay khóa mẫu bằng khóa 9Router của bạn:

```dotenv
NINE_ROUTER_BASE_URL=http://localhost:20128/v1
NINE_ROUTER_API_KEY=your-nine-router-api-key
NINE_ROUTER_MODELS=cx/gpt-5.6-sol,ag/gemini-3.8-flash-medium,gc/gemini-3-pro-preview
NINE_ROUTER_IMAGE_MODEL=your-image-model

APP_ENV=development
APP_HOST=127.0.0.1
APP_PORT=8000
FRONTEND_ORIGIN=http://localhost:5173
MAX_REVISIONS=3
LLM_TIMEOUT_SECONDS=180
```

Không đưa `.env` lên Git. Tệp này đã được loại trừ trong `.gitignore`.

## Chạy dự án

Cần mở hai cửa sổ terminal riêng.

### Terminal 1 — Backend

```powershell
Set-Location 'D:\Truyen_tranh'
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

### Terminal 2 — Frontend

```powershell
Set-Location 'D:\Truyen_tranh\frontend'
npm run dev
```

Sau đó mở:

- Giao diện: `http://localhost:5173`
- API: `http://127.0.0.1:8000`
- Kiểm tra backend: `http://127.0.0.1:8000/api/health`

Vite tự chuyển tiếp `/api` và `/artifacts` sang backend tại cổng `8000`.

> Nếu dự án nằm ở thư mục khác, thay `D:\Truyen_tranh` trong các lệnh bằng đường dẫn thực tế.

## Cách sử dụng

1. Mở trang chủ và chọn **Tạo dự án mới**.
2. Nhập yêu cầu truyện, ví dụ chủ đề, lứa tuổi, số trang, phong cách và bài học.
3. Chọn model cho các agent nếu không muốn dùng cấu hình mặc định.
4. Thêm agent hỗ trợ nếu muốn chia việc song song.
5. Tạo dự án và theo dõi tại **Tổng quan**, **List**, **Lịch**, **Giao tiếp**, **Agent** và **Sản phẩm**.
6. Nếu muốn tự duyệt, bật các phần cần duyệt trong cài đặt dự án.
7. Khi cần can thiệp, bấm **Tạm dừng**, chờ hệ thống dừng tại điểm an toàn rồi mở **Giao tiếp**.
8. Khi hoàn tất chỉnh sửa hoặc giao lại việc, bấm **Tiếp tục**.
9. Tải PDF ở tab **Sản phẩm** sau khi dự án hoàn thành.

Ví dụ yêu cầu:

```text
Hãy tạo một truyện tranh 8 trang dành cho trẻ 7–10 tuổi về một chú sóc nhỏ
học cách giữ lời hứa. Phong cách hoạt hình 2D sáng sủa, bối cảnh khu rừng mùa thu,
diễn biến vui nhộn, an toàn, đoạn kể đầy đủ và kết thúc bằng bài học về trách nhiệm.
```

## Trạng thái dự án

| Trạng thái | Ý nghĩa | Thao tác phù hợp |
|---|---|---|
| `running` | Agent đang làm việc. | Theo dõi tiến độ hoặc yêu cầu tạm dừng. |
| `awaiting_approval` | Đang chờ người dùng duyệt một đầu ra. | Mở Giao tiếp để duyệt hoặc yêu cầu làm lại. |
| `paused` | Đã tạm dừng tại điểm lưu an toàn. | Chỉnh nội dung, can thiệp, thêm agent hoặc tiếp tục. |
| `failed` | Lỗi không thể tự phục hồi. | Bấm **Tiếp tục từ bước này** sau khi xử lý nguyên nhân. |
| `stopped` | Người dùng đã dừng hẳn dự án. | Có thể xóa dự án hoặc giữ lại dữ liệu. |
| `completed` | Đã tạo xong sản phẩm. | Xem và tải PDF. |

Muốn xóa dự án đang chạy, cần bấm **Dừng hẳn** trước. Việc xóa sẽ xóa dữ liệu dự án và các sản phẩm liên quan nên cần kiểm tra kỹ trước khi xác nhận.

## URL của giao diện

- `/` — Trang chủ.
- `/models` — Quản lý model 9Router.
- `/projects/{id}/overview` — Tổng quan và luồng trực tiếp.
- `/projects/{id}/list` — Task, subtask và workflow.
- `/projects/{id}/schedule` — Lịch sản xuất.
- `/projects/{id}/messages` — Giao tiếp và duyệt nội dung.
- `/projects/{id}/agents` — Quản lý agent.
- `/projects/{id}/artifacts` — Sản phẩm.

Mỗi chức năng có URL riêng nên tải lại trình duyệt vẫn giữ đúng dự án và đúng trang đang mở.

## Dữ liệu được lưu

- Cơ sở dữ liệu và trạng thái chạy: `backend/data/`
- Sản phẩm theo từng dự án: `backend/data/artifacts/<project-id>/`
- Ảnh tham chiếu và ảnh trang: trong thư mục artifact của dự án.
- Bản dàn trang cuối: `final/`
- PDF hoàn chỉnh: đường dẫn được lưu trong trường `final_pdf` của dự án.

Các thư mục dữ liệu runtime đã được loại khỏi Git.

## Kiểm tra chất lượng mã nguồn

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
Truyen_tranh/
├── backend/
│   ├── app/
│   │   ├── agents/       # PM, Biên kịch, Thiết kế, Họa sĩ, Kiểm duyệt, Biên tập
│   │   ├── services/     # 9Router, tạo ảnh và dàn trang
│   │   ├── db.py         # SQLite, agent, tiến độ, task, sự kiện, duyệt
│   │   ├── main.py       # FastAPI và các API điều khiển dự án
│   │   ├── manager.py    # Quản lý tiến trình nền
│   │   ├── schemas.py    # Kiểu dữ liệu và trạng thái workflow
│   │   └── workflow.py   # Đồ thị LangGraph
│   └── data/             # Dữ liệu runtime, không đưa lên Git
├── frontend/
│   ├── src/              # React, TypeScript và giao diện dashboard
│   └── vite.config.ts    # Proxy API và artifact
├── tests/                # Kiểm thử backend và workflow
├── .env.example          # Cấu hình mẫu, không chứa khóa thật
├── pyproject.toml        # Thư viện Python và công cụ phát triển
└── README.md
```

## Xử lý lỗi thường gặp

### PowerShell báo `&& is not a valid statement separator`

Không dùng lệnh kiểu CMD như `cd /d ... && ...` trong PowerShell cũ. Chạy từng dòng như hướng dẫn hoặc dùng dấu `;`:

```powershell
Set-Location 'D:\Truyen_tranh\frontend'; npm run dev
```

### Backend không kết nối được 9Router

1. Kiểm tra 9Router đang chạy tại địa chỉ trong `NINE_ROUTER_BASE_URL`.
2. Kiểm tra `NINE_ROUTER_API_KEY` trong `.env`.
3. Mở `http://127.0.0.1:8000/api/health`.
4. Mở `/models` và thử đồng bộ danh sách model.

### Dự án dừng ở `failed`

Đọc lỗi hiển thị trên dashboard, sửa cấu hình hoặc khởi động lại dịch vụ cần thiết, sau đó bấm **Tiếp tục từ bước này**. Hệ thống dùng trạng thái đã lưu để tiếp tục thay vì tạo lại dự án.

### Dự án đứng ở `awaiting_approval`

Mở tab **Giao tiếp**, tìm tin nhắn có nhãn chờ duyệt rồi chọn **Duyệt** hoặc **Yêu cầu làm lại**.

### Thêm agent bị từ chối

Tạm dừng dự án và chờ trạng thái chuyển sang `paused`, sau đó thêm agent. Đổi model của agent hiện có không yêu cầu tạm dừng.

### Frontend không gọi được API

Đảm bảo backend chạy ở `127.0.0.1:8000` và frontend chạy bằng `npm run dev` để proxy trong Vite hoạt động.

## Lưu ý bảo mật

- Không chia sẻ hoặc commit khóa 9Router.
- Nếu khóa đã từng xuất hiện trong lịch sử Git hoặc nơi công khai, hãy thu hồi và tạo khóa mới.
- Chỉ dùng `.env.example` cho cấu hình mẫu; khóa thật chỉ đặt trong `.env` cục bộ.
- Không công khai thư mục `backend/data/` nếu sản phẩm có nội dung riêng tư.
