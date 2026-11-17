"""CMIT Housekeeping – Web V1 (Module 1): Upload, Validate, Run Cleaning, Summary, Preview, Download.

Chạy:  streamlit run app/streamlit_app.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
for p in (str(ROOT), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import streamlit as st  # noqa: E402

import services  # noqa: E402
from cleaning.engine import CleaningEngine, EngineSettings, precheck  # noqa: E402
from cleaning.errors import CleaningError  # noqa: E402
from cleaning.rules import RULES  # noqa: E402

st.set_page_config(page_title="CMIT Housekeeping – Module 1", layout="wide")

# Chế độ chạy thử công khai (Streamlit Community Cloud): không có đăng nhập nội bộ.
# Mỗi phiên trình duyệt có thư mục làm việc riêng (tên ngẫu nhiên). Giao diện không liệt kê
# lịch sử chạy của người khác.
BASE_WS = services.workspace_from_env(default=Path(tempfile.gettempdir()) / "cmit_housekeeping")
SETTINGS = EngineSettings.from_env()
STEPS = ["1. Upload", "2. Validate", "3. Run Cleaning", "4. Cleaning Summary", "5. Preview", "6. Download"]

# ---------------------------------------------------------------- session state
if "session_id" not in st.session_state:
    st.session_state.session_id = services.new_session_id()
    st.session_state.batch_id = services.new_batch_id()
    st.session_state.upload_key = 0
    st.session_state.precheck = None
    st.session_state.last_run_dir = None

WS = services.session_workspace(BASE_WS, st.session_state.session_id)


def _reset_batch() -> None:
    st.session_state.batch_id = services.new_batch_id()
    st.session_state.upload_key += 1
    st.session_state.precheck = None


def _clear_session_data() -> None:
    services.delete_workspace(WS)
    st.session_state.session_id = services.new_session_id()
    st.session_state.batch_id = services.new_batch_id()
    st.session_state.upload_key += 1
    st.session_state.precheck = None
    st.session_state.last_run_dir = None


def _run_selector(key: str) -> Path | None:
    """Chỉ hiển thị lần chạy do chính phiên này tạo ra. Không có lịch sử dùng chung."""
    last = st.session_state.last_run_dir
    if not last or not Path(last).is_dir():
        st.info("Chưa có lần chạy nào trong phiên này. Hãy chạy làm sạch ở bước 3.")
        return None
    run_dir = Path(last)
    st.caption(f"Lần chạy của phiên này: `{run_dir.name}`")
    return run_dir


# ---------------------------------------------------------------- sidebar
st.sidebar.title("CMIT Housekeeping")
st.sidebar.caption("Module 1 · Data Cleaning Engine")
step = st.sidebar.radio("Bước", STEPS, label_visibility="collapsed")
st.sidebar.divider()
st.sidebar.caption(f"Batch: `{st.session_state.batch_id}`")
st.sidebar.caption(f"DuckDB memory: {SETTINGS.memory_limit}")
st.sidebar.caption("Dữ liệu chỉ lưu trong phiên này. Đừng tải lên dữ liệu thật khi chưa được phê duyệt.")
if st.sidebar.button("Batch mới"):
    _reset_batch()
    st.rerun()
if st.sidebar.button("Xóa dữ liệu phiên này"):
    _clear_session_data()
    st.rerun()

st.title(step.split(". ", 1)[1])

# ---------------------------------------------------------------- 1. Upload
if step == STEPS[0]:
    st.write("Tải lên một hoặc nhiều file CSV. Tên file không bị giới hạn. Mỗi file phải có đủ 13 cột RAW.")
    uploads = st.file_uploader(
        "Chọn file CSV", type=["csv"], accept_multiple_files=True,
        key=f"uploader_{st.session_state.upload_key}",
    )
    if st.button("Lưu vào batch", disabled=not uploads, type="primary"):
        try:
            saved = services.save_uploads(uploads, st.session_state.batch_id, WS)
            st.session_state.precheck = None
            st.success(f"Đã lưu {len(saved)} file vào batch. File được đặt quyền chỉ đọc.")
        except CleaningError as exc:
            st.error(str(exc))

    current = services.list_batch_files(WS, st.session_state.batch_id)
    st.subheader(f"File trong batch ({len(current)})")
    if current:
        st.dataframe(
            [{"Tên file": p.name, "Dung lượng (MB)": round(p.stat().st_size / 1024 / 1024, 2)} for p in current],
            use_container_width=True, hide_index=True,
        )
    else:
        st.caption("Chưa có file nào.")

# ---------------------------------------------------------------- 2. Validate
elif step == STEPS[1]:
    files = services.list_batch_files(WS, st.session_state.batch_id)
    if not files:
        st.warning("Chưa có file trong batch. Hãy quay lại bước Upload.")
    else:
        st.write(f"Sẽ kiểm tra {len(files)} file. Không ghi kết quả ở bước này.")
        if st.button("Kiểm tra đầu vào", type="primary"):
            try:
                with st.spinner("Đang kiểm tra cấu trúc và Time Completed..."):
                    st.session_state.precheck = precheck(files, SETTINGS)
            except CleaningError as exc:
                st.session_state.precheck = None
                st.error(str(exc))

        pc = st.session_state.precheck
        if pc is not None:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Tổng dòng", f"{pc.rows_total:,}")
            c2.metric("Số file", len(pc.files))
            c3.metric("Dòng sai Time Completed", f"{pc.invalid_total:,}")
            c4.metric("Số tháng", len(pc.months))
            st.dataframe(
                [{
                    "File": f.name,
                    "Encoding": f.encoding,
                    "Số dòng": f.rows,
                    "Sai Time Completed": f.invalid_time_completed,
                    "Tháng (từ Time Completed)": ", ".join(f.months),
                } for f in pc.files],
                use_container_width=True, hide_index=True,
            )
            if pc.ok:
                st.success("Cấu trúc hợp lệ. Có thể chạy làm sạch.")
            else:
                st.error(
                    "Có dòng sai định dạng Time Completed. Hệ thống sẽ không chạy cho đến khi sửa dữ liệu "
                    "(yêu cầu dạng yy-Mon-dd HHMM, ví dụ 26-Oct-31 2358)."
                )

# ---------------------------------------------------------------- 3. Run Cleaning
elif step == STEPS[2]:
    files = services.list_batch_files(WS, st.session_state.batch_id)
    pc = st.session_state.precheck
    ready = bool(files) and pc is not None and pc.ok
    if not ready:
        st.warning("Cần kiểm tra đầu vào thành công ở bước Validate trước khi chạy.")

    st.write("Kết quả sẽ được ghi vào thư mục riêng theo Run ID, chỉ bạn xem được.")
    if st.button("Chạy làm sạch", disabled=not ready, type="primary"):
        bar = st.progress(0.0, text="Bắt đầu")

        def _progress(stage: str, message: str, fraction: float | None) -> None:
            bar.progress(min(max(fraction or 0.0, 0.0), 1.0), text=f"{stage}: {message}")

        try:
            result = CleaningEngine(progress=_progress, settings=SETTINGS).run(files, WS.outputs)
            st.session_state.last_run_dir = str(result.run_dir)
            s = result.stats
            st.success(f"Hoàn tất. Run ID: {result.run_id}")
            c1, c2, c3 = st.columns(3)
            c1.metric("Raw", f"{s.raw_total:,}")
            c2.metric("Clean", f"{s.clean_total:,}")
            c3.metric("Removed", f"{s.removed_total:,}")
            st.caption("Xem chi tiết ở bước 4. Cleaning Summary.")
        except CleaningError as exc:
            st.error(str(exc))
            st.caption("Manifest của lần chạy vẫn được ghi trong thư mục Run để kiểm toán.")
        except Exception as exc:  # lỗi ngoài dự kiến (ví dụ DuckDB hết bộ nhớ)
            st.error(f"Lỗi không mong đợi: {type(exc).__name__}: {exc}")

# ---------------------------------------------------------------- 4. Summary
elif step == STEPS[3]:
    run_dir = _run_selector("summary_run")
    if run_dir is not None:
        manifest = services.read_manifest(run_dir)
        counts = manifest.get("counts") or {}
        c = st.columns(5)
        c[0].metric("Raw", f"{counts.get('raw_total', 0):,}")
        c[1].metric("Clean", f"{counts.get('clean_total', 0):,}")
        c[2].metric("Removed", f"{counts.get('removed_total', 0):,}")
        c[3].metric("Đối soát", counts.get("reconciliation", "?"))
        c[4].metric("Trạng thái", manifest.get("status", "?"))
        if manifest.get("error"):
            st.error(manifest["error"])

        sheets = services.read_summary_sheets(run_dir)
        for title, key in [
            ("Theo file", "By_File"),
            ("Theo tháng (Time Completed)", "By_Month"),
            ("Theo rule", "By_Rule"),
            ("Số rule vi phạm đồng thời", "Rule_Overlap"),
            ("Cảnh báo", "Warnings"),
            ("Đối soát", "Reconciliation"),
        ]:
            st.subheader(title)
            st.dataframe(sheets[key], use_container_width=True, hide_index=True)

        with st.expander("Manifest (JSON)"):
            st.json(manifest)

# ---------------------------------------------------------------- 5. Preview
elif step == STEPS[4]:
    run_dir = _run_selector("preview_run")
    if run_dir is not None:
        dataset = st.radio("Tập dữ liệu", ["clean", "removed"], horizontal=True)
        sheets = services.read_summary_sheets(run_dir)
        month_options = sorted(sheets["By_Month"]["Tháng"].astype(str).tolist())
        months = st.multiselect("Lọc theo Report_Month", month_options)
        rules = []
        if dataset == "removed":
            rules = st.multiselect("Lọc theo Rule_ID (khớp nếu chứa mã)", [r.rule_id for r in RULES])
        limit = st.number_input("Số dòng xem trước", min_value=1, max_value=1000, value=200, step=50)

        try:
            df, total = services.preview(run_dir, dataset, months, rules, int(limit))
            st.caption(f"Khớp bộ lọc: {total:,} dòng. Đang hiển thị {len(df):,} dòng đầu.")
            st.dataframe(df, use_container_width=True, hide_index=True)
        except Exception as exc:
            st.error(f"Không xem trước được: {type(exc).__name__}: {exc}")

# ---------------------------------------------------------------- 6. Download
elif step == STEPS[5]:
    run_dir = _run_selector("download_run")
    if run_dir is not None:
        st.write("Tải về từng file của lần chạy. File gốc không bị thay đổi.")
        items = [
            ("clean_data.parquet", "clean", "application/octet-stream"),
            ("removed_data.parquet", "removed", "application/octet-stream"),
            ("cleaning_summary.xlsx", "summary", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            ("manifest.json", "manifest", "application/json"),
        ]
        for filename, dataset, mime in items:
            path = services.output_path(run_dir, dataset)
            if not path.exists():
                st.caption(f"Không có {filename}")
                continue
            size_mb = path.stat().st_size / 1024 / 1024
            st.download_button(
                f"Tải {filename} ({size_mb:,.1f} MB)",
                data=services.file_bytes(path),
                file_name=filename,
                mime=mime,
                key=f"dl_{run_dir.name}_{dataset}",
            )
