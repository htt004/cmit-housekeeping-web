# Triển khai CMIT Housekeeping Web V1 lên server nội bộ

Tài liệu này dành cho IT và người vận hành. Người dùng cuối chỉ cần mở một URL và đăng nhập trên trình duyệt. Không cần cài Python hay bất kỳ phần mềm nào trên máy cá nhân.

## 1. Chọn nơi đặt server (cần phê duyệt)

Dữ liệu là CSV vận hành nội bộ của cảng, nên nơi đặt server phải được IT và bộ phận bảo mật CMIT duyệt. Mình không chọn hosting công khai thay bạn.

| Phương án | Mô tả | Đánh giá |
|---|---|---|
| **A. Máy chủ Linux nội bộ CMIT** (khuyến nghị) | Một VM hoặc máy vật lý trong mạng CMIT, truy cập qua LAN hoặc VPN. | Dữ liệu không rời mạng nội bộ. Dễ kiểm soát. Cần IT cấp máy và DNS nội bộ. |
| **B. VM trong hạ tầng cloud riêng của CMIT** | Đặt trong VPC/VNet riêng, nối với mạng CMIT bằng VPN site-to-site hoặc private link. | Linh hoạt hơn A. Cần duyệt chính sách cloud và vị trí lưu trữ dữ liệu. |
| **C. Dịch vụ PaaS/cloud công khai** (ví dụ Streamlit Community Cloud) | Không dùng cho dữ liệu này. Các dịch vụ này mặc định công khai hoặc không kiểm soát được ai truy cập. | **Không khuyến nghị.** Chỉ cân nhắc khi bộ phận bảo mật phê duyệt bằng văn bản. |

Yêu cầu tối thiểu cho phương án A hoặc B:

- Hệ điều hành: Ubuntu Server 22.04 LTS hoặc 24.04 LTS.
- CPU 4 nhân, RAM 16 GB. Đây là mức phù hợp để chạy DuckDB với giới hạn 2 GB và xử lý 3–5 triệu dòng. Cần đo lại trên file thật.
- Ổ đĩa: tối thiểu 200 GB cho upload, kết quả và thư mục tạm của DuckDB. Nên dùng ổ mã hóa (LUKS hoặc BitLocker tùy hệ điều hành).
- Docker Engine và Docker Compose v2.
- Tên miền nội bộ, ví dụ `cmit-housekeeping.cmit.local`, trỏ về IP của server qua DNS nội bộ.
- Chứng chỉ TLS do CMIT cấp cho tên miền đó.

## 2. Kiến trúc và lý do

```
Người dùng (trình duyệt trong mạng CMIT/VPN)
        │ HTTPS 443
        ▼
[ proxy: Caddy ]  ── basic auth, TLS, gán header danh tính, giới hạn upload
        │ HTTP nội bộ (mạng Docker cmit_net)
        ▼
[ app: Streamlit + engine DuckDB ]  ── không publish cổng ra ngoài
        │
        ▼
[ volume cmit_data ]  /data/workspace/users/<hash>/{uploads,outputs}
```

- Chỉ proxy mở cổng 443. Container `app` không publish cổng, nên không ai truy cập trực tiếp được.
- Mỗi người dùng có workspace riêng. Người A không thấy file hay kết quả của người B.
- Ứng dụng từ chối truy cập nếu proxy không gán danh tính người dùng.
- File CSV và kết quả không được công khai dưới bất kỳ đường dẫn tĩnh nào. Chỉ có API của Streamlit, và chỉ sau khi đăng nhập.

## 3. Chuẩn bị server

```bash
# Ubuntu: cài Docker Engine và compose plugin theo tài liệu chính thức của Docker
sudo apt-get update && sudo apt-get install -y ca-certificates curl
# (cài Docker theo https://docs.docker.com/engine/install/ubuntu/)
docker --version && docker compose version

# Tường lửa: chỉ cho phép 443 từ mạng nội bộ, không mở 8501
sudo ufw default deny incoming
sudo ufw allow from 10.0.0.0/8 to any port 443 proto tcp     # thay bằng dải mạng CMIT thật
sudo ufw allow OpenSSH
sudo ufw enable
```

