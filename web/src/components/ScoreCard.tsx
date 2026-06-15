import React from 'react';
import { Box, Typography } from '@mui/material';
import type { ScoreCard } from '../api/client';

// 等级颜色映射
const GRADE_COLORS: Record<string, string> = {
  '优': '#2e7d32',
  '良': '#1565c0',
  '创新': '#2e7d32',
  '挑战': '#1565c0',
  '博学': '#ed6c02',
  '待改进': '#ed6c02',
  '中': '#ed6c02',
  '差': '#c62828',
  '不合格': '#c62828',
  '不达标': '#c62828',
  '不达标（红线违规）': '#c62828',
};

interface ScoreCardProps {
  scoreCard: ScoreCard;
}

/** 总分大字 + 等级徽章 */
const ScoreCardDisplay: React.FC<ScoreCardProps> = ({ scoreCard }) => {
  const gradeColor = GRADE_COLORS[scoreCard.grade] || '#757575';
  const percentage = scoreCard.total_max > 0
    ? ((scoreCard.total_score / scoreCard.total_max) * 100).toFixed(1)
    : '0.0';

  return (
    <Box
      sx={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 4,
        p: 4,
        borderRadius: 3,
        background: 'linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%)',
        boxShadow: '0 4px 20px rgba(21, 101, 192, 0.15)',
      }}
    >
      {/* 总分 */}
      <Box sx={{ textAlign: 'center' }}>
        <Typography variant="h2" sx={{ fontWeight: 800, color: '#1565c0', lineHeight: 1 }}>
          {scoreCard.total_score.toFixed(1)}
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
          满分 {scoreCard.total_max.toFixed(0)} 分 · 得分率 {percentage}%
        </Typography>
      </Box>

      {/* 分隔线 */}
      <Box
        sx={{
          width: 2,
          height: 80,
          bgcolor: 'rgba(21, 101, 192, 0.2)',
          borderRadius: 1,
        }}
      />

      {/* 等级徽章 */}
      <Box sx={{ textAlign: 'center' }}>
        <Box
          sx={{
            display: 'inline-block',
            px: 3,
            py: 1.5,
            borderRadius: 2,
            bgcolor: gradeColor,
            color: 'white',
            fontWeight: 700,
            fontSize: '1.5rem',
            letterSpacing: 2,
          }}
        >
          {scoreCard.grade || '—'}
        </Box>
        {scoreCard.red_line_violation && (
          <Typography variant="body2" color="error" sx={{ mt: 1, fontWeight: 600 }}>
            红线违规
          </Typography>
        )}
        {scoreCard.level && (
          <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
            {scoreCard.level}
          </Typography>
        )}
      </Box>
    </Box>
  );
};

export default ScoreCardDisplay;
