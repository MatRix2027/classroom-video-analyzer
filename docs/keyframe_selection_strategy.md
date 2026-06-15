# 课堂视频关键帧智能选取策略 — 技术方案

> 作者：general-purpose-1 | 日期：2026-06-05 | 版本：v1.0

---

## 1. 背景与问题定义

### 1.1 现有策略的不足

当前 V2 设计方案采用 **"每30秒固定截帧 + SSIM去重"** 的策略选取关键帧，存在以下明显问题：

| 问题 | 具体表现 | 后果 |
|------|---------|------|
| 均匀分布假设错误 | 课堂内容变化不均匀：导入阶段画面稳定，互动阶段频繁切换 | 重要教学时刻可能完全没有被截到 |
| 忽视语义信号 | 仅依赖画面相似度，不利用ASR文本和教学事件 | 选出的帧可能没有教学意义 |
| 固定间隔浪费配额 | 稳定讲解时段截多帧，互动高潮时段只截1帧 | 多模态LLM的输入帧质量低 |
| 无教学环节覆盖保证 | 随机截帧无法确保覆盖导入/讲解/互动/练习/总结 | 视觉分析结果片面 |

### 1.2 设计目标

1. **输入**：ASR转录结果 + 教学事件检测结果 + 视频元数据
2. **输出**：8-15帧，覆盖课堂关键教学时刻
3. **策略**：融合语音、文本、画面、教学事件四类信号
4. **约束**：确保覆盖教学五大环节（导入、讲解、互动、练习、总结）

---

## 2. 输入数据结构

### 2.1 ASR 转录结果（`Transcript`）

```python
@dataclass
class Transcript:
    segments: list[TranscriptSegment]  # 按时间有序
    duration: float                    # 视频总时长（秒）
    speaker_count: int                 # 说话人数量

@dataclass
class TranscriptSegment:
    start_time: float   # 开始时间（秒，带小数）
    end_time: float     # 结束时间（秒，带小数）
    text: str           # 识别文本
    speaker: str        # "teacher" / "student_1" / ...
```

**示例**（来自 `output/slice_1_20260605/transcript.txt`）：

```
[00:05-00:08] teacher: 先把上节课的内容快速的做一个小复习吧，
[00:15-00:18] teacher: 上节课主要学习的就是关于同余定理的使用，
[00:19-00:24] teacher: 直接出一道题考考大家看谁记得...
```

### 2.2 教学事件（`EventTimeline`）

```python
@dataclass
class EventTimeline:
    events: list[TeachingEvent]

@dataclass
class TeachingEvent:
    event_type: str      # 环节切换/互动指令/学生应答/教师反馈/知识节点/节奏信号
    subtype: str         # 子类型（如"复习引入""提问""个人回答"）
    start_time: float    # 事件开始时间（秒）
    end_time: float      # 事件结束时间（秒）
    description: str     # 事件描述
    confidence: float    # 置信度（0.0-1.0）
    related_text: str    # 触发此事件的原文片段
```

**示例**（来自 `output/slice_1_20260605/events.json`）：

```json
[
  {
    "event_type": "环节切换",
    "subtype": "复习引入",
    "start_time": 5.0,
    "end_time": 8.0,
    "confidence": 0.9,
    "related_text": "先把上节课的内容快速的做一个小复习吧"
  },
  {
    "event_type": "互动指令",
    "subtype": "提问",
    "start_time": 19.0,
    "end_time": 24.0,
    "confidence": 0.95,
    "related_text": "直接出一道题考考大家看谁记得..."
  }
]
```

### 2.3 视频元数据（`VideoInfo`）

```python
@dataclass
class VideoInfo:
    file_path: str
    file_size: int
    duration: float            # 秒
    format: str
    resolution: tuple[int, int]  # (width, height)
```

---

## 3. 四路信号定义与计算

### 3.1 信号一：语音信号（`speech_score[t]`）

