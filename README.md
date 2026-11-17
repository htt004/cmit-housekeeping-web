# CMIT Housekeeping/Shifting – Module 1 (v3.0.0) + Web V1 (Streamlit)

Làm sạch dữ liệu khai thác cảng theo 8 rule R01–R08, kèm giao diện Web V1 để tải lên, kiểm tra, chạy, xem và tải kết quả.
Chưa có Dashboard hay Phase 2.

## Cài đặt (Windows, Python 3.10+)

```bat
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Chạy giao diện Web V1

```bat
run_app.bat
```

Hoặc: `streamlit run app\streamlit_app.py`. Trình duyệt mở tại http://localhost:8501.

Các bước trên giao diện:

1. **Upload**: chọn một hoặc nhiều file CSV. Tên file không bị giới hạn. File được lưu vào batch và đặt quyền chỉ đọc.
2. **Validate**: kiểm tra cấu trúc 13 cột, encoding, số dòng, tháng và dòng sai Time Completed. Không ghi kết quả.
3. **Run Cleaning**: chạy làm sạch, có thanh tiến trình. Chỉ chạy khi bước Validate đạt.
4. **Cleaning Summary**: số liệu Raw/Clean/Removed, theo file, theo tháng, theo rule, cảnh báo, đối soát, manifest.
5. **Preview**: xem trước dữ liệu Clean hoặc Removed. Lọc theo tháng và Rule_ID. Tối đa 1.000 dòng mỗi lần.
6. **Download**: tải clean_data.parquet, removed_data.parquet, cleaning_summary.xlsx, manifest.json.

Thư mục workspace mặc định là `workspace\` cạnh dự án. Đổi bằng biến `CMIT_WORKSPACE`.
Giới hạn upload là 2 GB mỗi lần, cấu hình trong `.streamlit\config.toml`.

## Chạy từ dòng lệnh

```bat
python run_cleaning.py --input-dir "D:\Data\2026" --out "D:\Output"
python run_cleaning.py "D:\Data\bat_ky_ten.csv" --out "D:\Output" --memory-limit 4GB --temp-dir "D:\Temp\duck"
```

## Giới hạn bộ nhớ và thư mục temp

| Cài đặt | Biến môi trường | Tham số CLI | Mặc định |
|---|---|---|---|
| Giới hạn bộ nhớ DuckDB | `CMIT_MEMORY_LIMIT` | `--memory-limit` | `2GB` |
| Thư mục temp (khi DuckDB tràn bộ nhớ) | `CMIT_TEMP_DIR` | `--temp-dir` | `<thư mục Run>\_duckdb_tmp` (xóa sau khi chạy) |
| Số luồng | `CMIT_THREADS` | `--threads` | tự động |

DuckDB tự tràn ra thư mục temp khi vượt giới hạn bộ nhớ. Thời gian từng bước và cấu hình đã dùng được ghi trong `manifest.json`.

## Kiểm thử

```bat
run_tests.bat
```

Hoặc `python -m pytest -v -rs`. Test bị skip sẽ được ghi rõ lý do.

| Nhóm | File | Cần gì |
|---|---|---|
| Rule Python, sinh dữ liệu, service, ingest | `test_reference.py`, `test_synthetic.py`, `test_services.py`, `test_ingest.py` | chỉ Python |
| Rule trên DuckDB, luồng chính, precheck | `test_rules.py`, `test_engine.py` | `duckdb`, `openpyxl` |
| Đối chiếu với 3 file thật (Python) | `test_reference_real.py` | `set CMIT_TEST_DATA_DIR=...` |
| Integration trên 3 file thật (DuckDB) | `test_integration_real.py` | `set CMIT_TEST_DATA_DIR=...` |
| Scale 1–5 triệu dòng (DuckDB) | `test_scale.py` | `set CMIT_SCALE_ROWS=1000000` (hoặc 5000000) |

Ví dụ chạy scale 5 triệu dòng với giới hạn 1 GB:

```bat
set CMIT_SCALE_ROWS=5000000
set CMIT_MEMORY_LIMIT=1GB
python -m pytest tests\test_scale.py -s
```

Kết quả đo được in ra và ghi vào thư mục tạm của test.

Sinh dữ liệu tổng hợp để benchmark thủ công:

```bat
python scripts\generate_synthetic.py --rows 5000000 --out D:\Bench\5m
python run_cleaning.py --input-dir D:\Bench\5m\input --out D:\Bench\5m\out --memory-limit 1GB
```

Đối chiếu số tham chiếu của dữ liệu tổng hợp: `D:\Bench\5m\expected.json`.

## Quy tắc đầu vào

- **Tên file**: mọi tên `.csv`. Tên file chỉ dùng cho `Source_File`. Hai file cùng tên sẽ bị từ chối.
- **Cấu trúc**: đủ 13 cột RAW chuẩn. Chuẩn hóa tên cột chỉ khi khác khoảng trắng hoặc chữ hoa/thường. Không đoán cột thiếu. Cột thừa, cột lặp, cột thiếu đều báo lỗi.
- **Tháng**: lấy từ `Time Completed` theo `yy-Mon-dd HHMM` (ví dụ `26-Oct-31 2358` là 2026-10-31). Sai định dạng hoặc không phải ngày hợp lệ sẽ dừng lần chạy.
- **Encoding**: UTF-8 (có hoặc không BOM) và UTF-16 (có BOM).

## Quy tắc làm sạch (không thay đổi)

| Rule | Điều kiện |
|---|---|
| R01 | Move Kind = Other hoặc Shift O.B. |
| R02 | Fetch CHE Name trống và Move Kind = Load hoặc Delivery |
| R03 | Fetch CHE Name và Put CHE Name cùng trống |
| R04 | Fetch CHE Name = RTG16 hoặc RTG17 |
| R05 | Fetch CHE Name bắt đầu bằng QC và Put CHE Name trống |
| R06 | Put CHE Name trống và Move Kind = Discharge hoặc Receival |
| R07 | Put CHE Name = RTG16 hoặc RTG17 |
| R08 | Put CHE Name bắt đầu bằng QC và Fetch CHE Name trống |

## Đảm bảo an toàn dữ liệu

- **RAW không bị sửa**: file đầu vào chỉ được đọc. SHA-256 được tính trước và sau khi chạy.
- **Không ghi đè**: mỗi lần chạy một thư mục Run ID. Thư mục đã tồn tại sẽ báo lỗi.
- **Không xóa trùng lặp**: dòng trùng khóa chỉ được cảnh báo.
- **Đối soát bắt buộc**: Raw = Clean + Removed theo file, theo tháng và toàn bộ.
- **Lỗi không bị bỏ qua**: manifest luôn được ghi, kể cả khi thất bại.

## Cấu trúc dự án

```
cleaning/
  config.py      cấu trúc 13 cột, tên file, biến môi trường
  rules.py       8 rule dưới dạng SQL, chuẩn hóa, phân tích Time Completed
  ingest.py      kiểm tra file, encoding, cấu trúc cột
  audit.py       Run ID, SHA-256, manifest.json
  engine.py      CleaningEngine, EngineSettings, precheck
  summary.py     thống kê theo file và tháng, đối soát, Excel
  reference.py   rule bằng Python thuần, dùng để kiểm chứng
  synthetic.py   sinh dữ liệu tổng hợp có số tham chiếu
  errors.py      các loại lỗi
app/
  streamlit_app.py   giao diện Web V1
  services.py        lưu upload, danh sách Run, xem trước, không phụ thuộc Streamlit
scripts/generate_synthetic.py
run_cleaning.py      CLI
tests/
```

## Lưu ý

- Parquet được ghi trực tiếp bằng DuckDB, không cần pyarrow.
- Cột `Report_Month` là cột thêm vào đầu ra, không có trong RAW.
- Nút tải về đọc toàn bộ file vào bộ nhớ của máy chủ Streamlit. Với file Parquet lớn, nên dùng CLI hoặc lấy trực tiếp từ thư mục Run.
