import React, { useEffect, useState, useRef, useContext } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Box, Typography, LinearProgress, Button, Alert } from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';
import { getTaskStatus, type TaskStatusType, type TaskStatus } from '../api/client';
import StepProgress from '../components/StepProgress';
import { ToastContext } from '../App';

const POLL_INTERVAL = 2000; // 2 秒轮询

const AnalyzingPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { showToast } = useContext(ToastContext);

  const [status, setStatus] = useState<TaskStatusType>('pending');
  const [progress, setProgress] = useState(0);
  const [currentStage, setCurrentStage] = useState('');
  const [error, setError] = useState('');
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // 轮询任务状态
  useEffect(() => {
    if (!id) return;

    const pollStatus = async () => {
      try {
        const data = await getTaskStatus(id);
        setStatus(data.status);
        setProgress(data.progress);
        setCurrentStage(data.current_stage);

        // 完成或失败时停止轮询
        if (data.status === 'completed') {
          if (timerRef.current) {
            clearInterval(timerRef.current);
            timerRef.current = null;
          }
          showToast('分析完成！正在跳转到评分面板...', 'success');
          setTimeout(() => navigate(`/tasks/${id}/dashboard`), 1500);
        } else if (data.status === 'failed') {
          if (timerRef.current) {
            clearInterval(timerRef.current);
            timerRef.current = null;
          }
          setError(data.current_stage || '分析失败');
          showToast('分析失败', 'error');
        }
      } catch (err: any) {
        setError('获取任务状态失败');
      }
    };

    // 立即查询一次
    pollStatus();

    // 定时轮询
    timerRef.current = setInterval(pollStatus, POLL_INTERVAL);

    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
    };
  }, [id, navigate, showToast]);

  // 进度条颜色
  const getProgressColor = (): 'primary' | 'success' | 'error' | 'warning' => {
    if (status === 'failed') return 'error';
    if (status === 'completed') return 'success';
    if (progress > 70) return 'primary';
    return 'primary';
  };

  return (
    <Box
      sx={{
        maxWidth: 640,
        mx: 'auto',
        py: 6,
        px: 2,
        textAlign: 'center',
      }}
    >
      <Typography variant="h4" sx={{ mb: 2 }}>
        正在分析中
      </Typography>
      <Typography variant="body1" color="text.secondary" sx={{ mb: 4 }}>
        任务 ID：{id}
      </Typography>

      {/* 四阶段进度条 */}
      <StepProgress status={status} currentStage={currentStage} />

      {/* 总进度条 */}
      <Box sx={{ mt: 4, mb: 2 }}>
        <LinearProgress
          variant="determinate"
          value={progress}
          color={getProgressColor()}
          sx={{ height: 10, borderRadius: 5 }}
        />
        <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
          总进度：{progress}%
        </Typography>
      </Box>

      {/* 失败提示 */}
      {status === 'failed' && (
        <Box sx={{ mt: 3 }}>
          <Alert severity="error" sx={{ mb: 2, textAlign: 'left' }}>
            {error}
          </Alert>
          <Button
            variant="outlined"
            startIcon={<RefreshIcon />}
            onClick={() => navigate('/')}
          >
            重新上传
          </Button>
        </Box>
      )}
    </Box>
  );
};

export default AnalyzingPage;