从 ASR 时间戳派生，不需要原始音频。

#### 3.1.1 语速变化分数

```
对于时间轴上每个时间点 t（1秒粒度）：
  窗口 = [t-15, t+15]  （30秒滑动窗口）
  窗口内字数 = 所有被窗口覆盖的 TranscriptSegment 的字数之和
  语速 = 窗口内字数 / 30  （字/秒）

  语速变化分数 = | 当前语速 - 平均语速 | / 最大语速
```

**教学意义**：
- 语速突然加快 → 教师赶进度或进入熟练讲解区
- 语速突然减慢 → 进入难点，或等待学生反应
- 两项都是关键教学时刻，应截帧

#### 3.1.2 停顿检测分数

```
对于相邻的 TranscriptSegment i 和 i+1：
  间隙 = seg[i+1].start_time - seg[i].end_time
  
  长停顿（>3秒）= 1.0
  中等停顿（1-3秒）= 0.5
  短停顿（<1秒）= 0.0
```

**教学意义**：长停顿往往对应：
- 教师等待学生举手回答
- 教师思考/强调
- 学生上台做题的空白期

#### 3.1.3 说话人切换分数

```
对于时间 t：
  若 t 落在说话人切换的时间点附近（±2秒）：
    切换分数 = 1.0
  否则：
    切换分数 = 0.0
```

**教学意义**：说话人切换 = 师生互动发生的时刻，必截帧。

#### 3.1.4 语音信号综合

```
speech_score[t] = w_s1 * normalize(语速变化分数[t])
                + w_s2 * normalize(停顿分数[t])
                + w_s3 * normalize(说话人切换分数[t])

默认权重：w_s1=0.4, w_s2=0.3, w_s3=0.3
```

---

### 3.2 信号二：文本信号（`text_score[t]`）

从 ASR 文本内容和教学事件推导，不需要额外数据。

#### 3.2.1 问句检测分数

```
问句关键词 = ["谁", "什么", "怎么", "为什么", "吗", "呢", "？", "是不是", "对不对"]
问句模式 = [".+吗[，。]?", ".+呢[，。]?", "为什么.+", "怎么.+"]

对于包含时间点 t 的文本窗口（前后30秒）：
  问句分数 = 窗口内问句关键词命中次数 / 窗口总字数
             + 匹配问句模式的数量 * 0.3
```

**教学意义**：问句是互动的核心信号，提问前后必截帧。

#### 3.2.2 话题切换分数

利用 LLM 已输出的 `TeachingEvent`（类型="环节切换"）来推导：

```
对于时间 t：
  若 t 落在任意 "环节切换" 事件的 [start_time-5, end_time+5] 范围内：
    话题切换分数 = 该事件的 confidence
  否则：
    话题切换分数 = 0.0
```

如果想不依赖 LLM 事件，也可以用文本嵌入计算（可选增强）：

```
对于任意两个相邻文本窗口 W_i 和 W_{i+1}：
  计算 embedding(W_i) 和 embedding(W_{i+1}) 的余弦相似度
  话题切换分数 = 1 - 相似度
```

#### 3.2.3 关键词密度分数

```
领域关键词可以从配置中读取，也可以通过 TF-IDF 从本节视频中自动提取。

对于包含时间点 t 的文本窗口（前后30秒）：
  关键词分数 = 窗口内关键词命中次数 / 窗口总字数
```

**教学意义**：关键词密集区 = 知识传授的核心区，应截帧。

#### 3.2.4 文本信号综合

```
text_score[t] = w_t1 * normalize(问句分数[t])
              + w_t2 * normalize(话题切换分数[t])
              + w_t3 * normalize(关键词密度分数[t])

默认权重：w_t1=0.4, w_t2=0.4, w_t3=0.2
```

---

### 3.3 信号三：画面信号（`visual_score[t]`）

通过对视频进行稀疏采样计算帧间相似度，不需要对每帧都解码。

