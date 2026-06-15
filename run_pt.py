"""直接运行 pt_classroom 评估（3轮QC-v4），绕过 CLI 输出问题"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from classroom_analyzer.pipeline import AnalysisPipeline
from classroom_analyzer.config import ConfigManager

video_path = Path("data/pt_classroom.mp4")
config_path = Path("config/default.yaml")
api_keys_path = Path("config/api_keys.json")
output_dir = Path("output/pt_classroom_20260606")

# 强制重新运行质量评估
for f in ["quality_report.md", "score_card.json"]:
    fp = output_dir / f
    if fp.exists():
        fp.unlink()
        print(f"已删除旧文件: {fp}")

print(f"开始分析: {video_path}")
print(f"QC 版本: QC-v4, 1轮 (视觉测试)")
print(f"关键帧目录: {output_dir / 'keyframes'}")
print("=" * 60)

config_manager = ConfigManager(str(config_path), str(api_keys_path))
app_config = config_manager.load(level="QC-v4")
app_config.analysis_config["num_rounds"] = 1  # 快速测试

pipeline = AnalysisPipeline(app_config)

try:
    result = pipeline.run(str(video_path), str(output_dir))
    print("=" * 60)
    sc = result.score_card
    print(f"总分: {sc.total_score:.1f}/{sc.total_max} ({sc.grade})")
    for d in sc.dimensions:
        print(f"  {d.name}: {d.score:.1f}/{d.max_score} ({d.grade})")
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
