import React, { useEffect, useState, useRef, useContext } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Divider,
  Typography,
  Chip,
  Tooltip,
} from '@mui/material';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import PictureAsPdfIcon from '@mui/icons-material/PictureAsPdf';
import VisibilityIcon from '@mui/icons-material/Visibility';
import TextFieldsIcon from '@mui/icons-material/TextFields';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import { getTaskDetail, getVideoUrl, getReportUrl, type TaskDetail } from '../api/client';
import DimensionCard from '../components/DimensionCard';
import VideoPlayer, { type VideoPlayerHandle } from '../components/VideoPlayer';
import { ToastContext } from '../App';

const ReportPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { showToast } = useContext(ToastContext);
  const playerRef = useRef<VideoPlayerHandle>(null);

  const [task, setTask] = useState<TaskDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;

    const fetchDetail = async () => {
      try {
        const data = await getTaskDetail(id);
        setTask(data);
      } catch (err: any) {
        showToast('获取任务详情失败', 'error');
      } finally {
        setLoading(false);
      }
    };

    fetchDetail();
  }, [id, showToast]);

  const handleSeekTo = (seconds: number) => {
    playerRef.current?.seekTo(seconds);
  };

  const formatTime = (seconds: number | null): string => {
    if (seconds === null || seconds === undefined) return '--:--';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    if (h > 0) return `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (!task) {
    return (
      <Box sx={{ textAlign: 'center', py: 8 }}>
        <Typography variant="h6" color="text.secondary">
          任务不存在
        </Typography>
        <Button variant="contained" sx={{ mt: 2 }} onClick={() => navigate('/')}>
          返回首页
        </Button>
      </Box>
    );
  }

  const scoreCard = task.scoring_data;

  return (
    <Box sx={{ maxWidth: 1200, mx: 'auto', py: 3, px: 2 }}>
      {/* 顶部操作栏 */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <Button
            variant="text"
            startIcon={<ArrowBackIcon />}
            onClick={() => navigate(`/tasks/${id}/dashboard`)}
          >
            返回面板
          </Button>
          <Typography variant="h5" sx={{ fontWeight: 700 }}>
            详细分析报告
          </Typography>
        </Box>
        <Button
          variant="contained"
          startIcon={<PictureAsPdfIcon />}
          href={getReportUrl(id!)}
          target="_blank"
        >
          导出 PDF
        </Button>
      </Box>

      <Box sx={{ display: 'flex', flexDirection: { xs: 'column', md: 'row' }, gap: 3 }}>
        {/* 左侧：视频 */}
        <Box sx={{ width: { xs: '100%', md: '40%' }, flexShrink: 0 }}>
          <Card>
            <CardContent>
              <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>
                视频回放
              </Typography>
              <VideoPlayer ref={playerRef} src={getVideoUrl(id!)} height={300} />
            </CardContent>
          </Card>

          {/* 基本信息卡片 */}
          <Card sx={{ mt: 2 }}>
            <CardContent>
              <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>
                基本信息
              </Typography>
              <Divider sx={{ mb: 1 }} />
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
                <Typography variant="body2">
                  <strong>文件名：</strong>{task.filename}
                </Typography>
                <Typography variant="body2">
                  <strong>状态：</strong>{task.status}
                </Typography>
                <Typography variant="body2">
                  <strong>总分：</strong>
                  {scoreCard ? `${scoreCard.total_score.toFixed(1)} / ${scoreCard.total_max.toFixed(0)}` : '—'}
                </Typography>
                <Typography variant="body2">
                  <strong>等级：</strong>{scoreCard?.grade || '—'}
                </Typography>
                <Typography variant="body2">
                  <strong>班型：</strong>{scoreCard?.level || '—'}
                </Typography>
                <Typography variant="body2">
                  <strong>评估轮数：</strong>{scoreCard?.num_rounds || 1}
                </Typography>
                {task.created_at && (
                  <Typography variant="body2">
                    <strong>创建时间：</strong>{task.created_at}
                  </Typography>
                )}
                {task.completed_at && (
                  <Typography variant="body2">
                    <strong>完成时间：</strong>{task.completed_at}
                  </Typography>
                )}
              </Box>
            </CardContent>
          </Card>
        </Box>

        {/* 右侧：报告详情 */}
        <Box sx={{ flexGrow: 1 }}>
          {/* 红线违规提示 */}
          {scoreCard?.red_line_violation && (
            <Card sx={{ mb: 2, border: '2px solid', borderColor: 'error.main' }}>
              <CardContent>
                <Typography variant="subtitle1" color="error" sx={{ fontWeight: 700 }}>
                  红线违规 — 一票否决
                </Typography>
                <Typography variant="body2" color="error">
                  该课堂检测到红线淘汰行为，评分直接判定为不达标。
                </Typography>
              </CardContent>
            </Card>
          )}

          {/* 总分概览 */}
          {scoreCard && (
            <Card sx={{ mb: 2 }}>
              <CardContent>
                <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>
                  评分概览
                </Typography>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                  <Typography variant="h3" sx={{ fontWeight: 800, color: 'primary.main' }}>
                    {scoreCard.total_score.toFixed(1)}
                  </Typography>
                  <Typography variant="body1" color="text.secondary">
                    / {scoreCard.total_max.toFixed(0)} 分 · 等级：
                    <strong style={{ color: scoreCard.grade === '优' ? '#2e7d32' : scoreCard.grade === '良' ? '#1565c0' : '#ed6c02' }}>
                      {scoreCard.grade}
                    </strong>
                  </Typography>
                </Box>
              </CardContent>
            </Card>
          )}

          {/* 各维度详细报告 */}
          <Typography variant="h6" sx={{ fontWeight: 600, mb: 1 }}>
            逐维度分析
          </Typography>

          {/* 混合评分策略说明 */}
          {scoreCard && scoreCard.dimensions.some(d => d.source_model === 'vision') && (
            <Card sx={{ mb: 1.5, bgcolor: '#f0f7ff', border: '1px solid #bbdefb' }}>
              <CardContent sx={{ py: 1.5, '&:last-child': { pb: 1.5 } }}>
                <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1 }}>
                  <InfoOutlinedIcon sx={{ color: '#1565c0', fontSize: 18, mt: 0.2 }} />
                  <Box>
                    <Typography variant="body2" sx={{ fontWeight: 600, color: '#1565c0', mb: 0.5 }}>
                      混合评分策略
                    </Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.6 }}>
                      本报告采用<strong>视觉+文本混合评分</strong>：
                    </Typography>
                    <Box sx={{ display: 'flex', gap: 1, mt: 0.8, flexWrap: 'wrap' }}>
                      <Chip
                        icon={<VisibilityIcon sx={{ fontSize: '14px !important' }} />}
                        label="视觉分析 — 仪表教态、语言表达及板书（视觉模型看视频截图）"
                        size="small"
                        sx={{ bgcolor: '#e3f2fd', color: '#1565c0', border: '1px solid #90caf9', fontSize: '0.72rem' }}
                      />
                      <Chip
                        icon={<TextFieldsIcon sx={{ fontSize: '14px !important' }} />}
                        label="文本分析 — 其余维度（文本模型读转录文本）"
                        size="small"
                        sx={{ bgcolor: '#f5f5f5', color: '#616161', border: '1px solid #e0e0e0', fontSize: '0.72rem' }}
                      />
                    </Box>
                  </Box>
                </Box>
              </CardContent>
            </Card>
          )}

          {scoreCard?.dimensions.map((dim) => (
            <DimensionCard
              key={dim.name}
              dimension={dim}
              onSeekTo={handleSeekTo}
              defaultExpanded={true}
            />
          ))}

          {!scoreCard?.dimensions.length && (
            <Card>
              <CardContent>
                <Typography variant="body1" color="text.secondary" sx={{ textAlign: 'center', py: 4 }}>
                  暂无评分数据
                </Typography>
              </CardContent>
            </Card>
          )}
        </Box>
      </Box>
    </Box>
  );
};

export default ReportPage;
