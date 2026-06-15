"""课堂视频智能分析工具 — CLI 入口"""

from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.table import Table

from classroom_analyzer import __version__
from classroom_analyzer.config import ConfigManager
from classroom_analyzer.models import AnalysisResult
from classroom_analyzer.pipeline import AnalysisPipeline

console = Console()


def _format_time(seconds: float) -> str:
    """将秒数格式化为 MM:SS 格式。"""
    minutes = int(seconds) // 60
    secs = int(seconds) % 60
    return f"{minutes:02d}:{secs:02d}"


@click.group()
@click.version_option(version=__version__, prog_name="classroom-analyzer")
@click.option(
    "--level",
    "level",
    type=click.Choice(["L1_L3", "L4_L6", "L7_L9", "QC-v4"], case_sensitive=False),
    default="L4_L6",
    show_default=True,
    help="班型等级，对应不同的评分标准（L1-L3博学/L4-L6挑战/L7-L9创新）",
)
def cli(level: str) -> None:
    """课堂视频智能分析工具 — 基于语义驱动的教学视频质检、评分与素材提取"""
    pass


def get_level() -> str:
    """获取当前会话的班型等级（供子命令使用）。"""
    # 从click上下文获取level参数
    from click import get_current_context
    try:
        ctx = get_current_context()
        while ctx is not None:
            if "level" in ctx.params:
                return ctx.params["level"]
            ctx = ctx.parent
    except Exception:
        pass
    return "L4_L6"


@cli.command()
@click.argument("video_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True, path_type=Path),
    default=Path("config/default.yaml"),
    help="评分标准YAML配置文件路径",
)
@click.option(
    "--api-keys",
    "api_keys_path",
    type=click.Path(exists=True, path_type=Path),
    default=Path("config/api_keys.json"),
    help="API密钥JSON配置文件路径",
)
@click.option(
    "--output",
    "output_dir",
    type=click.Path(path_type=Path),
    default=None,
    help="输出目录（默认：./output/{video_stem}_{date}/）",
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="强制重新运行，忽略断点恢复",
)
@click.option(
    "--rounds",
    "num_rounds",
    type=click.IntRange(min=1, max=10),
    default=None,
    help="质量评估轮数（1-10），多轮取均值减少LLM偏差，默认使用配置文件值",
)
@click.pass_context
def analyze(
    ctx: click.Context,
    video_path: Path,
    config_path: Path,
    api_keys_path: Path,
    output_dir: Optional[Path],
    force: bool,
    num_rounds: Optional[int],
) -> None:
    """分析课堂视频，生成质检报告和评分卡。

    VIDEO_PATH: 待分析的视频文件路径（支持 mp4/flv/mkv）
    """
    # 从父上下文获取 level 参数
    level = ctx.parent.params.get("level", "L4_L6") if ctx.parent else "L4_L6"
    # 显示标题
    console.print()
    console.print(
        Panel(
            f"[bold]课堂视频智能分析工具[/bold] v{__version__}  [dim]({level})[/dim]",
            style="blue",
        )
    )
    console.print("━" * 40)

    # 加载配置（按班型加载对应评分标准）
    try:
        config_manager = ConfigManager(
            config_path=str(config_path),
            api_keys_path=str(api_keys_path),
        )
        app_config = config_manager.load(level=level)
    except Exception as e:
        console.print(f"[bold red]配置加载失败：{e}[/bold red]")
        raise SystemExit(1)

    # CLI --rounds 覆盖配置
    if num_rounds is not None:
        app_config.analysis_config["num_rounds"] = num_rounds
        console.print(f"[dim]评估轮数：{num_rounds}（CLI覆盖）[/dim]")

    # 确定输出目录
    if output_dir is None:
        from datetime import datetime

        date_str = datetime.now().strftime("%Y%m%d")
        output_dir = Path("output") / f"{video_path.stem}_{date_str}"

    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    # 管线步骤名称
    step_names = [
        "读取视频文件",
        "FFmpeg提取音频",
        "腾讯云ASR转文字",
        "LLM语义分析",
        "事件驱动截帧",
        "生成报告",
    ]

    # 执行分析管线
    pipeline = AnalysisPipeline(app_config, force=force)

    result: Optional[AnalysisResult] = None

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            overall_task = progress.add_task("分析进度", total=len(step_names))

            def on_progress(step: int, message: str = "") -> None:
                """管线进度回调。"""
                progress.update(overall_task, completed=step, description=f"[{step}/{len(step_names)}] {message}")

            result = pipeline.run(
                video_path=str(video_path.resolve()),
                output_dir=str(output_dir),
                progress_callback=on_progress,
            )

    except KeyboardInterrupt:
        console.print("\n[yellow]分析已中断。可重新运行以从断点恢复。[/yellow]")
        raise SystemExit(130)
    except Exception as e:
        console.print(f"\n[bold red]分析失败：{e}[/bold red]")
        raise SystemExit(1)

    # 展示结果
    console.print()
    console.print("━" * 40)
    console.print("[bold green]分析完成！[/bold green]")

    if result is not None:
        # 输出统计
        table = Table(show_header=False, border_style="dim")
        table.add_column("项目", style="cyan")
        table.add_column("值", style="white")
        table.add_row("课程时长", _format_time(result.video_info.duration))
        if result.transcript:
            table.add_row("转写字数", f"{len(result.transcript.to_text())} 字")
            table.add_row("说话人数", f"{result.transcript.speaker_count} 人")
        if result.event_timeline:
            table.add_row("教学事件", f"{len(result.event_timeline.events)} 个")
        if result.keyframes:
            table.add_row("关键帧", f"{len(result.keyframes)} 张")
        if result.score_card:
            table.add_row("总分", f"{result.score_card.total_score:.0f} / {result.score_card.total_max:.0f}")
        console.print(table)

    # 展示输出目录
    console.print()
    console.print(f"[bold]输出目录:[/bold] {output_dir}")
    console.print("  ├── transcript.txt          # 带时间戳的转录文本")
    console.print("  ├── events.json             # 教学事件时间轴")
    console.print("  ├── keyframes/              # 关键帧截图")
    console.print("  ├── quality_report.md       # 质检报告")
    console.print("  └── score_card.json         # 评分卡")
