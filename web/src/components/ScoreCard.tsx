import React from 'react';
import { Box, Chip, Typography } from '@mui/material';
import type { ScoreCard } from '../api/client';

const GRADE_COLORS: Record<string, string> = {
  优: '#15803d',
  良: '#1d4ed8',
  中: '#b45309',
  差: '#b91c1c',
  待改进: '#b45309',
  不合格: '#b91c1c',
  不达标: '#b91c1c',
};

interface ScoreCardProps {
  scoreCard: ScoreCard;
}

const ScoreCardDisplay: React.FC<ScoreCardProps> = ({ scoreCard }) => {
  const gradeColor = GRADE_COLORS[scoreCard.grade] || '#475569';
  const percentage = scoreCard.total_max > 0
    ? Math.round((scoreCard.total_score / scoreCard.total_max) * 100)
    : 0;

  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: { xs: '1fr', sm: '1fr auto' },
        gap: 2,
        alignItems: 'center',
        p: 3,
        borderRadius: 2,
        bgcolor: '#ffffff',
        border: '1px solid #dbe4d3',
      }}
    >
      <Box>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
          综合授课质量得分
        </Typography>
        <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 1 }}>
          <Typography variant="h3" sx={{ fontWeight: 800, color: 'primary.main', lineHeight: 1 }}>
            {scoreCard.total_score.toFixed(1)}
          </Typography>
          <Typography color="text.secondary">/ {scoreCard.total_max.toFixed(0)} 分</Typography>
        </Box>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.75 }}>
          得分率 {percentage}% · 标准 {scoreCard.level || '未标注'}
        </Typography>
      </Box>
      <Box sx={{ textAlign: { xs: 'left', sm: 'right' } }}>
        <Chip
          label={scoreCard.grade || '未评级'}
          sx={{ bgcolor: gradeColor, color: '#ffffff', fontWeight: 700, fontSize: 16, height: 38, px: 1 }}
        />
        {scoreCard.red_line_violation && (
          <Typography variant="body2" color="error" sx={{ mt: 1, fontWeight: 700 }}>
            存在红线风险
          </Typography>
        )}
      </Box>
    </Box>
  );
};

export default ScoreCardDisplay;