#### 3.3.1 SSIM 场景变化检测

```
采样策略：
  以 interval 秒为间隔从视频中提取帧（默认 interval=2 秒）
  对相邻两帧计算 SSIM（结构相似性）

对于采样帧 i（对应视频时间 t_i）：
  if i == 0:
    visual_score[t_i] = 0.0
  else:
    ssim = SSIM(frame_i, frame_{i-1})
    visual_score[t_i] = 1.0 - ssim   # SSIM越低 = 变化越大 = 分数越高

场景切换阈值：visual_score[t] > 0.3  → 判定为场景切换
```

**课堂场景切换的典型情况**：
- 教师走到白板前（画面从讲台→白板）
- PPT翻页（画面内容突变）
- 镜头切换（教师画面↔学生画面，适用于双机位录制）
- 学生起立回答（画面中出现学生）

#### 3.3.2 优化：使用缩略图加速 SSIM 计算

```
不需要用原始分辨率计算 SSIM。
将帧缩放至 320x180 后再计算，速度提升 ~10x，精度损失可接受。
```

#### 3.3.3 画面信号输出

```
visual_score[t]：通过最近采样点的分数插值得到任意时间点 t 的分数。
（线性插值，或取最近邻）
```

---

### 3.4 信号四：教学事件信号（`event_score[t]`）

直接利用 LLM 输出的 `EventTimeline`，是最强信号。

#### 3.4.1 事件重要性权重

不同事件类型对截帧的重要性不同：

```python
EVENT_TYPE_WEIGHTS = {
    "环节切换": 1.0,   # 最高优先级：教学阶段转换点
    "知识节点": 0.9,   # 很高优先级：概念引入/例题讲解/方法总结
    "互动指令": 0.8,   # 高优先级：提问/讨论等互动发起
    "学生应答": 0.7,   # 中高优先级：学生回答
    "教师反馈": 0.7,   # 中高优先级：教师评价/纠正
    "节奏信号": 0.4,   # 中优先级：加速/放慢等节奏变化
}
```

#### 3.4.2 事件时间点的分数分配

对于每个教学事件 e：

```
在 e.start_time 处：event_score += e.confidence * EVENT_TYPE_WEIGHTS[e.event_type]
在 e.end_time 处：  event_score += e.confidence * EVENT_TYPE_WEIGHTS[e.event_type] * 0.6
在 (e.start_time + e.end_time) / 2 处：event_score += e.confidence * EVENT_TYPE_WEIGHTS[e.event_type] * 0.8
```

**为什么取三个点**：
- `start_time`：事件触发的时刻（如教师刚提问）
- `midpoint`：事件进行中的高潮（如学生正在回答）
- `end_time`：事件结束的时刻（如教师给出反馈）

#### 3.4.3 事件信号输出

```
event_score[t]：每个时间点 t 上所有事件贡献之和（多个事件可叠加）
```

---

## 4. 多信号融合与帧选取算法

### 4.1 信号归一化

四路信号的数值范围不同，需先归一化到 [0, 1]：

```
对于每路信号 s ∈ {speech, text, visual, event}：
  s_normalized[t] = (s[t] - min(s)) / (max(s) - min(s) + ε)
```

### 4.2 加权融合

```
fusion_score[t] = w1 * speech_normalized[t]
                + w2 * text_normalized[t]
                + w3 * visual_normalized[t]
                + w4 * event_normalized[t]

默认权重：w1=0.15, w2=0.30, w3=0.15, w4=0.40
```

**权重设计理由**：
- `event`（0.40）最高：教学事件是最直接的"该截帧"信号
- `text`（0.30）次之：问句、话题切换是强语义信号
- `speech`（0.15）和 `visual`（0.15）较低：作为补充信号

**注意**：权重应可配置（`config/default.yaml` 中新增 `keyframe_selection.weights` 段）。

### 4.3 候选帧选取（核心算法）

