"""
断点恢复状态管理模块
- 跟踪每个视频的转写进度
- 支持断点恢复（重启后自动跳过已完成项）
- 持久化到 .transcribe_state.json
"""
import json
import os
import time
import logging
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

STATE_FILE = ".transcribe_state.json"

# 视频状态枚举
STATUS_PENDING = "pending"           # 待处理
STATUS_FETCHING = "fetching"         # 正在获取信息
STATUS_AUDIO_DOWNLOADING = "audio_downloading"  # 正在下载音频
STATUS_AUDIO_DOWNLOADED = "audio_downloaded"    # 音频已下载
STATUS_TRANSCRIBING = "transcribing"  # 正在转写
STATUS_DONE = "done"                 # 已完成
STATUS_FAILED = "failed"             # 失败
STATUS_SKIPPED = "skipped"           # 已跳过（用户手动）


@dataclass
class VideoState:
    """单个视频的状态"""
    bvid: str
    title: str = ""
    status: str = STATUS_PENDING
    model: str = ""
    output_file: str = ""
    duration: int = 0
    error: str = ""
    started_at: float = 0
    finished_at: float = 0
    # 分P级别状态
    pages: list = field(default_factory=list)  # [{"page": 1, "status": "done"}]


class StateManager:
    """状态管理器"""

    def __init__(self, work_dir: str):
        """
        Args:
            work_dir: 工作目录（video_temp/ 所在目录）
        """
        self.work_dir = work_dir
        self.temp_dir = os.path.join(work_dir, "video_temp")
        self.output_dir = os.path.join(work_dir, "video_output")
        self.state_path = os.path.join(self.temp_dir, STATE_FILE)
        self.states: dict[str, VideoState] = {}  # bvid -> VideoState

        # 确保目录存在
        os.makedirs(self.temp_dir, exist_ok=True)
        os.makedirs(self.output_dir, exist_ok=True)

    def load(self):
        """加载持久化状态"""
        if os.path.exists(self.state_path):
            try:
                with open(self.state_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for bvid, s in data.get("videos", {}).items():
                    self.states[bvid] = VideoState(**s)
                logger.info(f"加载状态: {len(self.states)} 条记录")
            except Exception as e:
                logger.warning(f"加载状态失败: {e}，从零开始")
                self.states = {}

        # 扫描 output 目录中已有文件，同步状态
        self._sync_with_output()

    def save(self):
        """持久化状态"""
        data = {
            "updated_at": time.time(),
            "videos": {bvid: asdict(vs) for bvid, vs in self.states.items()},
        }
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _sync_with_output(self):
        """扫描输出目录，将已有结果的标记为done"""
        if not os.path.exists(self.output_dir):
            return
        for fname in os.listdir(self.output_dir):
            if not fname.endswith(".md"):
                continue
            # 从文件名提取BV号
            bvid = fname.split("_")[0] if "_" in fname else ""
            if not bvid.startswith("BV"):
                continue
            if bvid not in self.states:
                self.states[bvid] = VideoState(bvid=bvid, title="未知", status=STATUS_DONE)
            elif self.states[bvid].status not in (STATUS_DONE, STATUS_FAILED):
                # 检查文件中是否有模型标记
                fpath = os.path.join(self.output_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        head = f.read(300)
                    if "[medium]" in head or "[base]" in head or "[small]" in head or "[large-v3]" in head:
                        self.states[bvid].status = STATUS_DONE
                        self.states[bvid].output_file = fpath
                except:
                    pass

    def get_or_create(self, bvid: str) -> VideoState:
        """获取或创建视频状态"""
        if bvid not in self.states:
            self.states[bvid] = VideoState(bvid=bvid)
        return self.states[bvid]

    def update(self, bvid: str, **kwargs):
        """更新视频状态"""
        vs = self.get_or_create(bvid)
        for k, v in kwargs.items():
            if hasattr(vs, k):
                setattr(vs, k, v)
        self.save()

    def mark_done(self, bvid: str, output_file: str, model: str = ""):
        """标记视频已完成"""
        vs = self.get_or_create(bvid)
        vs.status = STATUS_DONE
        vs.output_file = output_file
        vs.model = model
        vs.finished_at = time.time()
        self.save()

    def mark_failed(self, bvid: str, error: str = ""):
        """标记视频失败"""
        vs = self.get_or_create(bvid)
        vs.status = STATUS_FAILED
        vs.error = error
        vs.finished_at = time.time()
        self.save()

    def is_done(self, bvid: str, model: str = "") -> bool:
        """检查视频是否已完成（支持按模型检查）"""
        if bvid not in self.states:
            return False
        vs = self.states[bvid]
        if vs.status != STATUS_DONE:
            return False
        # 如果指定了模型，检查输出文件是否匹配
        if model and vs.model != model:
            return False
        return True

    def get_pending(self, bvid_list: list[str], model: str = "") -> list[str]:
        """获取待处理的BV号列表"""
        return [b for b in bvid_list if not self.is_done(b, model)]

    def get_status_summary(self) -> dict:
        """获取状态摘要"""
        counts = {}
        for vs in self.states.values():
            counts[vs.status] = counts.get(vs.status, 0) + 1
        return counts

    def cleanup_temp(self, bvid: str = ""):
        """清理临时文件"""
        if bvid:
            # 清理特定视频的临时音频
            for f in os.listdir(self.temp_dir):
                if f.startswith(f"audio_{bvid}") and f.endswith(".m4a"):
                    try:
                        os.remove(os.path.join(self.temp_dir, f))
                    except:
                        pass
        else:
            # 清理所有临时音频（保留状态文件）
            for f in os.listdir(self.temp_dir):
                if f.endswith(".m4a"):
                    try:
                        os.remove(os.path.join(self.temp_dir, f))
                    except:
                        pass

    def reset(self, bvid: str = ""):
        """重置状态"""
        if bvid:
            if bvid in self.states:
                del self.states[bvid]
        else:
            self.states.clear()
        self.save()
