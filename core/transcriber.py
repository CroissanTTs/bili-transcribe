"""
语音转写模块
- 封装 faster-whisper，支持多种模型
- 输出 Markdown 格式
"""
import os
import time
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# 设置 ffmpeg 路径（Windows 环境兼容）
_FFMPEG_DIR = os.path.join(
    os.path.expanduser("~"),
    ".cache", "imageio_ffmpeg_bin",
)
# 尝试检测 imageio-ffmpeg
try:
    import imageio_ffmpeg
    _FFMPEG_DIR = os.path.dirname(imageio_ffmpeg.get_ffmpeg_exe())
    os.environ["PATH"] = _FFMPEG_DIR + os.pathsep + os.environ.get("PATH", "")
except ImportError:
    pass


@dataclass
class TranscribeSegment:
    """单个转写片段"""
    start: float
    end: float
    text: str


@dataclass
class TranscribeResult:
    """转写结果"""
    segments: list  # List[TranscribeSegment]
    language: str
    model_name: str


def _format_timestamp(seconds: float) -> str:
    """格式化时间戳"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


class WhisperTranscriber:
    """faster-whisper 转写引擎封装"""

    AVAILABLE_MODELS = ["base", "small", "medium", "large-v3"]
    DEFAULT_MODEL = "medium"
    DEFAULT_COMPUTE = "int8"

    def __init__(self, model_name: str = DEFAULT_MODEL, compute_type: str = DEFAULT_COMPUTE, device: str = "cpu"):
        self.model_name = model_name
        self.compute_type = compute_type
        self.device = device
        self._model = None

    def load_model(self):
        """加载模型（首次调用时自动下载）"""
        if self._model is not None:
            return
        from faster_whisper import WhisperModel
        logger.info(f"加载 faster-whisper {self.model_name} 模型 ({self.compute_type})...")
        t0 = time.time()
        self._model = WhisperModel(
            self.model_name,
            device=self.device,
            compute_type=self.compute_type,
        )
        logger.info(f"模型加载完成 ({time.time() - t0:.1f}s)")

    def transcribe(self, audio_path: str, language: str = "zh",
                   beam_size: int = 5, vad_filter: bool = True,
                   progress_callback=None) -> TranscribeResult:
        """
        转写音频文件

        Args:
            audio_path: 音频文件路径
            language: 语言代码 (zh/en/auto)
            beam_size: beam search 宽度
            vad_filter: 是否启用VAD静音过滤
            progress_callback: 进度回调函数 (optional)

        Returns:
            TranscribeResult
        """
        self.load_model()

        t0 = time.time()
        seg_iter, info = self._model.transcribe(
            audio_path,
            language=language if language != "auto" else None,
            beam_size=beam_size,
            vad_filter=vad_filter,
        )

        segments = []
        for seg in seg_iter:
            segments.append(TranscribeSegment(
                start=seg.start,
                end=seg.end,
                text=seg.text.strip(),
            ))
            if progress_callback and len(segments) % 10 == 0:
                progress_callback(len(segments))

        elapsed = time.time() - t0
        logger.info(f"转写完成: {len(segments)}段, {elapsed:.1f}s")

        return TranscribeResult(
            segments=segments,
            language=info.language,
            model_name=self.model_name,
        )

    @staticmethod
    def result_to_markdown(result: TranscribeResult, title: str, bvid: str,
                           duration: int, owner: str = "", page_info: dict = None) -> str:
        """
        将转写结果转为 Markdown 格式

        Args:
            result: 转写结果
            title: 视频标题
            bvid: BV号
            duration: 时长(秒)
            owner: UP主
            page_info: 分P信息 {"page": 1, "title": "xxx"} (可选)
        """
        md = f"# {title} [{result.model_name}]\n\n"
        md += f"- **BV号**: {bvid}\n"
        md += f"- **链接**: https://www.bilibili.com/video/{bvid}\n"
        if owner:
            md += f"- **UP主**: {owner}\n"
        md += f"- **时长**: {duration // 60}分{duration % 60}秒\n"
        md += f"- **转写引擎**: faster-whisper {result.model_name} (CTranslate2)\n"
        md += f"- **语言**: {result.language}\n\n"
        md += "---\n\n"

        # 带时间戳转录
        full_text_parts = []
        for seg in result.segments:
            if seg.text:
                md += f"**[{_format_timestamp(seg.start)}-{_format_timestamp(seg.end)}]** {seg.text}\n\n"
                full_text_parts.append(seg.text)

        # 完整文本
        md += "\n---\n\n## 完整文本\n\n"
        md += " ".join(full_text_parts) + "\n"

        return md
