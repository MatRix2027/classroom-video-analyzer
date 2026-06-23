import React, { useContext, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  Alert,
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Divider,
  LinearProgress,
  Tooltip,
  Typography,
} from '@mui/material';
import AutoAwesomeMotionIcon from '@mui/icons-material/AutoAwesomeMotion';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import FactCheckIcon from '@mui/icons-material/FactCheck';
import FeedbackIcon from '@mui/icons-material/Feedback';
import ImageSearchIcon from '@mui/icons-material/ImageSearch';
import ModelTrainingIcon from '@mui/icons-material/ModelTraining';
import RefreshIcon from '@mui/icons-material/Refresh';
import ScheduleIcon from '@mui/icons-material/Schedule';
import SmartToyIcon from '@mui/icons-material/SmartToy';
import SpatialAudioOffIcon from '@mui/icons-material/SpatialAudioOff';
import VisibilityIcon from '@mui/icons-material/Visibility';

import { ToastContext } from '../App';
import {
  getModelConfig,
  getTaskDetail,
  getTaskStatus,
  retryTaskAnalysis,
  submitCalibrationFeedback,
  type ModelConfig,
  type TaskDetail,
  type TaskStatus,
  type TaskStatusType,
} from '../api/client';
import CalibrationFeedbackDialog from '../components/CalibrationFeedbackDialog';
import StepProgress from '../components/StepProgress';

const POLL_INTERVAL = 3000;

const ANALYSIS_STAGES = [
  {
    id: 'media',
    label: '视频预处理',
    helper: '读取视频信息，抽取音频，为后续 ASR 和视觉证据做准备。',
    focus: '当前重点是稳定读取视频与音频。大文件在这一阶段可能需要较长时间。',
    icon: <AutoAwesomeMotionIcon />,
    match: ['读取视频', '提取音频', '准备开始'],
  },
  {
    id: 'asr',
    label: '语音转写',
    helper: '调用 ASR 生成带时间戳的课堂转写，是长视频最耗时的环节之一。',
    focus: '正在等待语音识别结果。完整课堂视频可能需要几十分钟，请不要重复上传。',
    icon: <SpatialAudioOffIcon />,
    match: ['语音识别', 'ASR', '转写', '上传音频到COS', '创建ASR'],
  },
  {
    id: 'semantic',
    label: '教学事件识别',
    helper: '识别提问、应答、反馈、知识节点和教学环节。',
    focus: '正在把转写内容拆解为教学事件，用于后续评分与证据定位。',
    icon: <SmartToyIcon />,
    match: ['语义', '事件识别', 'LLM'],
  },
  {
    id: 'keyframes',
    label: '关键帧提取',
    helper: '按教学环节抽取画面证据，为视觉分析和人工复核提供定位。',
    focus: '正在提取课堂画面证据，后续可以在看板中按时间点回看。',
    icon: <ImageSearchIcon />,
    match: ['截帧', '关键帧', '视觉证据'],
  },
  {
    id: 'vision',
    label: '视觉分析',
    helper: '观察教态、板书、学生状态和课堂氛围。',
    focus: '正在分析视觉证据。若视觉模型不可用，结果会标记为待复核。',
    icon: <VisibilityIcon />,
    match: ['视觉预观察', '视觉模型', '视觉评分'],
  },
  {
    id: 'report',
    label: '报告生成',
    helper: '合并文本、视觉证据与评分结果，生成质检报告。',
    focus: '正在生成最终报告和维度评分，完成后会自动进入质量看板。',
    icon: <FactCheckIcon />,
    match: ['生成报告', '文本模型评分', '合并评分', '分析完成'],
  },
];

function stageIndex(currentStage: string, status: TaskStatusType): number {
  if (status === 'completed') return ANALYSIS_STAGES.length - 1;
  const index = ANALYSIS_STAGES.findIndex((item) => item.match.some((keyword) => currentStage.includes(keyword)));
  return index >= 0 ? index : 0;
}

function stageState(index: number, currentIndex: number, status: TaskStatusType): 'done' | 'active' | 'waiting' | 'failed' {
  if (status === 'failed' && index === currentIndex) return 'failed';
  if (status === 'completed' || index < currentIndex) return 'done';
  if (index === currentIndex) return 'active';
  return 'waiting';
}