```
输入：
  - fusion_score[t]：每个时间点 t 的融合分数
  - desired_count：目标帧数（默认 12，范围 8-15，可配置）
  - min_gap：选中帧之间的最小时间间隔（默认 10 秒）
  - video_duration：视频总时长

算法步骤：

Step 1: 按融合分数降序排列所有候选时间点
  candidates = sorted(all_t, key=fusion_score, reverse=True)

Step 2: 贪心选取，保证最小时间间隔
  selected = []
  for t in candidates:
    if len(selected) >= desired_count:
      break
    # 检查与已选帧的时间间隔
    if all(|t - s| >= min_gap for s in selected):
      selected.append(t)

Step 3: 教学环节覆盖约束（强制保证）
  定义五大教学环节的时间范围：
    phases = [
      ("导入",   0.00 * duration,  0.10 * duration),
      ("讲解",   0.15 * duration,  0.45 * duration),
      ("互动",   0.30 * duration,  0.65 * duration),
      ("练习",   0.50 * duration,  0.80 * duration),
      ("总结",   0.85 * duration,  1.00 * duration),
    ]

  for phase_name, phase_start, phase_end in phases:
    # 检查此环节是否已有选中帧
    if 没有 selected 中的帧落在 [phase_start, phase_end] 内：
      # 强制加入此环节 fusion_score 最高的时间点
      phase_best_t = argmax_{t ∈ [phase_start, phase_end]} fusion_score[t]
      if len(selected) < desired_count:
        selected.append(phase_best_t)
      else:
        # 替换已选帧中分数最低的那帧
        worst_t = argmin_{s ∈ selected} fusion_score[s]
        if fusion_score[phase_best_t] > fusion_score[worst_t]:
          selected.remove(worst_t)
          selected.append(phase_best_t)

Step 4: 按时间排序
  selected.sort()

输出：selected（时间点的有序列表）
```

### 4.4 代表帧截取

```
对于每个选中的时间点 t：
  截帧时间戳选择：
    - 优先：t 本身
    - 若 t 处有教学事件：截 event.start_time（事件精确起点）
    - 若 t 处是说话人切换点：截切换发生的精确时间戳

  帧文件名：frame_{phase_name}_{t:.0f}.jpg
    - phase_name 为此帧所属的教学环节名称
```

---

## 5. 完整算法流程

```
输入：Transcript, EventTimeline, VideoInfo, config
输出：list[KeyFrame]（8-15帧）

1. 计算语音信号 speech_score[t]
   - 语速变化（滑动窗口）
   - 停顿检测（段间间隙）
   - 说话人切换检测

2. 计算文本信号 text_score[t]
   - 问句检测（关键词 + 模式匹配）
   - 话题切换（来自环节切换事件）
   - 关键词密度

3. 计算画面信号 visual_score[t]
   - 以2秒间隔抽取视频帧
   - 计算相邻帧 SSIM
   - visual_score = 1 - SSIM

4. 计算教学事件信号 event_score[t]
   - 每个事件在 start_time、midpoint、end_time 三处加分
   - 按事件类型和置信度加权

5. 四路信号归一化
   - Min-Max 归一化到 [0, 1]

6. 加权融合
   - fusion_score[t] = 0.15*speech + 0.30*text + 0.15*visual + 0.40*event

7. 贪心选取候选帧（保证最小间隔10秒）

8. 强制覆盖五大教学环节

9. 按选定时间点截帧，生成 KeyFrame 列表

10. 返回 KeyFrame 列表（8-15帧）
```

---

## 6. 配置参数设计

在 `config/default.yaml` 中新增 `keyframe_selection` 配置段：

