"""
B站视频语音转写工具 — Streamlit Web UI
启动方式: streamlit run app.py
"""
import os
import sys
import time
import logging
import traceback
import subprocess

import streamlit as st

# 确保当前目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.fetcher import BilibiliFetcher, VideoInfo
from core.transcriber import WhisperTranscriber
from core.state import StateManager, STATUS_DONE, STATUS_FAILED, STATUS_PENDING

# ============================================================
# 页面配置
# ============================================================
st.set_page_config(
    page_title="B站视频语音转写",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# 自定义 CSS
# ============================================================
st.markdown("""
<style>
    .status-done { color: #2ecc71; font-weight: bold; }
    .status-failed { color: #e74c3c; font-weight: bold; }
    .status-pending { color: #f39c12; }
    .status-running { color: #3498db; font-weight: bold; }
    .log-box {
        background: #1e1e1e; color: #d4d4d4; padding: 12px;
        border-radius: 6px; font-family: 'Consolas', monospace;
        font-size: 13px; max-height: 300px; overflow-y: auto;
    }
    .folder-picker-row {
        display: flex; align-items: center; gap: 8px;
    }
    div[data-testid="stSidebar"] .folder-picker-info {
        font-size: 0.85rem; color: #888; margin-top: -8px;
    }
</style>
""", unsafe_allow_html=True)

# ============================================================
# 文件夹选择器
# ============================================================
def pick_folder() -> str:
    """使用 tkinter 打开原生文件夹选择对话框"""
    script = '''
import tkinter as tk
from tkinter import filedialog
root = tk.Tk()
root.withdraw()
root.attributes('-topmost', True)
folder = filedialog.askdirectory(title="选择工作目录")
root.destroy()
print(folder)
'''
    try:
        result = subprocess.run(
            [sys.executable, '-c', script],
            capture_output=True, text=True, timeout=60
        )
        path = result.stdout.strip()
        return path if path and os.path.isdir(path) else ""
    except Exception as e:
        st.error(f"文件夹选择器失败: {e}")
        return ""


# ============================================================
# Session State 初始化
# ============================================================
def init_state():
    defaults = {
        "work_dir": "",
        "url_text": "",
        "video_list": [],       # List[dict] {bvid, title, duration, owner, pages, status}
        "fetcher": None,
        "state_mgr": None,
        "transcriber": None,
        "running": False,
        "logs": [],
        "current_bvid": "",
        "progress": 0.0,
        "folder_dialog_triggered": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()


def add_log(msg: str, level: str = "info"):
    """添加日志"""
    prefix = {"info": "ℹ️", "success": "✅", "warning": "⚠️", "error": "❌"}.get(level, "")
    ts = time.strftime("%H:%M:%S")
    st.session_state.logs.append(f"[{ts}] {prefix} {msg}")
    # 最多保留 200 条
    if len(st.session_state.logs) > 200:
        st.session_state.logs = st.session_state.logs[-200:]


# ============================================================
# 侧边栏 — 配置面板
# ============================================================
with st.sidebar:
    st.title("⚙️ 配置")

    # 工作目录选择
    st.subheader("📁 工作目录")

    # 文本输入行
    work_dir_input = st.text_input(
        "目录路径",
        value=st.session_state.work_dir,
        placeholder="例如: C:\\Users\\xxx\\Videos\\bilibili",
        help="video_output/ 和 video_temp/ 将在此目录下自动创建",
        key="work_dir_text_input",
    )

    # 文件夹选择按钮
    if st.button("📂 浏览文件夹...", use_container_width=True, disabled=st.session_state.running):
        selected = pick_folder()
        if selected:
            st.session_state.work_dir = selected
            st.session_state.video_list = []
            st.session_state.state_mgr = None
            add_log(f"已选择工作目录: {selected}", "success")
            st.rerun()

    # 同步文本输入到 session state
    if work_dir_input != st.session_state.work_dir:
        st.session_state.work_dir = work_dir_input
        st.session_state.video_list = []
        st.session_state.state_mgr = None

    # 显示目录状态
    if st.session_state.work_dir and os.path.isdir(st.session_state.work_dir):
        output_dir = os.path.join(st.session_state.work_dir, "video_output")
        temp_dir = os.path.join(st.session_state.work_dir, "video_temp")
        has_output = os.path.exists(output_dir)
        has_temp = os.path.exists(temp_dir)

        cols = st.columns(2)
        with cols[0]:
            st.markdown(f"📂 `video_output/` {'✅' if has_output else '⬜'}")
            if has_output:
                n_files = len([f for f in os.listdir(output_dir) if f.endswith(".md")])
                st.caption(f"  {n_files} 个转写文件")
        with cols[1]:
            st.markdown(f"🗂️ `video_temp/` {'✅' if has_temp else '⬜'}")
            if has_temp:
                n_audio = len([f for f in os.listdir(temp_dir) if f.endswith(".m4a")])
                st.caption(f"  {n_audio} 个音频缓存")

        # URLs 文件检测
        urls_file = os.path.join(st.session_state.work_dir, "urls.txt")
        if os.path.exists(urls_file):
            with open(urls_file, "r", encoding="utf-8") as f:
                file_content = f.read()
            n_urls = len(BilibiliFetcher.parse_url_list(file_content))
            st.markdown(f"📄 `urls.txt` ✅ ({n_urls} 个链接)")
        else:
            st.markdown("📄 `urls.txt` ⬜ (未找到)")
    elif st.session_state.work_dir:
        st.warning("目录不存在，请检查路径")
    else:
        st.info("👆 输入路径或点击「浏览」选择目录")

    st.divider()

    # 模型选择
    st.subheader("🤖 转写模型")
    model_name = st.selectbox(
        "选择 Whisper 模型",
        options=WhisperTranscriber.AVAILABLE_MODELS,
        index=WhisperTranscriber.AVAILABLE_MODELS.index(WhisperTranscriber.DEFAULT_MODEL),
        help="base最快但准确率低, medium平衡, large-v3最准但最慢",
    )

    model_desc = {
        "base": "最快 (~10x实时), 适合快速预览",
        "small": "较快 (~6x实时), 准确率明显提升",
        "medium": "平衡 (~3x实时), 推荐日常使用 ⭐",
        "large-v3": "最准 (~1.5x实时), 长视频较慢",
    }
    st.caption(model_desc.get(model_name, ""))

    st.divider()

    # 工具按钮
    st.subheader("🔧 工具")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🗑️ 清理临时文件", disabled=st.session_state.running):
            if st.session_state.state_mgr:
                st.session_state.state_mgr.cleanup_temp()
                add_log("已清理所有临时音频文件", "success")
                st.rerun()
    with col2:
        if st.button("🔄 重置所有状态", disabled=st.session_state.running):
            if st.session_state.state_mgr:
                st.session_state.state_mgr.reset()
                st.session_state.video_list = []
                add_log("已重置所有状态", "warning")
                st.rerun()

# ============================================================
# 主区域
# ============================================================
st.title("🎬 B站视频语音转写工具")
st.caption("粘贴B站视频链接 → 选择要转写的视频 → 开始批量转写")

# ============================================================
# Step 1: URL 输入
# ============================================================
st.header("1️⃣ 输入视频链接", divider=True)

tab_paste, tab_file = st.tabs(["📋 粘贴链接", "📂 从 urls.txt 加载"])

with tab_paste:
    url_text = st.text_area(
        "粘贴B站视频链接（每行一个，或混合文本均可）",
        value=st.session_state.url_text,
        height=120,
        placeholder="https://www.bilibili.com/video/BV1xxx...\nhttps://www.bilibili.com/video/BV1yyy...\nBV1zzz...",
    )

with tab_file:
    if st.session_state.work_dir and os.path.isdir(st.session_state.work_dir):
        urls_file = os.path.join(st.session_state.work_dir, "urls.txt")
        if os.path.exists(urls_file):
            with open(urls_file, "r", encoding="utf-8") as f:
                file_urls = f.read()
            st.code(file_urls, language=None)
            if st.button("📂 使用 urls.txt 中的链接"):
                st.session_state.url_text = file_urls
                st.rerun()
        else:
            st.info("在工作目录下创建 `urls.txt` 文件，每行放一个B站链接，即可从此加载。")
    else:
        st.info("请先在左侧指定工作目录")

# 解析按钮
col_parse1, col_parse2 = st.columns([1, 5])
with col_parse1:
    if st.button("🔍 解析链接", type="primary", disabled=st.session_state.running):
        if not url_text.strip():
            st.warning("请输入视频链接")
        else:
            bvid_list = BilibiliFetcher.parse_url_list(url_text)
            if not bvid_list:
                st.error("未找到有效的BV号，请检查链接格式")
            else:
                add_log(f"解析到 {len(bvid_list)} 个BV号，正在获取视频信息...")

                # 解析链接时，如果还没指定工作目录，提示用户先设置
                if not st.session_state.work_dir or not os.path.isdir(st.session_state.work_dir):
                    st.warning("⚠️ 请先在左侧**指定工作目录**（输出和临时文件将保存在该目录下），然后再开始转写。你也可以继续解析链接预览信息。")

                with st.spinner("正在获取视频信息..."):
                    fetcher = BilibiliFetcher()
                    infos = fetcher.batch_get_info(bvid_list)
                    st.session_state.fetcher = fetcher

                    # 初始化状态管理器（如果已有工作目录）
                    if st.session_state.work_dir and os.path.isdir(st.session_state.work_dir):
                        sm = StateManager(st.session_state.work_dir)
                        sm.load()
                        st.session_state.state_mgr = sm

                    # 构建视频列表
                    video_list = []
                    for info in infos:
                        status = STATUS_PENDING
                        if st.session_state.state_mgr:
                            vs = st.session_state.state_mgr.get_or_create(info.bvid)
                            vs.title = info.title
                            vs.duration = info.duration
                            status = vs.status
                        video_list.append({
                            "bvid": info.bvid,
                            "title": info.title,
                            "duration": info.duration,
                            "owner": info.owner,
                            "pages": len(info.pages),
                            "status": status,
                            "selected": status != STATUS_DONE,  # 已完成的默认不选
                            "info": info,  # 保留完整信息
                        })
                    st.session_state.video_list = video_list

                    done_count = sum(1 for v in video_list if v["status"] == STATUS_DONE)
                    add_log(f"获取到 {len(video_list)} 个视频信息 (已完成: {done_count})", "success")
                st.rerun()

# ============================================================
# Step 1.5: 输出文件夹确认（粘贴链接时）
# ============================================================
if st.session_state.video_list:
    has_work_dir = st.session_state.work_dir and os.path.isdir(st.session_state.work_dir)

    if not has_work_dir:
        st.header("📁 指定输出文件夹", divider=True)
        st.warning("⚠️ 转写前需要指定输出文件夹，转写结果和临时文件将保存在该目录下。")

        col_folder_input, col_folder_browse = st.columns([4, 1])
        with col_folder_input:
            fallback_dir = st.text_input(
                "输出文件夹路径",
                value="",
                placeholder="例如: D:\\Videos\\transcribe_output",
                key="fallback_dir_input",
            )
        with col_folder_browse:
            st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            if st.button("📂 浏览...", key="browse_fallback"):
                selected = pick_folder()
                if selected:
                    st.session_state.work_dir = selected
                    add_log(f"已选择输出目录: {selected}", "success")
                    st.rerun()

        if fallback_dir and fallback_dir != st.session_state.work_dir:
            st.session_state.work_dir = fallback_dir
            st.session_state.state_mgr = None
            # 初始化状态管理器
            if os.path.isdir(fallback_dir):
                sm = StateManager(fallback_dir)
                sm.load()
                st.session_state.state_mgr = sm
                add_log(f"输出目录已设置: {fallback_dir}", "success")
                st.rerun()

        # 提示快捷设置
        st.caption("💡 提示：在左侧边栏的「工作目录」中也可以设置，效果相同。")

# ============================================================
# Step 2: 视频列表 + 选择
# ============================================================
if st.session_state.video_list:
    st.header("2️⃣ 选择要转写的视频", divider=True)

    # 选择控制
    col_all, col_none, col_inv = st.columns(3)
    with col_all:
        if st.button("✅ 全选"):
            for v in st.session_state.video_list:
                v["selected"] = True
            st.rerun()
    with col_none:
        if st.button("⬜ 全不选"):
            for v in st.session_state.video_list:
                v["selected"] = False
            st.rerun()
    with col_inv:
        if st.button("🔄 反选"):
            for v in st.session_state.video_list:
                v["selected"] = not v["selected"]
            st.rerun()

    # 视频列表表格
    selected_count = 0
    total_duration = 0
    for i, v in enumerate(st.session_state.video_list):
        cols = st.columns([0.5, 1.5, 4, 1, 1, 1])
        with cols[0]:
            selected = st.checkbox(
                f"sel_{i}",
                value=v["selected"],
                key=f"sel_{v['bvid']}",
                disabled=v["status"] == STATUS_DONE or st.session_state.running,
            )
            v["selected"] = selected
            if selected and v["status"] != STATUS_DONE:
                selected_count += 1
                total_duration += v["duration"]
        with cols[1]:
            st.caption(v["bvid"])
        with cols[2]:
            st.markdown(f"**{v['title']}**")
        with cols[3]:
            dur = v["duration"]
            st.caption(f"{dur // 60}:{dur % 60:02d}")
        with cols[4]:
            st.caption(v.get("owner", ""))
        with cols[5]:
            status_text = v["status"]
            status_class = {
                STATUS_DONE: "status-done",
                STATUS_FAILED: "status-failed",
                STATUS_PENDING: "status-pending",
            }.get(status_text, "status-running")
            st.markdown(f'<span class="{status_class}">{status_text}</span>', unsafe_allow_html=True)

    # 选择摘要
    st.info(f"已选择 **{selected_count}** 个视频待转写 | 预计总时长 **{total_duration // 60}分{total_duration % 60}秒**")

    # ============================================================
    # Step 3: 开始转写
    # ============================================================
    st.header("3️⃣ 执行转写", divider=True)

    # 检查输出目录
    dir_ok = st.session_state.work_dir and os.path.isdir(st.session_state.work_dir)

    if not dir_ok:
        st.error("❌ 请先指定输出文件夹！在上方「📁 指定输出文件夹」区域设置路径，或在左侧边栏设置工作目录。")
        start_disabled = True
    else:
        start_disabled = st.session_state.running or selected_count == 0

    col_start, col_info = st.columns([1, 3])
    with col_start:
        if st.button(
            f"🚀 开始转写 ({selected_count}个)",
            type="primary",
            disabled=start_disabled,
        ):
            # 二次确认输出目录
            if not dir_ok:
                st.error("请先指定输出文件夹！")
                st.stop()
            st.session_state.running = True
            st.rerun()

    if dir_ok:
        # 显示输出路径信息
        output_dir = os.path.join(st.session_state.work_dir, "video_output")
        temp_dir = os.path.join(st.session_state.work_dir, "video_temp")
        col_info.caption(f"📂 输出: `{output_dir}`  |  🗂️ 临时: `{temp_dir}`")

    # 转写执行
    if st.session_state.running and dir_ok:
        selected_videos = [v for v in st.session_state.video_list if v["selected"] and v["status"] != STATUS_DONE]

        if not selected_videos:
            st.session_state.running = False
            st.success("所有选中的视频都已完成！")
            st.rerun()

        # 初始化转写器
        if st.session_state.transcriber is None or st.session_state.transcriber.model_name != model_name:
            st.session_state.transcriber = WhisperTranscriber(model_name=model_name)

        transcriber = st.session_state.transcriber
        fetcher = st.session_state.fetcher or BilibiliFetcher()
        state_mgr = st.session_state.state_mgr

        # 确保 state_mgr 初始化
        if state_mgr is None:
            state_mgr = StateManager(st.session_state.work_dir)
            state_mgr.load()
            st.session_state.state_mgr = state_mgr

        # 全局进度
        total = len(selected_videos)
        progress_bar = st.progress(0, text=f"0/{total} 完成")
        status_text = st.empty()
        eta_text = st.empty()

        # 日志区域
        log_placeholder = st.empty()

        start_time = time.time()

        for idx, v in enumerate(selected_videos):
            bvid = v["bvid"]
            info = v.get("info")
            if not info:
                # 重新获取信息
                info = fetcher.get_video_info(bvid)
                if not info:
                    if state_mgr:
                        state_mgr.mark_failed(bvid, "无法获取视频信息")
                    add_log(f"{bvid}: 获取信息失败", "error")
                    continue

            v["status"] = "running"
            status_text.markdown(f"🔄 正在处理 **{info.title}** ({idx+1}/{total})")

            # ETA 计算
            elapsed_so_far = time.time() - start_time
            if idx > 0:
                avg_per_video = elapsed_so_far / idx
                remaining = avg_per_video * (total - idx)
                eta_mins = int(remaining // 60)
                eta_secs = int(remaining % 60)
                eta_text.caption(f"⏱️ 已用时 {int(elapsed_so_far//60)}分{int(elapsed_so_far%60)}秒 | 预计剩余 {eta_mins}分{eta_secs}秒")
            else:
                eta_text.caption(f"⏱️ 已用时 {int(elapsed_so_far//60)}分{int(elapsed_so_far%60)}秒 | 预计剩余 计算中...")

            try:
                # 处理每个分P
                all_results = []
                for page_info in info.pages:
                    cid = page_info.cid
                    page_no = page_info.page

                    # 音频路径
                    audio_path = os.path.join(
                        st.session_state.work_dir, "video_temp",
                        f"audio_{bvid}_P{page_no}.m4a"
                    )

                    # 下载音频
                    if not (os.path.exists(audio_path) and os.path.getsize(audio_path) > 10000):
                        add_log(f"{bvid} P{page_no}: 下载音频...")
                        au_url, bu_urls = fetcher.get_audio_url(info.aid, cid)
                        if au_url:
                            if fetcher.download_audio(au_url, bu_urls, audio_path):
                                add_log(f"{bvid} P{page_no}: 音频下载完成", "success")
                            else:
                                add_log(f"{bvid} P{page_no}: 音频下载失败", "error")
                                continue
                        else:
                            add_log(f"{bvid} P{page_no}: 无法获取音频URL", "error")
                            continue
                    else:
                        add_log(f"{bvid} P{page_no}: 音频已存在，跳过下载")

                    # 转写
                    add_log(f"{bvid} P{page_no}: 开始转写 ({model_name})...")
                    result = transcriber.transcribe(audio_path, language="zh")
                    all_results.append({"page": page_no, "title": page_info.part, "result": result})
                    add_log(f"{bvid} P{page_no}: 转写完成 ({len(result.segments)}段)", "success")

                    # 清理临时音频
                    try:
                        os.remove(audio_path)
                    except:
                        pass

                if not all_results:
                    if state_mgr:
                        state_mgr.mark_failed(bvid, "所有分P转写失败")
                    v["status"] = STATUS_FAILED
                    add_log(f"{bvid}: 全部分P失败", "error")
                    continue

                # 生成 Markdown
                md = f"# {info.title} [{model_name}]\n\n"
                md += f"- **BV号**: {bvid}\n"
                md += f"- **链接**: https://www.bilibili.com/video/{bvid}\n"
                md += f"- **UP主**: {info.owner}\n"
                md += f"- **时长**: {info.duration // 60}分{info.duration % 60}秒\n"
                md += f"- **转写引擎**: faster-whisper {model_name} (CTranslate2)\n\n"
                md += "---\n\n"

                full_text_parts = []
                for pi, pd in enumerate(all_results):
                    r = pd["result"]
                    if len(all_results) > 1:
                        md += f"## P{pd['page']}: {pd['title']}\n\n"
                    for seg in r.segments:
                        if seg.text:
                            from core.transcriber import _format_timestamp
                            md += f"**[{_format_timestamp(seg.start)}-{_format_timestamp(seg.end)}]** {seg.text}\n\n"
                            full_text_parts.append(seg.text)
                    if len(all_results) > 1 and pi < len(all_results) - 1:
                        md += "---\n\n"

                md += "\n---\n\n## 完整文本\n\n" + " ".join(full_text_parts) + "\n"

                # 写入文件
                safe_title = "".join(c for c in info.title if c not in r'\/:*?"<>|').strip()
                output_path = os.path.join(
                    st.session_state.work_dir, "video_output",
                    f"{bvid}_{safe_title}.md"
                )
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(md)

                v["status"] = STATUS_DONE
                if state_mgr:
                    state_mgr.mark_done(bvid, output_path, model_name)
                add_log(f"✅ {info.title} → {output_path}", "success")

            except Exception as e:
                v["status"] = STATUS_FAILED
                if state_mgr:
                    state_mgr.mark_failed(bvid, str(e))
                add_log(f"{bvid}: 转写失败 - {e}", "error")
                traceback.print_exc()

            # 更新进度
            progress = (idx + 1) / total
            elapsed = time.time() - start_time
            progress_bar.progress(progress, text=f"{idx+1}/{total} 完成")

            # 更新日志显示
            log_placeholder.markdown(
                '<div class="log-box">' +
                "<br>".join(st.session_state.logs[-30:]) +
                '</div>',
                unsafe_allow_html=True,
            )

        # 全部完成
        st.session_state.running = False
        total_time = time.time() - start_time
        progress_bar.progress(1.0, text=f"🎉 全部完成！{total}/{total} | 用时 {int(total_time//60)}分{int(total_time%60)}秒")
        add_log(f"批量转写完成！共处理 {total} 个视频，用时 {int(total_time//60)}分{int(total_time%60)}秒", "success")
        st.rerun()

# ============================================================
# 日志区域
# ============================================================
if st.session_state.logs:
    st.header("📋 运行日志", divider=True)
    with st.expander("查看日志", expanded=False):
        log_html = '<div class="log-box">' + "<br>".join(st.session_state.logs) + '</div>'
        st.markdown(log_html, unsafe_allow_html=True)

# ============================================================
# 输出文件浏览
# ============================================================
if st.session_state.work_dir:
    output_dir = os.path.join(st.session_state.work_dir, "video_output")
    if os.path.exists(output_dir):
        md_files = sorted([f for f in os.listdir(output_dir) if f.endswith(".md")])
        if md_files:
            st.header("📄 转写结果", divider=True)
            for fname in md_files:
                fpath = os.path.join(output_dir, fname)
                size_kb = os.path.getsize(fpath) / 1024
                with st.expander(f"📝 {fname} ({size_kb:.1f}KB)"):
                    with open(fpath, "r", encoding="utf-8") as f:
                        content = f.read()
                    # 只显示前2000字符预览
                    if len(content) > 2000:
                        st.markdown(content[:2000] + "\n\n---\n*... (内容已截断，请打开文件查看完整内容)*")
                    else:
                        st.markdown(content)