function parseDate(value?: string | null): number | null {
  if (!value) return null;
  const trimmed = value.trim();
  const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(trimmed);
  const normalized = hasTimezone
    ? trimmed
    : trimmed.includes('T')
      ? `${trimmed}Z`
      : `${trimmed.replace(' ', 'T')}Z`;
  const timestamp = new Date(normalized).getTime();
  return Number.isFinite(timestamp) ? timestamp : null;
}

function formatDuration(ms: number): string {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) return `${hours}小时${minutes}分钟`;
  if (minutes > 0) return `${minutes}分钟${seconds.toString().padStart(2, '0')}秒`;
  return `${seconds}秒`;
}

function estimateRemaining(elapsedMs: number, progress: number): string {
  if (progress >= 100) return '已完成';
  if (elapsedMs <= 10 * 60 * 1000) return '目标 5-10 分钟';
  if (elapsedMs <= 20 * 60 * 1000) return '已超目标，后台继续';
  return '建议稍后回看或反馈任务';
}

const AnalyzingPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { showToast } = useContext(ToastContext);

  const [status, setStatus] = useState<TaskStatusType>('pending');
  const [progress, setProgress] = useState(0);
  const [currentStage, setCurrentStage] = useState('任务已创建');
  const [createdAt, setCreatedAt] = useState<string | null>(null);
  const [analysisStartedAt, setAnalysisStartedAt] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [retrying, setRetrying] = useState(false);
  const [task, setTask] = useState<TaskDetail | null>(null);
  const [modelConfig, setModelConfig] = useState<ModelConfig | null>(null);
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [lastProgressAt, setLastProgressAt] = useState(Date.now());
  const [tick, setTick] = useState(Date.now());
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const progressRef = useRef(0);
  const firstSeenAtRef = useRef(Date.now());

  const activeStageIndex = stageIndex(currentStage, status);
  const activeStage = ANALYSIS_STAGES[activeStageIndex];
  const persistedStartedAt = parseDate(analysisStartedAt);
  const startedAtMs = persistedStartedAt || firstSeenAtRef.current;
  const elapsedMs = Math.max(0, tick - startedAtMs);
  const remainingText = estimateRemaining(elapsedMs, progress);
  const noProgressMs = Math.max(0, tick - lastProgressAt);
  const isRunning = status !== 'completed' && status !== 'failed';
  const hasServerStartedAt = Boolean(persistedStartedAt);
  const elapsedLabel = hasServerStartedAt ? '已耗时' : '本次查看';
  const hasLongRuntime = elapsedMs > 30 * 60 * 1000 && isRunning;
  const looksQuiet = noProgressMs > 10 * 60 * 1000 && isRunning;

  useEffect(() => {
    if (!id) return undefined;

    getTaskDetail(id).then(setTask).catch(() => undefined);
    getModelConfig().then(setModelConfig).catch(() => undefined);

    const pollStatus = async () => {
      try {
        const data: TaskStatus = await getTaskStatus(id);
        const previousProgress = progressRef.current;
        setStatus(data.status);
        setProgress(data.progress);
        setCurrentStage(data.current_stage || '任务处理中');
        setCreatedAt(data.created_at || null);
        setAnalysisStartedAt(data.analysis_started_at || null);
        progressRef.current = data.progress;

        const statusUpdatedAt = parseDate(data.status_updated_at);
        if (statusUpdatedAt) {
          setLastProgressAt(statusUpdatedAt);
        }

        if (!statusUpdatedAt && data.progress !== previousProgress) {
          setLastProgressAt(Date.now());
        }

        if (data.status === 'completed') {
          if (timerRef.current) clearInterval(timerRef.current);
          timerRef.current = null;
          showToast('分析完成，正在打开质量看板。', 'success');
          setTimeout(() => navigate(`/tasks/${id}/dashboard`), 1000);
        }

        if (data.status === 'failed') {
          if (timerRef.current) clearInterval(timerRef.current);
          timerRef.current = null;
          setError(data.current_stage || '分析失败');
          showToast('分析失败', 'error');
        }
      } catch {
        setError('获取任务状态失败');
      }
    };

    pollStatus();
    timerRef.current = setInterval(pollStatus, POLL_INTERVAL);
    const clock = setInterval(() => setTick(Date.now()), 1000);

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
      clearInterval(clock);
    };
  }, [id, navigate, showToast]);

  const handleRetry = async () => {
    if (!id) return;
    setRetrying(true);
    try {
      await retryTaskAnalysis(id);
      setStatus('pending');
      setProgress(0);
      setError('');
      setLastProgressAt(Date.now());
      showToast('已重新启动分析，将从已上传的视频继续处理', 'success');
      window.location.reload();
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.message || '重试分析失败，请稍后再试';
      setError(msg);
      showToast('重试分析失败', 'error');
    } finally {
      setRetrying(false);
    }
  };

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      showToast('已复制当前任务链接', 'success');
    } catch {
      showToast('复制失败，请手动复制浏览器地址', 'warning');
    }
  };

  const modelItems = useMemo(() => {
    if (!modelConfig) return [];
    return [
      { label: '文本模型', value: modelConfig.text_model },
      { label: '视觉模型', value: modelConfig.vision_enabled ? modelConfig.vision_model : '未启用' },
    ];
  }, [modelConfig]);

  return (
    <Box sx={{ maxWidth: 1080, mx: 'auto', px: { xs: 2, md: 3 }, py: 3 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 2, alignItems: 'flex-start', mb: 3 }}>
        <Box>
          <Typography variant="h4">分析监控台</Typography>
          <Typography color="text.secondary" sx={{ mt: 0.5 }}>
            任务编号：{id}
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
          <Button variant="outlined" startIcon={<ContentCopyIcon />} onClick={copyLink}>
            复制链接
          </Button>
          <Button variant="outlined" startIcon={<FeedbackIcon />} onClick={() => setFeedbackOpen(true)}>
            反馈当前任务
          </Button>
        </Box>
      </Box>

      {(hasLongRuntime || looksQuiet) && (
        <Alert severity="warning" sx={{ mb: 2, borderRadius: 2 }}>
          {looksQuiet
            ? `最近 ${formatDuration(noProgressMs)} 没有进度更新，后台任务可能在等待 ASR 或已被服务休眠中断。可先保留链接，必要时反馈或重试。`
            : `当前任务运行时间超过预期，后台仍会继续处理；页面可关闭，稍后从当前链接回看。`}
        </Alert>
      )}

      <Card sx={{ mb: 2, borderRadius: 2, boxShadow: '0 10px 28px rgba(15, 23, 42, 0.06)' }}>
        <CardContent>
          <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1.2fr 0.8fr' }, gap: 3 }}>
            <Box>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 1, mb: 1 }}>
                <Typography variant="h6">当前进度</Typography>
                <Chip
                  color={status === 'failed' ? 'error' : status === 'completed' ? 'success' : 'primary'}
                  label={status === 'completed' ? '已完成' : status === 'failed' ? '失败' : '进行中'}
                />
              </Box>
              <LinearProgress
                variant="determinate"
                value={progress}
                color={status === 'failed' ? 'error' : status === 'completed' ? 'success' : 'primary'}
                sx={{ height: 12, borderRadius: 6 }}
              />
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 1 }}>
                <Typography variant="body2" color="text.secondary">总进度 {progress}%</Typography>
                <Typography variant="body2" color="text.secondary">耗时目标：{remainingText}</Typography>
              </Box>

              <Box sx={{ mt: 2, p: 1.5, borderRadius: 2, bgcolor: '#f8fafc', border: '1px solid #e5e7eb' }}>
                <Typography variant="subtitle2" sx={{ fontWeight: 800 }}>
                  {activeStage.label}
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                  当前阶段：{currentStage}
                </Typography>
                <Typography variant="body2" sx={{ mt: 1, lineHeight: 1.7 }}>
                  {activeStage.focus}
                </Typography>
              </Box>
            </Box>

            <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1.5 }}>
              <MetricCard icon={<ScheduleIcon />} label={elapsedLabel} value={formatDuration(elapsedMs)} />
              <MetricCard icon={<RefreshIcon />} label="最近更新" value={`${formatDuration(noProgressMs)}前`} />
              <MetricCard icon={<ModelTrainingIcon />} label="处理阶段" value={activeStage.label} />
              <MetricCard icon={<FeedbackIcon />} label="人工入口" value="可反馈" />
            </Box>
          </Box>
        </CardContent>
      </Card>

      <Card variant="outlined" sx={{ bgcolor: '#f8fafc', borderRadius: 2 }}>
        <CardContent>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 1, mb: 2 }}>
            <Box>
              <Typography variant="h6">质检分析流程</Typography>
              <Typography variant="body2" color="text.secondary">
                长任务会分阶段更新。当前页面每 {POLL_INTERVAL / 1000} 秒自动刷新一次状态。
              </Typography>
            </Box>
            <Tooltip title="完成后可在报告页逐项提交人工校对，形成优化案例库">
              <Chip icon={<FeedbackIcon />} label="支持人工校对" variant="outlined" />
            </Tooltip>
          </Box>

          <StepProgress status={status} currentStage={currentStage} />

          <Accordion disableGutters sx={{ mt: 2, borderRadius: 2, '&:before': { display: 'none' } }}>
            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
              <Typography variant="subtitle2" sx={{ fontWeight: 800 }}>查看详细流程与模型配置</Typography>
            </AccordionSummary>
            <AccordionDetails>
              <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr', md: 'repeat(3, 1fr)' }, gap: 1.5 }}>
                {ANALYSIS_STAGES.map((item, index) => {
                  const state = stageState(index, activeStageIndex, status);
                  const active = state === 'active';
                  const done = state === 'done';
                  const failed = state === 'failed';
                  return (
                    <Box
                      key={item.id}
                      sx={{
                        p: 1.5,
                        borderRadius: 1.5,
                        border: '1px solid',
                        borderColor: failed ? '#fecaca' : active ? '#86efac' : done ? '#bbf7d0' : '#e5e7eb',
                        bgcolor: failed ? '#fef2f2' : active ? '#f0fdf4' : done ? '#f7fee7' : '#ffffff',
                        minHeight: 118,
                      }}
                    >
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                        <Box sx={{ color: failed ? 'error.main' : active || done ? 'primary.main' : 'text.disabled', display: 'flex' }}>
                          {item.icon}
                        </Box>
                        <Typography variant="subtitle2" sx={{ fontWeight: 800 }}>
                          {item.label}
                        </Typography>
                      </Box>
                      <Typography variant="body2" color="text.secondary" sx={{ minHeight: 44, lineHeight: 1.6 }}>
                        {item.helper}
                      </Typography>
                      <Chip
                        size="small"
                        sx={{ mt: 1 }}
                        color={failed ? 'error' : active ? 'primary' : done ? 'success' : 'default'}
                        variant={active || failed ? 'filled' : 'outlined'}
                        label={failed ? '需处理' : active ? '正在处理' : done ? '已完成' : '等待中'}
                      />
                    </Box>
                  );
                })}
              </Box>

              <Divider sx={{ my: 2 }} />
              <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                {modelItems.map((item) => (
                  <Chip key={item.label} icon={<ModelTrainingIcon />} label={`${item.label}：${item.value}`} variant="outlined" />
                ))}
              </Box>
              <Alert severity="info" sx={{ mt: 2 }}>
                完成后可以在看板或报告页提交人工校对，反馈会绑定当前视频任务并进入校对记录。
              </Alert>
            </AccordionDetails>
          </Accordion>
        </CardContent>
      </Card>

      {status === 'failed' && (
        <Box sx={{ mt: 3 }}>
          <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>
          <Box sx={{ display: 'flex', gap: 1.5, flexWrap: 'wrap' }}>
            <Button variant="contained" startIcon={<RefreshIcon />} onClick={handleRetry} disabled={retrying}>
              {retrying ? '正在重试' : '重试分析'}
            </Button>
            <Button variant="outlined" onClick={() => navigate('/')}>
              重新上传
            </Button>
          </Box>
        </Box>
      )}

      <CalibrationFeedbackDialog
        open={feedbackOpen}
        task={task}
        onClose={() => setFeedbackOpen(false)}
        onSubmit={async (payload) => {
          if (!id) return;
          await submitCalibrationFeedback(id, {
            ...payload,
            feedback_type: payload.feedback_type || 'overall_score',
          });
          showToast('当前任务反馈已提交，已进入校对记录', 'success');
        }}
      />
    </Box>
  );
};

const MetricCard: React.FC<{ icon: React.ReactNode; label: string; value: string }> = ({ icon, label, value }) => (
  <Box sx={{ p: 1.35, border: '1px solid #e5e7eb', borderRadius: 2, bgcolor: '#ffffff', minHeight: 78 }}>
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, color: 'primary.main', mb: 0.75 }}>
      {icon}
      <Typography variant="caption" color="text.secondary">{label}</Typography>
    </Box>
    <Typography variant="subtitle2" sx={{ fontWeight: 800, wordBreak: 'break-word' }}>{value}</Typography>
  </Box>
);

export default AnalyzingPage;
