import React, { useState } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  LinearProgress,
  IconButton,
  Collapse,
  Chip,
  Tooltip,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  RadioGroup,
  Radio,
  FormControlLabel,
  FormControl,
  FormLabel,
  Snackbar,
  Alert,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import VisibilityIcon from '@mui/icons-material/Visibility';
import TextFieldsIcon from '@mui/icons-material/TextFields';
import FeedbackIcon from '@mui/icons-material/Feedback';
import type { ScoreDimension } from '../api/client';
import ScoringPointList from './ScoringPointList';
import { getCategoryColor } from './RadarChart';

// 等级颜色映射
const GRADE_COLORS: Record<string, string> = {
  '优': '#2e7d32',
  '良': '#1565c0',
  '中': '#ed6c02',
  '差': '#c62828',
};

interface DimensionCardProps {
  dimension: ScoreDimension;
  /** 点击时间戳回调 */
  onSeekTo?: (seconds: number) => void;
  /** 默认是否展开 */
  defaultExpanded?: boolean;
}

/** 单维度详情卡片 */
const DimensionCard: React.FC<DimensionCardProps> = ({
  dimension,
  onSeekTo,
  defaultExpanded = false,
}) => {
  const [expanded, setExpanded] = useState(defaultExpanded);

  const percentage = dimension.max_score > 0
    ? (dimension.score / dimension.max_score) * 100
    : 0;

  const gradeColor = GRADE_COLORS[dimension.grade] || '#757575';
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const categoryColor = getCategoryColor(dimension.name);

  const isVision = dimension.source_model === 'vision';
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [feedbackAgree, setFeedbackAgree] = useState('agree');
  const [feedbackSuggestion, setFeedbackSuggestion] = useState('');
  const [feedbackScore, setFeedbackScore] = useState('');
  const [feedbackSubmitted, setFeedbackSubmitted] = useState(false);

  const handleFeedbackSubmit = () => {
    // 收集反馈数据（目前存localStorage，后续接API）
    const feedback = {
      dimension: dimension.name,
      aiScore: dimension.score,
      agree: feedbackAgree,
      suggestedScore: feedbackScore ? parseFloat(feedbackScore) : null,
      suggestion: feedbackSuggestion,
      timestamp: new Date().toISOString(),
    };
    const existing = JSON.parse(localStorage.getItem('dimension_feedback') || '[]');
    existing.push(feedback);
    localStorage.setItem('dimension_feedback', JSON.stringify(existing));
    setFeedbackSubmitted(true);
    setFeedbackOpen(false);
    setTimeout(() => setFeedbackSubmitted(false), 3000);
  };

  return (
    <Card
      sx={{
        mb: 1.5,
        border: '1px solid',
        borderColor: isVision ? 'rgba(21, 101, 192, 0.3)' : 'divider',
        transition: 'box-shadow 0.2s',
        '&:hover': { boxShadow: '0 4px 12px rgba(0,0,0,0.1)' },
        ...(isVision && {
          background: 'linear-gradient(135deg, rgba(227, 242, 253, 0.4) 0%, #fff 100%)',
        }),
      }}
    >
      <CardContent sx={{ py: 2, '&:last-child': { pb: 2 } }}>
        {/* 标题行 */}
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            cursor: 'pointer',
          }}
          onClick={() => setExpanded(!expanded)}
        >
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, flexWrap: 'wrap' }}>
            <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
              {dimension.name}
            </Typography>
            <Chip
              label={dimension.grade || '—'}
              size="small"
              sx={{
                bgcolor: gradeColor,
                color: 'white',
                fontWeight: 600,
                height: 22,
                fontSize: '0.75rem',
              }}
            />
            {/* 来源模型标签 */}
            <Tooltip
              title={
                isVision
                  ? '此维度由 Qwen-VL 视觉模型基于视频关键帧评分（更准确）'
                  : '此维度由文本模型基于转录文本评分'
              }
            >
              <Chip
                icon={isVision
                  ? <VisibilityIcon sx={{ fontSize: '14px !important' }} />
                  : <TextFieldsIcon sx={{ fontSize: '14px !important' }} />
                }
                label={isVision ? '视觉分析' : '文本分析'}
                size="small"
                variant="outlined"
                sx={{
                  height: 20,
                  fontSize: '0.7rem',
                  borderColor: isVision ? '#1565c0' : '#bdbdbd',
                  color: isVision ? '#1565c0' : '#757575',
                  '& .MuiChip-icon': { color: isVision ? '#1565c0' : '#757575' },
                }}
              />
            </Tooltip>
          </Box>

          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <Typography variant="body2" sx={{ fontWeight: 600, color: 'primary.main' }}>
              {dimension.score.toFixed(1)} / {dimension.max_score.toFixed(0)}
            </Typography>
            <IconButton size="small">
              {expanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
            </IconButton>
          </Box>
        </Box>

        {/* 进度条 */}
        <Box sx={{ mt: 1, mb: 0.5 }}>
          <LinearProgress
            variant="determinate"
            value={percentage}
            sx={{
              height: 6,
              borderRadius: 3,
              bgcolor: '#e0e0e0',
              '& .MuiLinearProgress-bar': {
                borderRadius: 3,
                bgcolor: percentage >= 90 ? '#2e7d32' : percentage >= 70 ? '#1565c0' : percentage >= 50 ? '#ed6c02' : '#c62828',
              },
            }}
          />
        </Box>

        {/* 展开内容 */}
        <Collapse in={expanded}>
          <Box sx={{ mt: 2 }}>
            {/* 证据描述 */}
            {dimension.evidence && (
              <Box sx={{ mb: 2 }}>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
                  证据描述
                </Typography>
                <Typography variant="body2" sx={{ lineHeight: 1.7 }}>
                  {dimension.evidence}
                </Typography>
              </Box>
            )}

            {/* 详细说明 */}
            {dimension.details && (
              <Box sx={{ mb: 2 }}>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
                  详细说明
                </Typography>
                <Typography variant="body2">{dimension.details}</Typography>
              </Box>
            )}

            {/* 评分证据点列表 */}
            {dimension.scoring_points && dimension.scoring_points.length > 0 && (
              <Box>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
                  评分证据点（{dimension.scoring_points.length} 项）
                </Typography>
                <ScoringPointList points={dimension.scoring_points} onSeekTo={onSeekTo} />
              </Box>
            )}

            {/* 多轮评估信息 */}
            {dimension.round_scores && dimension.round_scores.length > 1 && (
              <Box sx={{ mt: 1, display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                {dimension.round_scores.map((s, i) => (
                  <Chip
                    key={i}
                    label={`第${i + 1}轮: ${s.toFixed(1)}`}
                    size="small"
                    variant="outlined"
                  />
                ))}
                {dimension.score_std !== null && dimension.score_std !== undefined && (
                  <Chip
                    label={`σ = ${dimension.score_std.toFixed(2)}`}
                    size="small"
                    color="warning"
                    variant="outlined"
                  />
                )}
              </Box>
            )}
          </Box>
        </Collapse>

        {/* 反馈按钮 */}
        <Box sx={{ mt: 1, display: 'flex', justifyContent: 'flex-end' }}>
          <Button
            size="small"
            startIcon={<FeedbackIcon />}
            onClick={() => setFeedbackOpen(true)}
            sx={{ textTransform: 'none', color: 'text.secondary' }}
          >
            评分反馈
          </Button>
        </Box>
      </CardContent>

      {/* 反馈对话框 */}
      <Dialog open={feedbackOpen} onClose={() => setFeedbackOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>评分反馈 — {dimension.name}</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            AI评分：{dimension.score.toFixed(1)} / {dimension.max_score.toFixed(0)}（{dimension.grade}）
          </Typography>
          <FormControl component="fieldset" sx={{ mb: 2 }}>
            <FormLabel component="legend">你是否同意此评分？</FormLabel>
            <RadioGroup value={feedbackAgree} onChange={(e) => setFeedbackAgree(e.target.value)}>
              <FormControlLabel value="agree" control={<Radio size="small" />} label="同意" />
              <FormControlLabel value="too_high" control={<Radio size="small" />} label="偏高" />
              <FormControlLabel value="too_low" control={<Radio size="small" />} label="偏低" />
              <FormControlLabel value="wrong" control={<Radio size="small" />} label="明显错误" />
            </RadioGroup>
          </FormControl>
          {feedbackAgree !== 'agree' && (
            <TextField
              label="你认为合理的分数"
              type="number"
              size="small"
              value={feedbackScore}
              onChange={(e) => setFeedbackScore(e.target.value)}
              inputProps={{ min: 0, max: dimension.max_score, step: 0.5 }}
              sx={{ mb: 2, width: 200 }}
            />
          )}
          <TextField
            label="具体原因或建议"
            multiline
            rows={3}
            fullWidth
            value={feedbackSuggestion}
            onChange={(e) => setFeedbackSuggestion(e.target.value)}
            placeholder="描述你认为评分不合理的原因，或给出改进建议..."
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setFeedbackOpen(false)}>取消</Button>
          <Button variant="contained" onClick={handleFeedbackSubmit}>提交反馈</Button>
        </DialogActions>
      </Dialog>

      {/* 提交成功提示 */}
      <Snackbar
        open={feedbackSubmitted}
        autoHideDuration={3000}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert severity="success" variant="filled">
          反馈已记录，感谢你的意见！
        </Alert>
      </Snackbar>
    </Card>
  );
};

export default DimensionCard;
