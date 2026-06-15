import React, { useEffect, useState, useContext } from 'react';
import {
  Box,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Divider,
  Typography,
} from '@mui/material';
import Grid2 from '@mui/material/Grid2';
import WarningIcon from '@mui/icons-material/Warning';
import { getStandards, type StandardsResponse, type StandardLevel } from '../api/client';
import { ToastContext } from '../App';

// 类目颜色
const CATEGORY_COLORS: Record<string, string> = {
  '教学内容': '#1976d2',
  '教学方法': '#2e7d32',
  '教学表现力': '#ed6c02',
  '教学规范': '#ed6c02',
  '课堂教学效果': '#9c27b0',
};

// 班型标签
const LEVEL_LABELS: Record<string, string> = {
  'L1_L3': '学前班型（L1-L3）',
  'L4_L6': '小低班型（L4-L6）',
  'L7_L9': '小高班型（L7-L9）',
  'QC_v4': '新版课中质检 v4',
  'QC-v4': '新版课中质检 v4',
};

const StandardsPage: React.FC = () => {
  const { showToast } = useContext(ToastContext);
  const [standards, setStandards] = useState<StandardsResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchStandards = async () => {
      try {
        const data = await getStandards();
        setStandards(data);
      } catch (err: any) {
        showToast('获取评价标准失败', 'error');
      } finally {
        setLoading(false);
      }
    };
    fetchStandards();
  }, [showToast]);

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (!standards) {
    return (
      <Box sx={{ textAlign: 'center', py: 8 }}>
        <Typography variant="h6" color="text.secondary">
          暂无评价标准数据
        </Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ maxWidth: 1000, mx: 'auto', py: 3, px: 2 }}>
      <Typography variant="h4" sx={{ mb: 1 }}>
        QC-v4 评价标准
      </Typography>
      <Typography variant="body1" color="text.secondary" sx={{ mb: 3 }}>
        基于火花思维教学评价体系，包含不同班型的评分维度和红线淘汰行为
      </Typography>

      {/* 各班型评分标准 */}
      {Object.entries(standards.levels).map(([levelKey, levelData]) => (
        <LevelCard key={levelKey} levelKey={levelKey} level={levelData} />
      ))}

      {/* 红线淘汰行为 */}
      {standards.red_lines.length > 0 && (
        <Card sx={{ mt: 3, border: '2px solid', borderColor: 'error.light' }}>
          <CardContent>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
              <WarningIcon color="error" />
              <Typography variant="h6" color="error" sx={{ fontWeight: 700 }}>
                红线淘汰行为（一票否决）
              </Typography>
            </Box>
            {standards.red_lines.map((rl, idx) => (
              <Box key={rl.id || idx} sx={{ mb: 2 }}>
                <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                  {rl.id}：{rl.name}
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                  {rl.description}
                </Typography>
              </Box>
            ))}
          </CardContent>
        </Card>
      )}

      {/* 等级制 */}
      {standards.grade_system.length > 0 && (
        <Card sx={{ mt: 3 }}>
          <CardContent>
            <Typography variant="h6" sx={{ fontWeight: 600, mb: 2 }}>
              等级划分（合格线 75 分）
            </Typography>
            <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
              {standards.grade_system.map((g, idx) => (
                <Chip
                  key={idx}
                  label={`${g.name}：${g.min}-${g.max} 分`}
                  sx={{
                    bgcolor: g.color === 'red' ? '#c62828' : g.color === 'orange' ? '#ed6c02' : g.color === 'blue' ? '#1565c0' : '#2e7d32',
                    color: 'white',
                    fontWeight: 600,
                    px: 1,
                  }}
                />
              ))}
            </Box>
          </CardContent>
        </Card>
      )}
    </Box>
  );
};

/** 班型标准卡片 */
const LevelCard: React.FC<{ levelKey: string; level: StandardLevel }> = ({ levelKey, level }) => {
  // 按类目分组
  const categoryMap = new Map<string, typeof level.dimensions>();
  for (const dim of level.dimensions) {
    const cat = dim.category || '其他';
    if (!categoryMap.has(cat)) categoryMap.set(cat, []);
    categoryMap.get(cat)!.push(dim);
  }

  return (
    <Card sx={{ mb: 2 }}>
      <CardContent>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
          <Typography variant="h6" sx={{ fontWeight: 700 }}>
            {LEVEL_LABELS[levelKey] || levelKey}
          </Typography>
        </Box>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
          {level.description}
        </Typography>
        {level.student_focus && (
          <Typography variant="body2" color="text.secondary">
            关注重点：{level.student_focus}
          </Typography>
        )}

        <Divider sx={{ my: 2 }} />

        {/* 按类目展示维度 */}
        {Array.from(categoryMap.entries()).map(([category, dims]) => (
          <Box key={category} sx={{ mb: 2 }}>
            <Typography
              variant="subtitle1"
              sx={{
                fontWeight: 600,
                color: CATEGORY_COLORS[category] || 'text.primary',
                mb: 1,
                display: 'flex',
                alignItems: 'center',
                gap: 1,
              }}
            >
              <Box
                sx={{
                  width: 12,
                  height: 12,
                  borderRadius: '50%',
                  bgcolor: CATEGORY_COLORS[category] || '#757575',
                }}
              />
              {category}
            </Typography>
            <Grid2 container spacing={1}>
              {dims.map((dim) => (
                <Grid2 size={{ xs: 12, sm: 6 }} key={dim.name}>
                  <Box
                    sx={{
                      p: 1.5,
                      borderRadius: 1,
                      bgcolor: 'action.hover',
                      border: '1px solid',
                      borderColor: 'divider',
                    }}
                  >
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        {dim.name}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {dim.max_score}分 × {dim.weight}
                      </Typography>
                    </Box>
                    {dim.criteria_excellent && (
                      <Typography variant="caption" color="success.main" sx={{ display: 'block' }}>
                        优：{dim.criteria_excellent.substring(0, 60)}...
                      </Typography>
                    )}
                    {dim.criteria_poor && (
                      <Typography variant="caption" color="error.main" sx={{ display: 'block' }}>
                        差：{dim.criteria_poor.substring(0, 60)}...
                      </Typography>
                    )}
                  </Box>
                </Grid2>
              ))}
            </Grid2>
          </Box>
        ))}

        {/* 质检清单 */}
        {level.quality_checklist.length > 0 && (
          <Box sx={{ mt: 2 }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 0.5 }}>
              质检清单
            </Typography>
            <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
              {level.quality_checklist.map((item, idx) => (
                <Chip key={idx} label={item} size="small" variant="outlined" />
              ))}
            </Box>
          </Box>
        )}
      </CardContent>
    </Card>
  );
};

export default StandardsPage;
