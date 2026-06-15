#!/usr/bin/env python3
"""混合评分测试：文本模型（8维度）+ 视觉模型（2视觉维度 + 红线检查）"""
import json
import logging
import sys
import os

# 确保项目根目录在 sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from loguru import logger
from classroom_analyzer.config import AppConfig, load_config
from classroom_analyzer.pipeline import AnalysisPipeline

logger.remove()
logger.add(sys.stderr, level="INFO", colorize=True)


def main():
    config = load_config("config/api_keys.json")
    pipeline = AnalysisPipeline(config, force=True)

    video_path = "data/ks_video.mp4"
    output_dir = "output/ks_video_hybrid_test"
    print(f"\n{'='*60}")
    print(f" 混合评分测试：KS课堂")
    print(f" 视频: {video_path}")
    print(f" 输出: {output_dir}")
    print(f"{'='*60}\n")

    result = pipeline.run(video_path, output_dir, progress_callback=print_progress)

    # 打印评分结果
    sc = result.score_card
    print(f"\n{'='*60}")
    print(f" 混合评分结果")
    print(f"{'='*60}")
    print(f"  总分: {sc.total_score:.1f}/{sc.total_max}  ({sc.grade})")
    print(f"  等级: {sc.level}")
    print(f"\n  各维度得分:")
    for d in sc.dimensions:
        bar = "█" * int(d.score / d.max_score * 20)
        print(f"    {d.name:<20} {d.score:5.1f}/{d.max_score:>4.0f}  {bar}")
    print()

    # 读取 score_card.json 确认
    import pathlib
    sc_path = pathlib.Path(output_dir) / "score_card.json"
    if sc_path.exists():
        with open(sc_path, encoding="utf-8") as f:
            data = json.load(f)
        print(f"  score_card.json 已保存: {sc_path}")
        print(f"  总分(从文件): {data.get('total_score', 'N/A')}")


def print_progress(step: int, msg: str):
    icons = ["📂", "🎵", "📝", "🤖", "📸", "📊"]
    icon = icons[step] if step < len(icons) else "⚙"
    print(f"  {icon} [{step+1}/6] {msg}")


if __name__ == "__main__":
    main()
