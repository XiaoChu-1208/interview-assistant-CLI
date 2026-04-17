"""STT post-processing: hallucination + filler word filters.

Whisper (and to a lesser extent other ASRs) routinely produces a small set of
fixed strings on silence — YouTube outros, fan-sub credits, Chinese streaming
platform residue. We dedupe them. Users (or the homophone-detector skill) can
extend the set via [stt_filter].extra_hallucinations.
"""
from __future__ import annotations

import re
from collections.abc import Iterable


BUILTIN_HALLUCINATIONS: set[str] = {
    "字幕志愿者 杨茜茜", "字幕志愿者杨茜茜",
    "请不吝点赞 订阅 转发 打赏支持明镜与点点栏目",
    "感谢观看", "谢谢观看", "謝謝觀看",
    "字幕由Amara.org社区提供", "字幕由 able.org社区提供",
    "潜水印记", "请订阅我的频道", "歡迎訂閱",
    "Thank you.", "Thanks for watching!",
    "Subtitles by the Amara.org community",
    "ご視聴ありがとうございました",
    "请订阅我们的频道", "欢迎订阅",
    "Thank you for watching!",
    # Chinese streaming-platform residue (extremely common in Whisper)
    "悠悠独播剧场", "悠悠獨播劇場", "优独播剧场",
    "优优独播剧场", "優優獨播劇場",
    "由由独播剧场", "优酷独播剧场", "腾讯独播",
    "本视频由", "本視頻由", "本期视频", "本期視頻",
    "明镜火眼", "明鏡火眼",
    "字幕组", "字幕組", "压制",
}


BUILTIN_FILLER = re.compile(
    r"^("
    r"你好[你好]*|您好[您好]*|哈[喽啰]|hello|hi|hey"
    r"|了解[了解]*|明白[了明白]*|清楚[了清楚]*"
    r"|好[的嘞哒]?[好的嘞哒]*|OK+|okay|okie"
    r"|嗯+[嗯哼]*|啊+|哦+|噢+"
    r"|对[对的啊]*|是[的啊]*|没错"
    r"|行[行的啊]*|可以[可以]*|没问题"
    r"|知道了?|收到|看到了?"
    r"|谢谢[你您]?[谢谢]*|感谢|thanks?"
    r"|没有[了]?|不[是会用]|还好"
    r"|那[个啥]?|然后呢?|继续"
    r"|我[看想]看|我[想]想|让我想想"
    r")$",
    re.IGNORECASE,
)


class STTFilter:
    """Holds built-in + user-extended sets and exposes simple checks."""

    def __init__(
        self,
        extra_hallucinations: Iterable[str] = (),
        extra_fillers: Iterable[str] = (),
    ) -> None:
        self.hallucinations = set(BUILTIN_HALLUCINATIONS) | {s.strip() for s in extra_hallucinations if s.strip()}
        self._extra_filler_pattern = (
            re.compile("|".join(f"(?:{p})" for p in extra_fillers), re.IGNORECASE)
            if extra_fillers else None
        )

    def is_hallucination(self, text: str) -> bool:
        return text.strip() in self.hallucinations

    def is_filler(self, text: str) -> bool:
        cleaned = text.strip()
        if BUILTIN_FILLER.match(cleaned):
            return True
        if self._extra_filler_pattern and self._extra_filler_pattern.match(cleaned):
            return True
        return False

    def add_hallucination(self, text: str) -> None:
        self.hallucinations.add(text.strip())
