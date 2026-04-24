"""
B站视频资源获取模块
- 解析URL → 提取BV号
- 获取视频详情（标题、分P、时长）
- 下载音频流
"""
import re
import time
import logging
from dataclasses import dataclass, field
from typing import Optional

import requests

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.bilibili.com/",
}


@dataclass
class VideoPage:
    """视频分P信息"""
    cid: int
    page: int
    part: str  # 分P标题
    duration: int  # 秒


@dataclass
class VideoInfo:
    """视频完整信息"""
    bvid: str
    aid: int
    title: str
    duration: int  # 秒
    owner: str = ""
    pages: list = field(default_factory=list)  # List[VideoPage]
    audio_downloaded: bool = False


class BilibiliFetcher:
    """B站视频资源获取器"""

    # BV号正则
    BV_PATTERN = re.compile(r"BV[a-zA-Z0-9]+")

    def __init__(self, timeout: int = 15, retry: int = 3):
        self.timeout = timeout
        self.retry = retry
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    @staticmethod
    def parse_bvid(url_or_text: str) -> Optional[str]:
        """从URL或文本中提取BV号"""
        match = BilibiliFetcher.BV_PATTERN.search(url_or_text)
        return match.group(0) if match else None

    @staticmethod
    def parse_url_list(text: str) -> list[str]:
        """从文本中解析出所有BV号（去重保序）"""
        seen = set()
        result = []
        for match in BilibiliFetcher.BV_PATTERN.finditer(text):
            bvid = match.group(0)
            if bvid not in seen:
                seen.add(bvid)
                result.append(bvid)
        return result

    def get_video_info(self, bvid: str) -> Optional[VideoInfo]:
        """获取视频详细信息"""
        for attempt in range(self.retry):
            try:
                url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
                resp = self.session.get(url, timeout=self.timeout)
                if resp.status_code == 412:
                    logger.warning(f"BV{bvid}: 412风控，等待重试 ({attempt+1}/{self.retry})")
                    time.sleep(2 * (attempt + 1))
                    continue
                resp.raise_for_status()
                data = resp.json()
                if data.get("code") != 0:
                    logger.error(f"BV{bvid}: API错误 {data.get('code')} - {data.get('message')}")
                    return None

                v = data["data"]
                pages = [
                    VideoPage(cid=p["cid"], page=p["page"], part=p.get("part", ""), duration=p.get("duration", 0))
                    for p in v.get("pages", [])
                ]
                return VideoInfo(
                    bvid=v["bvid"],
                    aid=v["aid"],
                    title=v["title"],
                    duration=v["duration"],
                    owner=v.get("owner", {}).get("name", ""),
                    pages=pages,
                )
            except requests.RequestException as e:
                logger.warning(f"BV{bvid}: 请求失败 ({attempt+1}/{self.retry}): {e}")
                if attempt < self.retry - 1:
                    time.sleep(1)
        return None

    def get_audio_url(self, aid: int, cid: int) -> tuple[Optional[str], list[str]]:
        """获取音频流URL"""
        try:
            url = (
                f"https://api.bilibili.com/x/player/playurl"
                f"?avid={aid}&cid={cid}&qn=64&fnver=0&fnval=16&fourk=0"
            )
            resp = self.session.get(url, timeout=self.timeout)
            if resp.status_code == 412:
                logger.warning("获取音频URL: 412风控")
                return None, []
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 0:
                return None, []

            dash = data["data"].get("dash")
            if dash and dash.get("audio"):
                # 选择最高质量音频
                audio_list = sorted(dash["audio"], key=lambda x: x.get("bandwidth", 0), reverse=True)
                main_url = audio_list[0]["baseUrl"]
                backup_urls = audio_list[0].get("backupUrl", [])
                return main_url, backup_urls
        except Exception as e:
            logger.error(f"获取音频URL失败: {e}")
        return None, []

    def download_audio(self, url: str, backup_urls: list[str], output_path: str) -> bool:
        """下载音频文件到指定路径"""
        headers = {**HEADERS, "Range": "bytes=0-"}
        for try_url in [url] + (backup_urls or []):
            try:
                resp = requests.get(try_url, headers=headers, timeout=30, stream=True)
                if resp.status_code in (200, 206):
                    with open(output_path, "wb") as f:
                        for chunk in resp.iter_content(chunk_size=1024 * 1024):
                            if chunk:
                                f.write(chunk)
                    return True
            except Exception as e:
                logger.warning(f"音频下载尝试失败: {e}")
                continue
        return False

    def batch_get_info(self, bvid_list: list[str]) -> list[VideoInfo]:
        """批量获取视频信息"""
        results = []
        for i, bvid in enumerate(bvid_list):
            info = self.get_video_info(bvid)
            if info:
                results.append(info)
            else:
                logger.warning(f"跳过无法获取信息的视频: {bvid}")
            if i < len(bvid_list) - 1:
                time.sleep(0.3)  # 避免触发风控
        return results
