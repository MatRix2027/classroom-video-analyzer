import React, { useContext, useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Divider,
  Typography,
} from '@mui/material';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import DownloadIcon from '@mui/icons-material/Download';
import RateReviewIcon from '@mui/icons-material/RateReview';

import { ToastContext } from '../App';
import {
  getReportUrl,
  getTaskDetail,
  getVideoUrl,
  submitCalibrationFeedback,
  type ScoreDimension,
  type TaskDetail,
} from '../api/client';
import CalibrationFeedbackDialog from '../components/CalibrationFeedbackDialog';
import DimensionCard from '../components/DimensionCard';
import VideoPlayer, { type VideoPlayerHandle } from '../components/VideoPlayer';

const ReportPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { showToast } = useContext(ToastContext);
  const playerRef = useRef<VideoPlayerHandle>(null);
  const [task, setTask] = useState<TaskDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [feedbackDimension, setFeedbackDimension] = useState<ScoreDimension | null>(null);

  useEffect(() => {
    if (!id) return;
    getTaskDetail(id)
      .then(setTask)
      .catch(() => showToast('获取详细报告失败', 'error'))
      .finally(() => setLoading(false));
  }, [id, showToast]);

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

  const scoreCard = task.scoring_data;
  const openFeedback = (dimension?: ScoreDimension) => {
    setFeedbackDimension(dimension || null);
    setFeedbackOpen(true);
  };

  return (
    <Box sx={{ maxWidth: 1200, mx: 'auto', px: 3, py: 4 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 2, alignItems: 'center', mb: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Button startIcon={<ArrowBackIcon />} onClick={() => navigate(`/tasks/${id}/dashboard`)}>
            返回面板
          </Button>
          <Typography variant="h4">质量分析报告</Typography>
        </Box>
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Button variant="outlined" startIcon={<RateReviewIcon />} onClick={() => openFeedback()}>
            人工校对
          </Button>
          <Button variant="contained" startIcon={<DownloadIcon />} href={getReportUrl(id!)} target="_blank">
            导出报告
          </Button>
        </Box>
      </Box>

      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '380px 1fr' }, gap: 3 }}>
        <Box sx={{ display: 'grid', gap: 2, alignContent: 'start' }}>
          <Card>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 1 }}>视频复核</Typography>
              <VideoPlayer ref={playerRef} src={getVideoUrl(id!)} height={280} />
            </CardContent>
          </Card>
          <Card>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 1 }}>基本信息</Typography>
              <Divider sx={{ mb: 1.5 }} />
              <InfoLine label="文件名" value={task.filename} />
              <InfoLine label="状态" value={task.status} />
              <InfoLine label="总分" value={scoreCard ? `${scoreCard.total_score.toFixed(1)} / ${scoreCard.total_max.toFixed(0)}` : '-'} />
              <InfoLine label="等级" value={scoreCard?.grade || '-'} />
              <InfoLine label="标准" value={scoreCard?.level || '-'} />
              <InfoLine label="创建时间" value={task.created_at || '-'} />
              <InfoLine label="完成时间" value={task.completed_at || '-'} />
            </CardContent>
          </Card>
        </Box>

        <Box>
          {scoreCard?.red_line_violation && (
            <Alert severity="error" sx={{ mb: 2 }}>
              存在红线风险，需要优先人工复核。
            </Alert>
          )}

          <Card sx={{ mb: 2 }}>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 1 }}>总体结论</Typography>
              <Typography variant="body1" sx={{ lineHeight: 1.8 }}>
                本节课综合得分为 {scoreCard ? scoreCard.total_score.toFixed(1) : '-'} 分，
                等级为 {scoreCard?.grade || '未评级'}。以下维度评价基于课堂转写、教学事件、关键帧证据和评分标准生成，适合作为质检员复核与教师反馈的初稿。
              </Typography>
            </CardContent>
          </Card>

          <Typography variant="h6" sx={{ mb: 1 }}>逐维度评价</Typography>
          {scoreCard?.dimensions.map((dimension) => (
            <DimensionCard
              key={dimension.name}
              dimension={dimension}
              onSeekTo={(seconds) => playerRef.current?.seekTo(seconds)}
              onFeedback={openFeedback}
              defaultExpanded
            />
          ))}
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

const InfoLine: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 2, py: 0.6 }}>
    <Typography variant="body2" color="text.secondary">{label}</Typography>
    <Typography variant="body2" sx={{ fontWeight: 650, textAlign: 'right' }}>{value}</Typography>
  </Box>
);

export default ReportPage;
