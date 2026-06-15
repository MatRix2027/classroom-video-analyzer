"""诊断 qwen-vl-max 视觉评分返回0的问题"""
import sys, os, json, traceback, logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

from classroom_analyzer.config import ConfigManager

# 1. Load config
base = Path(__file__).parent
loader = ConfigManager(str(base / "config" / "default.yaml"), str(base / "config" / "api_keys.json"))
config = loader.load(level="QC-v4")

# 2. Use pipeline to load transcript & events
from classroom_analyzer.pipeline import AnalysisPipeline
pipeline = AnalysisPipeline(config, force=False)

output_dir = base / "output" / "jj_video_20260606"
transcript = pipeline._load_transcript(str(output_dir / "transcript.txt"))
events = pipeline._load_events(str(output_dir / "events.json"))

print(f"Transcript: {len(transcript.segments)} segments")
print(f"Events: {len(events.events)} events")
print(f"Vision analyzer: {pipeline._vision_analyzer.model}")

keyframes_dir = str(output_dir / "keyframes")
kf_count = len(list(Path(keyframes_dir).glob("frame_*.jpg")))
print(f"Keyframes: {kf_count}")

# 3. Test with ALL 10 dimensions (production scenario)
print(f"\n=== NOW WITH ALL 10 DIMENSIONS (production scenario) ===")
try:
    check_items, scores = pipeline._vision_analyzer.assess_quality(
        transcript=transcript, events=events,
        checklist=config.quality_checklist, dimensions=config.scoring_dimensions,
        prompt_version="spark_standard", num_rounds=1,
        keyframe_dir=keyframes_dir,
    )
    print(f"\nOK! items={len(check_items)}, scores={len(scores)}")
    total = sum(s.score for s in scores)
    print(f"Total: {total}")
    for i, s in enumerate(scores):
        marker = " ← VISUAL" if s.name in ("仪表教态", "语言表达及板书设计") else ""
        print(f"  [{i}] {s.name}: {s.score:.1f}/{s.max_score:.0f}, {s.grade}{marker}")
    
    # Check specifically the visual dimensions
    for s in scores:
        if s.name in ("仪表教态", "语言表达及板书设计"):
            print(f"\n⚠{s.name}: score={s.score},  {'✅ >0' if s.score > 0 else '❌ ==0!'}")
except Exception as e:
    print(f"FAIL: {e}")
    traceback.print_exc()