```yaml
# 关键帧智能选取配置
keyframe_selection:
  # 目标帧数（8-15）
  target_frame_count: 12
  
  # 选中帧之间最小间隔（秒）
  min_gap_seconds: 10
  
  # 四路信号融合权重
  weights:
    speech: 0.15    # 语音信号
    text: 0.30       # 文本信号
    visual: 0.15     # 画面信号
    event: 0.40       # 教学事件信号
  
  # 语音信号子权重
  speech_subweights:
    speech_rate: 0.4    # 语速变化
    pause: 0.3           # 停顿检测
    speaker_switch: 0.3   # 说话人切换
  
  # 文本信号子权重
  text_subweights:
    question: 0.4       # 问句检测
    topic_switch: 0.4    # 话题切换
    keyword: 0.2         # 关键词密度
  
  # 画面信号配置
  visual:
    sample_interval: 2      # 采样间隔（秒）
    ssim_threshold: 0.7    # SSIM阈值（低于此值判定为场景切换）
    resize_for_ssim: true   # 是否缩放后计算SSIM（加速）
    ssim_resize_width: 320 # 缩放宽度（像素）
  
  # 事件类型权重
  event_type_weights:
    环节切换: 1.0
    知识节点: 0.9
    互动指令: 0.8
    学生应答: 0.7
    教师反馈: 0.7
    节奏信号: 0.4
  
  # 教学环节覆盖强制保证（on/off）
  ensure_phase_coverage: true
```

---

## 7. 与现有系统的集成方案

### 7.1 修改点概述

| 文件 | 修改内容 |
|------|---------|
| `config/default.yaml` | 新增 `keyframe_selection` 配置段 |
| `src/classroom_analyzer/models.py` | 无需修改（`KeyFrame` 已支持 `trigger_event`） |
| `src/classroom_analyzer/extractors/frames.py` | 重写 `extract_for_events()` → 新增 `smart_extract()` 实现本方案 |
| `src/classroom_analyzer/pipeline.py` | 将第5步从 `extract_for_events()` 改为调用新的 `smart_extract()` |
| `src/classroom_analyzer/analysis/llm_analyzer.py` | 无需修改 |

### 7.2 新模块：`KeyFrameSelector`

建议新增独立模块 `src/classroom_analyzer/analysis/keyframe_selector.py`：

```python
class KeyFrameSelector:
    """多信号融合关键帧选取器。"""
    
    def __init__(self, config: dict):
        """初始化，读取 keyframe_selection 配置段。"""
        ...
    
    def select(
        self,
        transcript: Transcript,
        events: EventTimeline,
        video_info: VideoInfo,
        video_path: str,        # 用于提取帧计算SSIM
    ) -> list[float]:
        """执行多信号融合，返回选定的时间点列表（秒）。"""
        # Step 1-4: 计算四路信号
        speech_score = self._compute_speech_signal(transcript)
        text_score = self._compute_text_signal(transcript, events)
        visual_score = self._compute_visual_signal(video_path, video_info)
        event_score = self._compute_event_signal(events)
        
        # Step 5-6: 归一化 + 融合
        fusion_score = self._normalize_and_fuse(
            speech_score, text_score, visual_score, event_score
        )
        
        # Step 7-9: 选取 + 覆盖保证
        selected_times = self._select_frames(fusion_score, video_info.duration)
        
        return selected_times
    
    def _compute_speech_signal(self, transcript) -> dict[float, float]: ...
    def _compute_text_signal(self, transcript, events) -> dict[float, float]: ...
    def _compute_visual_signal(self, video_path, video_info) -> dict[float, float]: ...
    def _compute_event_signal(self, events) -> dict[float, float]: ...
    def _normalize_and_fuse(self, *scores) -> dict[float, float]: ...
    def _select_frames(self, fusion_score, duration) -> list[float]: ...
```

### 7.3 Pipeline 改造

`pipeline.py` 第5步改为：

