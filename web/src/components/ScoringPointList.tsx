import React from 'react';
import {
  Box,
  Typography,
  Chip,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
} from '@mui/material';
import AddCircleIcon from '@mui/icons-material/AddCircle';
import RemoveCircleIcon from '@mui/icons-material/RemoveCircle';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import type { ScoringPoint } from '../api/client';

interface ScoringPointListProps {
  points: ScoringPoint[];
  /** 点击时间戳回调，跳转视频 */
  onSeekTo?: (seconds: number) => void;
}

/** ScoringPoint 列表渲染 */
const ScoringPointList: React.FC<ScoringPointListProps> = ({ points, onSeekTo }) => {
  if (!points || points.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary" sx={{ py: 1 }}>
        暂无评分证据点
      </Typography>
    );
  }

  const formatTime = (seconds: number | null): string => {
    if (seconds === null || seconds === undefined) return '--:--';
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  return (
    <List dense disablePadding>
      {points.map((point, index) => {
        const isPositive = point.type === '+';

        return (
          <ListItem
            key={index}
            sx={{
              px: 1,
              py: 0.5,
              borderRadius: 1,
              '&:hover': { bgcolor: 'action.hover' },
            }}
          >
            <ListItemIcon sx={{ minWidth: 32 }}>
              {isPositive ? (
                <AddCircleIcon fontSize="small" color="success" />
              ) : (
                <RemoveCircleIcon fontSize="small" color="error" />
              )}
            </ListItemIcon>
            <ListItemText
              primary={
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
                  <Typography variant="body2" sx={{ fontWeight: 500 }}>
                    {point.reason}
                  </Typography>
                  {point.at !== null && point.at !== undefined && (
                    <Chip
                      icon={<PlayArrowIcon sx={{ fontSize: '14px !important' }} />}
                      label={formatTime(point.at)}
                      size="small"
                      variant="outlined"
                      color={isPositive ? 'success' : 'error'}
                      onClick={() => onSeekTo?.(point.at!)}
                      sx={{ cursor: 'pointer', height: 24, '& .MuiChip-icon': { ml: 0.5 } }}
                    />
                  )}
                </Box>
              }
              secondary={
                point.quote ? (
                  <Typography
                    variant="body2"
                    color="text.secondary"
                    sx={{
                      mt: 0.5,
                      fontStyle: 'italic',
                      borderLeft: '3px solid',
                      borderColor: isPositive ? 'success.light' : 'error.light',
                      pl: 1,
                    }}
                  >
                    "{point.quote}"
                  </Typography>
                ) : undefined
              }
            />
          </ListItem>
        );
      })}
    </List>
  );
};

export default ScoringPointList;
