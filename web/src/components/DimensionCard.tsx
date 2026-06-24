import React, { useState } from 'react';
import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Collapse,
  IconButton,
  LinearProgress,
  Typography,
} from '@mui/material';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import FeedbackIcon from '@mui/icons-material/Feedback';
import TextFieldsIcon from '@mui/icons-material/TextFields';
import VisibilityIcon from '@mui/icons-material/Visibility';

import type { ScoreDimension } from '../api/client';
import ScoringPointList from './ScoringPointList';

const GRADE_COLORS: Record<string, string> = {
  优: '#15803d',
  良: '#1d4ed8',
  中: '#b45309',
  差: '#b91c1c',
};

interface DimensionCardProps {
  dimension: ScoreDimension;
  onSeekTo?: (seconds: number) => void;
  defaultExpanded?: boolean;
  onFeedback?: (dimension: ScoreDimension) => void;
}

const DimensionCard: React.FC<DimensionCardProps> = ({
  dimension,
  onSeekTo,
  defaultExpanded = false,
  onFeedback,
}) => {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const percentage = dimension.max_score > 0 ? (dimension.score / dimension.max_score) * 100 : 0;
  const gradeColor = GRADE_COLORS[dimension.grade] || '#64748b';
  const isVision = dimension.source_model === 'vision';
  const isVisionReview = dimension.source_model === 'vision_enhanced';
  const sourceLabel = isVision ? '视觉证据' : isVisionReview ? '视觉待复核' : '文本证据';

  return (
    <Card sx={{ mb: 1.5 }}>
      <CardContent sx={{ py: 2, '&:last-child': { pb: 2 } }}>
        <Box
          sx={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 2, alignItems: 'center', cursor: 'pointer' }}
          onClick={() => setExpanded((value) => !value)}
        >
          <Box sx={{ minWidth: 0 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap', mb: 1 }}>
              <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                {dimension.name}
              </Typography>
              <Chip label={dimension.grade || '未评级'} size="small" sx={{ bgcolor: gradeColor, color: '#ffffff', fontWeight: 700 }} />
              <Chip
                icon={isVision || isVisionReview ? <VisibilityIcon /> : <TextFieldsIcon />}
                label={sourceLabel}
                size="small"
                variant="outlined"
              />
            </Box>
            <LinearProgress
              variant="determinate"
              value={Math.min(100, Math.max(0, percentage))}
              sx={{
                height: 7,
                borderRadius: 4,
                bgcolor: '#e5e7eb',
                '& .MuiLinearProgress-bar': { bgcolor: gradeColor },
              }}
            />
          </Box>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Typography variant="body2" sx={{ fontWeight: 700, color: 'primary.main', whiteSpace: 'nowrap' }}>
              {dimension.score.toFixed(1)} / {dimension.max_score.toFixed(0)}
            </Typography>
            <IconButton size="small">
              {expanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
            </IconButton>
          </Box>
        </Box>

        <Collapse in={expanded}>
          <Box sx={{ pt: 2 }}>
            {dimension.evidence && (
              <Box sx={{ mb: 1.5 }}>
                <Typography variant="caption" color="text.secondary">评价依据</Typography>
                <Typography variant="body2" sx={{ lineHeight: 1.7 }}>{dimension.evidence}</Typography>
              </Box>
            )}
            {dimension.details && (
              <Box sx={{ mb: 1.5 }}>
                <Typography variant="caption" color="text.secondary">补充说明</Typography>
                <Typography variant="body2" sx={{ lineHeight: 1.7 }}>{dimension.details}</Typography>
              </Box>
            )}
            {dimension.scoring_points?.length > 0 && (
              <Box sx={{ mb: 1 }}>
                <Typography variant="caption" color="text.secondary">
                  证据片段 {dimension.scoring_points.length} 条
                </Typography>
                <ScoringPointList points={dimension.scoring_points} onSeekTo={onSeekTo} />
              </Box>
            )}
            <Box sx={{ display: 'flex', justifyContent: 'flex-end', mt: 1 }}>
              <Button
                size="small"
                startIcon={<FeedbackIcon />}
                onClick={(event) => {
                  event.stopPropagation();
                  onFeedback?.(dimension);
                }}
              >
                人工校对
              </Button>
            </Box>
          </Box>
        </Collapse>
      </CardContent>
    </Card>
  );
};

export default DimensionCard;
