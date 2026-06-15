"""媒体提取模块"""

from classroom_analyzer.extractors.video import VideoExtractor
from classroom_analyzer.extractors.audio import AudioExtractor
from classroom_analyzer.extractors.frames import FrameExtractor

__all__ = ["VideoExtractor", "AudioExtractor", "FrameExtractor"]