## 4. Đưa mã nguồn lên server

Chép thư mục dự án (không kèm `workspace/`, `.venv/`, CSV hay kết quả) vào `/opt/cmit-housekeeping`. Ví dụ:

```bash
sudo mkdir -p /opt/cmit-housekeeping && sudo chown "$USER" /opt/cmit-housekeeping
# từ máy có mã nguồn:
scp -r cmit_housekeeping_v3/* user@server:/opt/cmit-housekeeping/
```

Không đưa file CSV RAW lên server bằng cách copy thư mục. Người dùng tải lên qua giao diện.

## 5. Cấu hình

```bash
cd /opt/cmit-housekeeping
cp deploy/.env.example .env
nano .env            # đặt CMIT_HOST, CMIT_BIND_IP (nếu cần), CMIT_MEMORY_LIMIT
chmod 600 .env
```

Đặt chứng chỉ theo `deploy/certs/README.md`:

```bash
chmod 600 deploy/certs/cmit.key
```

Tạo tài khoản người dùng. Username phải là định danh dạng email hoặc tên nội bộ, chỉ gồm chữ thường, số và các ký tự `. _ % + - @`.

```bash
docker run --rm caddy:2.8-alpine caddy hash-password --plaintext 'MatKhauManh!2026'
```

Sao chép hash vào khối `basic_auth` trong `deploy/Caddyfile`, mỗi người một dòng. Không để mật khẩu thô trong file.

Kiểm tra cấu hình trước khi chạy:

```bash
docker compose config > /dev/null && echo "compose OK"
docker compose run --rm proxy caddy validate --config /etc/caddy/Caddyfile
```

## 6. Build và chạy

```bash
docker compose build
docker compose up -d
docker compose ps          # app phải ở trạng thái healthy sau khoảng 30 giây
docker compose logs -f app # Ctrl+C để thoát
```

## 7. Kiểm tra sau khi triển khai

Thực hiện các kiểm tra sau. Mỗi kiểm tra đều phải đạt.

1. Từ máy trong mạng CMIT, mở `https://<CMIT_HOST>`. Trình duyệt phải hỏi đăng nhập. Chứng chỉ phải hợp lệ, không có cảnh báo.
2. Không đăng nhập: `curl -sk -o /dev/null -w "%{http_code}\n" https://<CMIT_HOST>/` phải trả về `401`.
3. Cổng 8501 không truy cập được từ máy khác: `curl --max-time 5 http://<IP_server>:8501` phải thất bại.
4. Đăng nhập bằng tài khoản A, tải lên một file, chạy làm sạch. Sau đó đăng nhập bằng tài khoản B. Tài khoản B không được thấy batch hay Run ID của A.
5. Kiểm tra quyền file upload trong volume:
   ```bash
   docker compose exec app ls -la /data/workspace/users
   ```
   Mỗi thư mục người dùng có `owner.txt`, và file upload có quyền chỉ đọc.
6. Chạy thử với file mẫu thật. So số Raw, Clean, Removed với bảng đối chiếu đã có.

## 8. Quản lý người dùng

- **Thêm người dùng**: tạo hash mới, thêm dòng vào `basic_auth` trong `deploy/Caddyfile`, rồi chạy `docker compose restart proxy`.
- **Đổi mật khẩu**: tạo hash mới và thay dòng tương ứng, rồi restart proxy.
- **Khóa người dùng**: xóa dòng của người đó, rồi restart proxy.

Mật khẩu basic auth không có MFA. Nếu CMIT có hệ thống SSO (Azure AD, Keycloak, Google Workspace), nên đặt thêm `oauth2-proxy` phía trước Caddy. Cấu hình SSO chưa được xây dựng trong bản này và cần làm riêng sau khi IT chọn nhà cung cấp định danh.

## 9. Sao lưu, lưu giữ và dọn dữ liệu

**Sao lưu** (khuyến nghị hằng đêm): volume `cmit_data` chứa toàn bộ upload và kết quả. Ví dụ:

```bash
docker run --rm -v cmit-housekeeping_cmit_data:/data -v /backup:/backup alpine \
  tar czf /backup/cmit_data_$(date +%F).tar.gz -C /data .
```

Mã hóa bản sao lưu và lưu ở ổ khác hoặc máy khác. Thử khôi phục ít nhất mỗi quý.

**Lưu giữ**: dry-run để xem những gì sẽ bị xóa:

```bash
docker compose exec app python scripts/purge_workspace.py --days 30
```

Lệnh trên chỉ liệt kê các batch upload cũ hơn 30 ngày. Khi đã thống nhất thời hạn với bộ phận nghiệp vụ, thêm `--apply` để xóa. Kết quả (outputs) là bản ghi kiểm toán, chỉ xóa khi thêm `--include-outputs` và có quyết định rõ ràng.

Đặt lịch chạy hằng tuần bằng cron trên server, ví dụ:

```
0 2 * * 0 cd /opt/cmit-housekeeping && docker compose exec -T app python scripts/purge_workspace.py --days 30 --apply >> /var/log/cmit_purge.log 2>&1
```

## 10. Cập nhật phiên bản

```bash
cd /opt/cmit-housekeeping
# sao chép mã mới vào thư mục, giữ nguyên .env, deploy/certs và deploy/Caddyfile
docker compose build app
docker compose up -d app
```

Dữ liệu trong volume được giữ nguyên qua các lần cập nhật. Không chạy `docker compose down -v` trừ khi chủ động xóa dữ liệu.

## 11. Ước lượng tài nguyên

- `CMIT_MEMORY_LIMIT` (DuckDB) mặc định 2 GB. Container app giới hạn 6 GB (`CMIT_CONTAINER_MEM`).
- Khi DuckDB vượt giới hạn, nó ghi tràn ra thư mục tạm `/data/tmp`. Cần giữ đủ dung lượng trống, nên đo trên file thật trước khi chọn kích thước ổ.
- Nút tải về hiện đọc toàn bộ file vào bộ nhớ của app. Với file Parquet lớn, nên lấy trực tiếp từ volume khi cần.

## 12. Những điểm chưa được kiểm chứng

Các mục sau chưa chạy thật trong môi trường phát triển của mình. Cần kiểm tra trên server trước khi đưa người dùng vào.

- `docker compose build` và `docker compose up` chưa được chạy.
- Cú pháp `basic_auth` và `request_header {http.auth.user.id}` của Caddy 2.8 cần được xác nhận bằng `caddy validate` ở bước 5.
- `st.context.headers` cần Streamlit từ 1.37 trở lên. Phiên bản trong `requirements.txt` chưa được cài và kiểm tra.
- Giao diện Streamlit chưa được khởi chạy. Test xác thực và workspace theo người dùng đã pass (81 test), nhưng chưa có kiểm tra end-to-end qua trình duyệt.
- `requirements.txt` còn dùng ràng buộc phiên bản tối thiểu. Sau khi cài thành công, nên ghim phiên bản cụ thể để build có thể tái lập.

## 13. Danh sách kiểm tra bảo mật trước khi go-live

- [ ] Server nằm trong mạng nội bộ hoặc VPN CMIT, đã được IT và bảo mật phê duyệt.
- [ ] Chỉ cổng 443 mở, cổng 8501 không truy cập được từ bên ngoài container.
- [ ] Chứng chỉ TLS hợp lệ, khóa riêng có quyền 600, không nằm trong git.
- [ ] `.env` và mật khẩu không nằm trong git. Trong `Caddyfile` chỉ có hash.
- [ ] Ổ đĩa và bản sao lưu được mã hóa.
- [ ] Đã thử đăng nhập sai, thử truy cập trực tiếp cổng app, thử hai tài khoản cách ly dữ liệu.
- [ ] Đã thống nhất thời hạn lưu giữ dữ liệu với bộ phận nghiệp vụ.
- [ ] Đã có quy trình sao lưu và thử khôi phục.
- [ ] Có người phụ trách thêm, khóa tài khoản và theo dõi log `docker compose logs proxy`.
