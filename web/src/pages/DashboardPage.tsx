import React, { useContext, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  Alert,
  Box,
  Button,
  Card,
  CardActionArea,
  CardContent,
  CircularProgress,
  Chip,
  Divider,
  Typography,
} from '@mui/material';
import DescriptionIcon from '@mui/icons-material/Description';
import DownloadIcon from '@mui/icons-material/Download';
import ImageSearchIcon from '@mui/icons-material/ImageSearch';
import PlaylistPlayIcon from '@mui/icons-material/PlaylistPlay';
import RateReviewIcon from '@mui/icons-material/RateReview';
import RuleIcon from '@mui/icons-material/Rule';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';

import { ToastContext } from '../App';
import {
  getReportUrl,
  getTaskDetail,
  getTaskEvidence,
  getVideoUrl,
  submitCalibrationFeedback,
  type EvidenceResponse,
  type ScoreDimension,
  type ScoreCard,
  type TaskDetail,
} from '../api/client';
import CalibrationFeedbackDialog from '../components/CalibrationFeedbackDialog';
import DimensionCard from '../components/DimensionCard';
import ScoreCardDisplay from '../components/ScoreCard';
import ScoreRadarChart from '../components/RadarChart';
import VideoPlayer, { type VideoPlayerHandle } from '../components/VideoPlayer';

const categoryByDimension: Record<string, string> = {
  知识传授: '教学内容',
  熟练程度: '教学内容',
  重点难点: '教学内容',
  教学方式方法: '教学方法',
  教学逻辑: '教学方法',
  教学方法灵活应用: '教学方法',
  组织教学: '教学规范',
  仪表教态: '教学规范',
  语言表达及板书设计: '教学规范',
  关注公平: '教学规范',
  课堂效果及整体印象: '课堂效果',
};

const categoryColor: Record<string, string> = {
  教学内容: '#1d4ed8',
  教学方法: '#15803d',
  教学规范: '#b45309',
  课堂效果: '#7c3aed',
  其他: '#64748b',
};

function formatDuration(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(total / 60);
  const secs = total % 60;
  return `${minutes}:${String(secs).padStart(2, '0')}`;
}

function groupByCategory(scoreCard: ScoreCard) {
  const map = new Map<string, { score: number; maxScore: number }>();
  scoreCard.dimensions.forEach((dimension) => {
    const category = categoryByDimension[dimension.name] || '其他';
    const current = map.get(category) || { score: 0, maxScore: 0 };
    current.score += dimension.score;
    current.maxScore += dimension.max_score;
    map.set(category, current);
  });
  return Array.from(map.entries()).map(([name, value]) => ({ name, ...value }));
}

const DashboardPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { showToast } = useContext(ToastContext);
  const playerRef = useRef<VideoPlayerHandle>(null);
  const [task, setTask] = useState<TaskDetail | null>(null);
  const [evidence, setEvidence] = useState<EvidenceResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [feedbackDimension, setFeedbackDimension] = useState<ScoreDimension | null>(null);

  useEffect(() => {
    if (!id) return;
    Promise.all([getTaskDetail(id), getTaskEvidence(id)])
      .then(([detail, evidenceData]) => {
        setTask(detail);
        setEvidence(evidenceData);
      })
      .catch(() => showToast('获取分析结果失败', 'error'))
      .finally(() => setLoading(false));
  }, [id, showToast]);

  const scoreCard = task?.scoring_data || null;
  const categoryData = useMemo(() => (scoreCard ? groupByCategory(scoreCard) : []), [scoreCard]);
  const weakDimensions = useMemo(() => {
    if (!scoreCard) return [];
    return [...scoreCard.dimensions]
      .sort((a, b) => (a.score / a.max_score) - (b.score / b.max_score))
      .slice(0, 3);
  }, [scoreCard]);
  const evidenceStatus = evidence?.status || task?.evidence_status || null;
  const lessonEvents = useMemo(() => evidence?.events.slice(0, 12) || [], [evidence]);
  const keyframes = useMemo(() => evidence?.keyframes.slice(0, 12) || [], [evidence]);

  if (loading) {
    return <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}><CircularProgress /></Box>;
  }

  if (!task) {
    return (
      <Box sx={{ textAlign: 'center', py: 8 }}>
        <Typography variant="h6" color="text.secondary">任务不存在</Typography>
        <Button variant="contained" sx={{ mt: 2 }} onClick={() => navigate('/')}>返回</Button>
      </Box>
    );
  }

  const openFeedback = (dimension?: ScoreDimension) => {
    setFeedbackDimension(dimension || null);
    setFeedbackOpen(true);
  };

  return (
    <Box sx={{ maxWidth: 1280, mx: 'auto', px: 3, py: 4 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 2, alignItems: 'flex-start', mb: 3 }}>
        <Box>
          <Typography variant="h4">{task.filename}</Typography>
          <Typography color="text.secondary">
            创建时间：{task.created_at || '-'} · 状态：{task.status}
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Button variant="outlined" startIcon={<RateReviewIcon />} onClick={() => openFeedback()}>
            人工校对
          </Button>
          <Button variant="outlined" startIcon={<DescriptionIcon />} onClick={() => navigate(`/tasks/${id}/report`)}>
            详细报告
          </Button>
          <Button variant="contained" startIcon={<DownloadIcon />} href={getReportUrl(id!)} target="_blank">
            导出报告
          </Button>
        </Box>
      </Box>

      {scoreCard?.red_line_violation && (
        <Alert severity="error" icon={<WarningAmberIcon />} sx={{ mb: 3 }}>
          检测到红线风险，本节课需要优先人工复核。
        </Alert>
      )}

      {evidenceStatus && (
        <Alert
          severity={evidenceStatus.review_required ? 'warning' : 'success'}
          icon={<RuleIcon />}
          sx={{ mb: 3 }}
        >
          {evidenceStatus.summary}
        </Alert>
      )}

      {evidenceStatus && (
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr 1fr', md: 'repeat(5, 1fr)' }, gap: 1.5, mb: 3 }}>
          {[
            { label: '分析模式', value: evidenceStatus.is_clip ? '片段分析' : '完整课堂' },
            { label: '视频时长', value: formatDuration(evidenceStatus.duration_seconds) },
            { label: '教学事件', value: `${evidenceStatus.event_count} 个` },
            { label: '关键帧', value: `${evidenceStatus.keyframe_count} 张` },
            { label: '视觉评分', value: evidenceStatus.visual_scored ? '已参与' : '待复核' },
          ].map((item) => (
            <Card key={item.label}>
              <CardContent sx={{ py: 1.5 }}>
                <Typography variant="caption" color="text.secondary">{item.label}</Typography>
                <Typography variant="subtitle1" sx={{ fontWeight: 800 }}>{item.value}</Typography>
              </CardContent>
            </Card>
          ))}
        </Box>
      )}

      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: '420px 1fr' }, gap: 3 }}>
        <Box sx={{ display: 'grid', gap: 2, alignContent: 'start' }}>
          <Card>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 1 }}>课堂视频</Typography>
              <VideoPlayer ref={playerRef} src={getVideoUrl(id!)} />
              <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                点击证据片段可跳转到对应时间点。
              </Typography>
            </CardContent>
          </Card>

          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1.5 }}>
                <ImageSearchIcon color="primary" />
                <Typography variant="h6">关键帧证据</Typography>
              </Box>
              {keyframes.length === 0 ? (
                <Typography variant="body2" color="text.secondary">
                  暂未找到关键帧。完成分析后，这里会按教学环节展示画面证据。
                </Typography>
              ) : (
                <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 1 }}>
                  {keyframes.map((frame) => (
                    <CardActionArea
                      key={frame.id}
                      onClick={() => playerRef.current?.seekTo(frame.timestamp)}
                      sx={{ borderRadius: 1, overflow: 'hidden', border: '1px solid #e5e7eb' }}
                    >
                      <Box
                        component="img"
                        src={frame.url}
                        alt={`${frame.timestamp_display} ${frame.event_type}`}
                        sx={{ width: '100%', aspectRatio: '16 / 9', display: 'block', objectFit: 'cover', bgcolor: '#111827' }}
                      />
                      <Box sx={{ p: 1 }}>
                        <Typography variant="caption" sx={{ fontWeight: 800 }}>
                          {frame.timestamp_display} · {frame.event_type || '关键帧'}
                        </Typography>
                        <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }} noWrap>
                          {frame.subtype || frame.description || '点击跳转视频'}
                        </Typography>
                      </Box>
                    </CardActionArea>
                  ))}
                </Box>
              )}
            </CardContent>
          </Card>

          {scoreCard && (
            <Card>
              <CardContent>
                <Typography variant="h6" sx={{ mb: 1.5 }}>四类质量画像</Typography>
                {categoryData.map((item) => {
                  const pct = item.maxScore > 0 ? Math.round((item.score / item.maxScore) * 100) : 0;
                  return (
                    <Box key={item.name} sx={{ mb: 1.5 }}>
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                        <Typography variant="body2" sx={{ fontWeight: 650 }}>{item.name}</Typography>
                        <Typography variant="body2" color="text.secondary">{item.score.toFixed(1)} / {item.maxScore.toFixed(0)}</Typography>
                      </Box>
                      <Box sx={{ height: 8, borderRadius: 4, bgcolor: '#e5e7eb', overflow: 'hidden' }}>
                        <Box sx={{ height: '100%', width: `${pct}%`, bgcolor: categoryColor[item.name], borderRadius: 4 }} />
                      </Box>
                    </Box>
                  );
                })}
              </CardContent>
            </Card>
          )}
        </Box>

        <Box>
          {scoreCard && <ScoreCardDisplay scoreCard={scoreCard} />}

          {scoreCard && (
            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: 2, mt: 2 }}>
              <Card>
                <CardContent>
                  <Typography variant="h6" sx={{ mb: 1 }}>维度雷达</Typography>
                  <ScoreRadarChart dimensions={scoreCard.dimensions} height={320} />
                </CardContent>
              </Card>
              <Card>
                <CardContent>
                  <Typography variant="h6" sx={{ mb: 1 }}>优先改进项</Typography>
                  <Box sx={{ display: 'grid', gap: 1 }}>
                    {weakDimensions.map((dimension) => (
                      <Box key={dimension.name} sx={{ p: 1.25, border: '1px solid #e5e7eb', borderRadius: 1 }}>
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 1 }}>
                          <Typography variant="body2" sx={{ fontWeight: 700 }}>{dimension.name}</Typography>
                          <Chip size="small" label={`${dimension.score.toFixed(1)}/${dimension.max_score.toFixed(0)}`} />
                        </Box>
                        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, lineHeight: 1.6 }}>
                          {dimension.evidence || dimension.details || '暂无证据说明'}
                        </Typography>
                      </Box>
                    ))}
                  </Box>
                </CardContent>
              </Card>
            </Box>
          )}

          <Card sx={{ mt: 2 }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                <PlaylistPlayIcon color="primary" />
                <Typography variant="h6">教学环节时间线</Typography>
              </Box>
              {lessonEvents.length === 0 ? (
                <Typography variant="body2" color="text.secondary">暂无教学事件。</Typography>
              ) : (
                <Box sx={{ display: 'grid' }}>
                  {lessonEvents.map((event, index) => (
                    <Box key={`${event.event_type}-${event.start_time}-${index}`}>
                      <Box
                        onClick={() => playerRef.current?.seekTo(event.start_time)}
                        sx={{ display: 'grid', gridTemplateColumns: '76px 1fr auto', gap: 1.5, py: 1.25, cursor: 'pointer' }}
                      >
                        <Typography variant="body2" sx={{ fontWeight: 800, color: 'primary.main' }}>
                          {event.start_time_display}
                        </Typography>
                        <Box>
                          <Typography variant="body2" sx={{ fontWeight: 700 }}>
                            {event.event_type}{event.subtype ? ` · ${event.subtype}` : ''}
                          </Typography>
                          <Typography variant="body2" color="text.secondary">
                            {event.description}
                          </Typography>
                        </Box>
                        <Chip size="small" label={`${Math.round(event.confidence * 100)}%`} variant="outlined" />
                      </Box>
                      {index < lessonEvents.length - 1 && <Divider />}
                    </Box>
                  ))}
                </Box>
              )}
            </CardContent>
          </Card>

          <Box sx={{ mt: 2 }}>
            <Typography variant="h6" sx={{ mb: 1 }}>维度评价</Typography>
            {scoreCard?.dimensions.map((dimension) => (
              <DimensionCard
                key={dimension.name}
                dimension={dimension}
                onSeekTo={(seconds) => playerRef.current?.seekTo(seconds)}
                onFeedback={openFeedback}
              />
            ))}
          </Box>
        </Box>
      </Box>
      <CalibrationFeedbackDialog
        open={feedbackOpen}
        task={task}
        dimension={feedbackDimension}
        onClose={() => setFeedbackOpen(false)}
        onSubmit={async (payload) => {
          await submitCalibrationFeedback(task.id, payload);
          showToast('人工校对已提交，已进入优化案例库', 'success');
        }}
      />
    </Box>
  );
};

export default DashboardPage;