```python
# [5/6] 智能关键帧选取（替代原有的事件驱动截帧）
if progress_callback:
    progress_callback(4, self.STEPS[4])

# 新增：调用 KeyFrameSelector
selector = KeyFrameSelector(self._config.analysis_config.get("keyframe_selection", {}))
selected_times = selector.select(
    transcript=transcript,
    events=event_timeline,
    video_info=video_info,
    video_path=video_path,
)
logger.info(f"智能选取了 {len(selected_times)} 个关键帧时间点")

# 按选定时间截帧
keyframes = []
for t in selected_times:
    frame_path = self._frame_extractor.extract_at_timestamp(
        video_path=video_path,
        timestamp=t,
        output_dir=output_dir,
        frame_name=f"frame_{t:.0f}",
    )
    if frame_path:
        # 找出此时间点对应的教学事件（如有）
        nearest_event = self._find_nearest_event(t, event_timeline)
        keyframes.append(KeyFrame(
            file_path=frame_path,
            timestamp=t,
            trigger_event=nearest_event,
        ))

if progress_callback:
    progress_callback(5, f"{self.STEPS[4]} ✓")
```

---

## 8. 复杂度分析

| 步骤 | 时间复杂度 | 说明 |
|------|-----------|------|
| 语音信号计算 | O(N) | N = ASR段数，约数百至数千 |
| 文本信号计算 | O(N) | 滑动窗口，常数因子较小 |
| 画面信号计算 | O(T/interval) | T = 视频时长，interval=2s，40分钟视频约1200帧SSIM计算 |
| 事件信号计算 | O(M) | M = 事件数，通常20-100 |
| 融合 + 选取 | O(T) | T = 时间点数（每秒1个点）|
| **总计** | **O(T)** | 瓶颈在画面信号（SSIM计算）|

**优化建议**：
- SSIM 计算使用缩略图（320px宽）→ 单帧 <5ms，1200帧 <6s
- 语音/文本信号计算在 LLM 分析阶段可并行预处理

---

## 9. 预期效果

以示例视频 `slice_1`（70秒，6个事件）为例：

**现有策略**（每30秒截帧 + SSIM去重）：
- 截帧点：0s, 30s, 60s → 3帧
- 问题：19s处的"提问"事件、33s处的"学生应答"事件完全没有被截到

**新策略**（多信号融合）：
- 语音信号高分点：~5s（开场）、~33s（学生回答前停顿）
- 文本信号高分点：~19s（提问）、~44s（教师详细讲解）
- 事件信号高分点：5s、15s、19s、33s、44s、56s（所有6个事件）
- 融合后选中的时间点（假设target=8）：
  - 5s（环节切换：复习引入）
  - 15s（知识节点：概念回顾）
  - 19s（互动指令：提问）→ 强制覆盖"互动"
  - 33s（学生应答）
  - 44s（教师反馈：讲解）
  - 56s（知识节点：方法总结）→ 强制覆盖"总结"
  - （若视频更长，还会覆盖"讲解"和"练习"）

---

## 10. 后续增强方向

1. **基于嵌入的话题分割**：不依赖 LLM 事件，直接用文本嵌入检测话题切换（适合事件检测不准的情况）
2. **音量信号**：如果有原始音频，可计算音量 RMS 变化，检测教师提高音量（强调）的时刻
3. **人脸检测**：用轻量模型（如 YuNet）检测教师/学生人脸出现，作为额外视觉信号
4. **自适应帧数**：根据视频时长动态调整目标帧数（短于30分钟→8帧，长于45分钟→15帧）
5. **用户反馈闭环**：记录用户对选中帧质量的反馈，用强化学习动态调整信号权重

---

## 11. 结论

本方案通过融合**语音、文本、画面、教学事件**四路信号，替代现有的"固定间隔+SSIM去重"策略，能够：

1. **精准捕捉教学关键时刻**（提问、回答、讲解高潮）
2. **保证教学环节全覆盖**（导入/讲解/互动/练习/总结各有代表帧）
3. **输出帧数适中**（8-15帧，适合多模态LLM一次处理）
4. **计算开销可控**（SSIM用缩略图加速，整体 <10s）

建议作为 V2 视觉分析管道的优先改造项实施。
