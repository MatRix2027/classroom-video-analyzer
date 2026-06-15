import React, { useEffect, useState, useRef, useContext } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Typography,
} from '@mui/material';
import Grid2 from '@mui/material/Grid2';
import DescriptionIcon from '@mui/icons-material/Description';
import PictureAsPdfIcon from '@mui/icons-material/PictureAsPdf';
import {
  getTaskDetail,
  getVideoUrl,
  getReportUrl,
  type TaskDetail,
  type ScoreCard,
} from '../api/client';
import ScoreRadarChart from '../components/RadarChart';
import ScoreCardDisplay from '../components/ScoreCard';
import DimensionCard from '../components/DimensionCard';
import VideoPlayer, { type VideoPlayerHandle } from '../components/VideoPlayer';
import { ToastContext } from '../App';

const DashboardPage: React.FC = () => {
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

  // 视频跳转回调
  const handleSeekTo = (seconds: number) => {
    playerRef.current?.seekTo(seconds);
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

  // 按类目分组的柱状图数据
  const categoryData = scoreCard
    ? groupByCategory(scoreCard)
    : [];

  return (
    <Box sx={{ maxWidth: 1200, mx: 'auto', py: 3, px: 2 }}>
      {/* 页面标题 */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Box>
          <Typography variant="h5" sx={{ fontWeight: 700 }}>
            {task.filename}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            创建时间：{task.created_at || '未知'} · 状态：{task.status}
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Button
            variant="outlined"
            startIcon={<DescriptionIcon />}
            onClick={() => navigate(`/tasks/${id}/report`)}
          >
            详细报告
          </Button>
          <Button
            variant="contained"
            startIcon={<PictureAsPdfIcon />}
            href={getReportUrl(id!)}
            target="_blank"
          >
            导出报告
          </Button>
        </Box>
      </Box>

      <Grid2 container spacing={3}>
        {/* 左侧：视频播放器 */}
        <Grid2 size={{ xs: 12, md: 5 }}>
          <Card>
            <CardContent>
              <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>
                视频回放
              </Typography>
              <VideoPlayer ref={playerRef} src={getVideoUrl(id!)} />
              <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
                点击评分证据点的时间戳可跳转到对应位置
              </Typography>
            </CardContent>
          </Card>

          {/* 红线提示 */}
          {scoreCard?.red_line_violation && (
            <Card sx={{ mt: 2, border: '2px solid', borderColor: 'error.main' }}>
              <CardContent>
                <Typography variant="subtitle1" color="error" sx={{ fontWeight: 700 }}>
                  红线违规
                </Typography>
                <Typography variant="body2" color="error">
                  检测到红线淘汰行为，该课堂评分为不达标。
                </Typography>
              </CardContent>
            </Card>
          )}
        </Grid2>

        {/* 右侧：评分面板 */}
        <Grid2 size={{ xs: 12, md: 7 }}>
          {/* 总分卡片 */}
          {scoreCard && <ScoreCardDisplay scoreCard={scoreCard} />}

          {/* 雷达图 */}
          {scoreCard && scoreCard.dimensions.length > 0 && (
            <Card sx={{ mt: 2 }}>
              <CardContent>
                <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>
                  维度雷达图
                </Typography>
                <ScoreRadarChart dimensions={scoreCard.dimensions} height={350} />
              </CardContent>
            </Card>
          )}

          {/* 按类目柱状图 */}
          {categoryData.length > 0 && (
            <Card sx={{ mt: 2 }}>
              <CardContent>
                <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 2 }}>
                  分类得分
                </Typography>
                {categoryData.map((cat) => {
                  const pct = cat.maxScore > 0 ? (cat.score / cat.maxScore) * 100 : 0;
                  return (
                    <Box key={cat.name} sx={{ mb: 2 }}>
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                        <Typography variant="body2" sx={{ fontWeight: 500 }}>
                          {cat.name}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          {cat.score.toFixed(1)} / {cat.maxScore.toFixed(0)}
                        </Typography>
                      </Box>
                      <Box
                        sx={{
                          height: 8,
                          borderRadius: 4,
                          bgcolor: '#e0e0e0',
                          overflow: 'hidden',
                        }}
                      >
                        <Box
                          sx={{
                            height: '100%',
                            width: `${pct}%`,
                            borderRadius: 4,
                            bgcolor: cat.color,
                            transition: 'width 0.5s ease',
                          }}
                        />
                      </Box>
                    </Box>
                  );
                })}
              </CardContent>
            </Card>
          )}

          {/* 维度列表 */}
          {scoreCard && scoreCard.dimensions.length > 0 && (
            <Box sx={{ mt: 2 }}>
              <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>
                各维度详情
              </Typography>
              {scoreCard.dimensions.map((dim) => (
                <DimensionCard
                  key={dim.name}
                  dimension={dim}
                  onSeekTo={handleSeekTo}
                />
              ))}
            </Box>
          )}
        </Grid2>
      </Grid2>
    </Box>
  );
};

/** 按类目分组计算得分 */
function groupByCategory(scoreCard: ScoreCard) {
  const catMap = new Map<string, { score: number; maxScore: number; color: string }>();

  const CATEGORY_COLORS: Record<string, string> = {
    '教学内容': '#1976d2',
    '教学方法': '#2e7d32',
    '教学表现力': '#ed6c02',
    '教学规范': '#ed6c02',
    '课堂教学效果': '#9c27b0',
  };

  const CATEGORY_DIM_MAP: Record<string, string> = {
    '知识传授': '教学内容', '熟练程度': '教学内容', '重点难点': '教学内容',
    '启发引导': '教学方法', '教学灵活性': '教学方法', '思维方法': '教学方法',
    '教学方式方法': '教学方法', '教学逻辑': '教学方法', '教学方法灵活应用': '教学方法',
    '课堂互动': '教学表现力', '课堂节奏': '教学表现力', '语言表达': '教学表现力',
    '关注激励': '教学表现力', '数学表达能力': '教学表现力', '关注互动': '教学规范',
    '组织教学': '教学规范', '仪表教态': '教学规范',
    '语言表达及板书设计': '教学规范', '关注公平': '教学规范', '板书设计': '教学规范',
    '学习效果': '课堂教学效果', '效果外化': '课堂教学效果',
    '迁移应用': '课堂教学效果', '课堂效果及整体印象': '课堂教学效果',
  };

  for (const dim of scoreCard.dimensions) {
    const cat = CATEGORY_DIM_MAP[dim.name] || '其他';
    const existing = catMap.get(cat) || { score: 0, maxScore: 0, color: CATEGORY_COLORS[cat] || '#757575' };
    existing.score += dim.score;
    existing.maxScore += dim.max_score;
    catMap.set(cat, existing);
  }

  const order = ['教学内容', '教学方法', '教学表现力', '教学规范', '课堂教学效果'];
  return Array.from(catMap.entries())
    .map(([name, data]) => ({ name, ...data }))
    .sort((a, b) => order.indexOf(a.name) - order.indexOf(b.name));
}

export default DashboardPage;
