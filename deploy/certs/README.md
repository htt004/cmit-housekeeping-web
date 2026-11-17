# Chứng chỉ TLS

Đặt hai file do IT CMIT cấp (CA nội bộ hoặc chứng chỉ của tổ chức):

- `cmit.crt` (chuỗi chứng chỉ đầy đủ, gồm cả CA trung gian nếu có)
- `cmit.key` (khóa riêng)

Không commit file `.key` lên git. File `.gitignore` đã loại trừ `deploy/certs/*.key`.
Quyền khuyến nghị trên Linux: `chmod 600 deploy/certs/cmit.key`.
