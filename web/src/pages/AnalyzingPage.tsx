import React, { useContext, useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Alert, Box, Button, Card, CardContent, Chip, LinearProgress, Typography } from '@mui/material';
import AutoAwesomeMotionIcon from '@mui/icons-material/AutoAwesomeMotion';
import FactCheckIcon from '@mui/icons-material/FactCheck';
import ImageSearchIcon from '@mui/icons-material/ImageSearch';
import RefreshIcon from '@mui/icons-material/Refresh';
import SmartToyIcon from '@mui/icons-material/SmartToy';
import SpatialAudioOffIcon from '@mui/icons-material/SpatialAudioOff';
import VisibilityIcon from '@mui/icons-material/Visibility';

import { ToastContext } from '../App';
import { getTaskStatus, retryTaskAnalysis, type TaskStatus, type TaskStatusType } from '../api/client';
import StepProgress from '../components/StepProgress';

const POLL_INTERVAL = 2000;

const ANALYSIS_STAGES = [
  {
    id: 'media',
    label: '视频预处理',
    helper: '读取视频信息并抽取音频',
    icon: <AutoAwesomeMotionIcon />,
    match: ['读取视频', '提取音频', '准备开始'],
  },
  {
    id: 'asr',
    label: '语音转写',
    helper: '生成带时间戳的课堂转写',
    icon: <SpatialAudioOffIcon />,
    match: ['语音识别', 'ASR', '转写'],
  },
  {
    id: 'semantic',
    label: '教学事件识别',
    helper: '识别提问、应答、反馈、知识节点',
    icon: <SmartToyIcon />,
    match: ['语义', '事件识别', 'LLM'],
  },
  {
    id: 'keyframes',
    label: '关键帧提取',
    helper: '按教学环节抽取画面证据',
    icon: <ImageSearchIcon />,
    match: ['截帧', '关键帧', '视觉证据'],
  },
  {
    id: 'vision',
    label: '视觉分析',
    helper: '观察教态、板书、学生状态和课堂氛围',
    icon: <VisibilityIcon />,
    match: ['视觉预观察', '视觉模型', '视觉评分'],
  },
  {
    id: 'report',
    label: '报告生成',
    helper: '合并文本、视觉与评分结果',
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

const AnalyzingPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { showToast } = useContext(ToastContext);

  const [status, setStatus] = useState<TaskStatusType>('pending');
  const [progress, setProgress] = useState(0);
  const [currentStage, setCurrentStage] = useState('任务已创建');
  const [error, setError] = useState('');
  const [retrying, setRetrying] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const activeStageIndex = stageIndex(currentStage, status);

  useEffect(() => {
    if (!id) return undefined;

    const pollStatus = async () => {
      try {
        const data: TaskStatus = await getTaskStatus(id);
        setStatus(data.status);
        setProgress(data.progress);
        setCurrentStage(data.current_stage || '任务处理中');

        if (data.status === 'completed') {
          if (timerRef.current) clearInterval(timerRef.current);
          timerRef.current = null;
          showToast('分析完成，正在打开质量面板。', 'success');
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

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
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

  return (
    <Box sx={{ maxWidth: 760, mx: 'auto', px: 3, py: 6 }}>
      <Card>
        <CardContent sx={{ p: 4 }}>
          <Typography variant="h4" sx={{ mb: 1, textAlign: 'center' }}>
            正在生成质量分析报告
          </Typography>
          <Typography color="text.secondary" sx={{ mb: 4, textAlign: 'center' }}>
            任务编号：{id}
          </Typography>

          <StepProgress status={status} currentStage={currentStage} />

          <Box sx={{ mt: 4 }}>
            <LinearProgress
              variant="determinate"
              value={progress}
              color={status === 'failed' ? 'error' : status === 'completed' ? 'success' : 'primary'}
              sx={{ height: 10, borderRadius: 5 }}
            />
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1, textAlign: 'center' }}>
              总进度 {progress}%
            </Typography>
          </Box>

          <Card variant="outlined" sx={{ mt: 3, bgcolor: '#f8fafc' }}>
            <CardContent>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 1, mb: 2 }}>
                <Box>
                  <Typography variant="h6">分析流程</Typography>
                  <Typography variant="body2" color="text.secondary">
                    当前阶段：{currentStage}
                  </Typography>
                </Box>
                <Chip
                  color={status === 'failed' ? 'error' : status === 'completed' ? 'success' : 'primary'}
                  label={status === 'completed' ? '已完成' : status === 'failed' ? '失败' : '进行中'}
                />
              </Box>

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
                        minHeight: 112,
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
                      <Typography variant="body2" color="text.secondary" sx={{ minHeight: 38 }}>
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

              <Alert severity="info" sx={{ mt: 2 }}>
                视觉分析会先提取关键帧，再根据关键帧观察教态、板书、学生状态和课堂氛围；如果视觉模型不可用，结果会标记为待复核。
              </Alert>
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
        </CardContent>
      </Card>
    </Box>
  );
};

export default AnalyzingPage;
