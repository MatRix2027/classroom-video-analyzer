import React, { useEffect, useState, useContext } from 'react';
import {
  Box,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Divider,
  Typography,
  Accordion,
  AccordionSummary,
  AccordionDetails,
} from '@mui/material';
import Grid2 from '@mui/material/Grid2';
import WarningIcon from '@mui/icons-material/Warning';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import DesignServicesIcon from '@mui/icons-material/DesignServices';
import SchoolIcon from '@mui/icons-material/School';
import DashboardIcon from '@mui/icons-material/Dashboard';
import GavelIcon from '@mui/icons-material/Gavel';
import EmojiEventsIcon from '@mui/icons-material/EmojiEvents';
import CalculateIcon from '@mui/icons-material/Calculate';
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
  'L1_L3': '学前班型（L1-L3）兴趣启蒙',
  'L4_L6': '小低班型（L4-L6）习惯养成',
  'L7_L9': '小高班型（L7-L9）能力构建',
  'QC_v4': '综合评价 v5.0 · 通用版',
  'QC-v4': '综合评价 v5.0 · 通用版',
};

/** 设计哲学说明 */
const DESIGN_PHILOSOPHY = [
  {
    title: '维度统一',
    desc: '三大班型共享相同维度名称与满分，确保评价体系的跨段可比性',
    icon: '🔗',
  },
  {
    title: '细则差异化',
    desc: '同一维度在不同学段有不同的评分细则，适配各阶段教学重点',
    icon: '🎯',
  },
  {
    title: '权重论证',
    desc: '权重经教研团队论证，体现各维度对教学质量的影响程度差异',
    icon: '⚖️',
  },
];

/** 学段画像 */
const LEVEL_PROFILES = [
  {
    level: 'L1-L3',
    title: '兴趣启蒙',
    focus: '激发好奇心、培养探索欲、建立学科初印象',
    color: '#1565c0',
    bg: 'linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%)',
  },
  {
    level: 'L4-L6',
    title: '习惯养成',
    focus: '学习习惯养成、思维方法训练、基础能力夯实',
    color: '#2e7d32',
    bg: 'linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%)',
  },
  {
    level: 'L7-L9',
    title: '能力构建',
    focus: '深度思维训练、自主学习能力、知识迁移应用',
    color: '#7b1fa2',
    bg: 'linear-gradient(135deg, #f3e5f5 0%, #e1bee7 100%)',
  },
];

/** 10维度概览（含子维度拆分） */
const DIMENSIONS_OVERVIEW = [
  {
    name: '知识传授',
    category: '教学内容',
    weight: 0.10,
    maxScore: 10,
    subDimensions: [],
    desc: '学科知识的准确性与逻辑性',
  },
  {
    name: '熟练程度',
    category: '教学内容',
    weight: 0.10,
    maxScore: 10,
    subDimensions: [],
    desc: '教师对内容的驾驭与演绎能力',
  },
  {
    name: '重点难点',
    category: '教学内容',
    weight: 0.10,
    maxScore: 10,
    subDimensions: [],
    desc: '重难点的识别、讲解与突破',
  },
  {
    name: '教学逻辑',
    category: '教学方法',
    weight: 0.13,
    maxScore: 13,
    subDimensions: ['知识链条完整性', '逻辑推进节奏', '认知脚手架搭建'],
    desc: '教学设计的逻辑性与层次感',
    sourceType: 'vision_enhanced' as const,
  },
  {
    name: '教学方式方法',
    category: '教学方法',
    weight: 0.12,
    maxScore: 12,
    subDimensions: [],
    desc: '教学方法的多样性与适配性',
  },
  {
    name: '组织教学',
    category: '教学规范',
    weight: 0.13,
    maxScore: 13,
    subDimensions: [],
    desc: '课堂组织与时间管理',
    sourceType: 'vision_enhanced' as const,
  },
  {
    name: '关注公平',
    category: '教学规范',
    weight: 0.08,
    maxScore: 8,
    subDimensions: ['提问覆盖面', '回应等待时间', '边缘学生关注'],
    desc: '教学机会的公平分配',
    sourceType: 'vision_enhanced' as const,
  },
  {
    name: '仪表教态',
    category: '教学规范',
    weight: 0.06,
    maxScore: 6,
    subDimensions: [],
    desc: '教师外在形象与精神状态',
    sourceType: 'vision' as const,
  },
  {
    name: '语言表达及板书设计',
    category: '教学规范',
    weight: 0.08,
    maxScore: 8,
    subDimensions: [],
    desc: '语言表达的清晰度与板书的辅助效果',
    sourceType: 'vision' as const,
  },
  {
    name: '课堂效果及整体印象',
    category: '课堂教学效果',
    weight: 0.10,
    maxScore: 10,
    subDimensions: ['学习效果外化', '学生参与度', '目标达成度'],
    desc: '课堂整体教学效果与学习反馈',
    sourceType: 'vision_enhanced' as const,
  },
];

/** 评分纪律7条硬约束 */
const SCORING_DISCIPLINE = [
  { id: 1, rule: '红线一票否决：触碰任一红线，总分直接归零，等级判定为"不合格"' },
  { id: 2, rule: '维度独立评分：每个维度独立打分，不得因某一维度表现优异而补偿另一维度' },
  { id: 3, rule: '证据导向：评分必须基于视频中的客观证据，禁止主观推测或预设立场' },
  { id: 4, rule: '得分率换算：各维度原始得分÷满分×权重=加权得分，总分=加权得分之和' },
  { id: 5, rule: '多轮收敛：若两轮评分差异>5分，触发第三轮仲裁评分' },
  { id: 6, rule: '等级阈值硬约束：优≥85、良≥75、待改进≥50、不合格<50，不允许模糊评级' },
  { id: 7, rule: '视觉融合约束：仪表教态、语言表达及板书设计必须有视觉评分；关注公平和课堂效果按文本60%+视觉40%融合' },
];

/** 等级制说明 */
const GRADE_LEVELS = [
  { name: '优', range: '85-100', color: '#2e7d32', desc: '教学表现卓越，各维度均达优秀水平' },
  { name: '良', range: '75-85', color: '#1565c0', desc: '教学表现良好，部分维度有提升空间' },
  { name: '待改进', range: '50-75', color: '#ed6c02', desc: '教学表现一般，多个维度需要改进' },
  { name: '不合格', range: '0-50', color: '#c62828', desc: '教学表现不达标，或触碰红线淘汰' },
];

/** 数学课专项5项检查 */
const MATH_SPECIAL_CHECKS = [
  { id: 1, item: '数学语言规范性', desc: '教师是否使用规范数学术语，避免口语化表述' },
  { id: 2, item: '数学思维方法', desc: '是否渗透归纳、演绎、类比等数学思维方法' },
  { id: 3, item: '数学表达能力', desc: '学生是否有机会用数学语言表达思考过程' },
  { id: 4, item: '数形结合', desc: '是否有效运用数形结合思想辅助理解' },
  { id: 5, item: '解题策略多样性', desc: '是否鼓励一题多解，培养策略意识' },
];

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
      {/* 页面标题 */}
      <Typography variant="h4" sx={{ mb: 1, fontWeight: 800 }}>
        综合评价标准 v5.0 · 通用版
      </Typography>
      <Typography variant="body1" color="text.secondary" sx={{ mb: 3 }}>
        深度重构版 · 基于火花思维教学评价体系，维度统一、细则差异化、权重论证
      </Typography>

      {/* ── 设计哲学卡片 ── */}
      <Card sx={{ mb: 3, background: 'linear-gradient(135deg, #f5f7fa 0%, #e8eaf6 100%)' }}>
        <CardContent>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
            <DesignServicesIcon sx={{ color: '#4527a0' }} />
            <Typography variant="h6" sx={{ fontWeight: 700, color: '#4527a0' }}>
              设计哲学
            </Typography>
          </Box>
          <Grid2 container spacing={2}>
            {DESIGN_PHILOSOPHY.map((p) => (
              <Grid2 size={{ xs: 12, sm: 4 }} key={p.title}>
                <Box
                  sx={{
                    p: 2,
                    borderRadius: 2,
                    bgcolor: 'rgba(255,255,255,0.7)',
                    border: '1px solid',
                    borderColor: 'divider',
                  }}
                >
                  <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 0.5 }}>
                    {p.icon} {p.title}
                  </Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.6 }}>
                    {p.desc}
                  </Typography>
                </Box>
              </Grid2>
            ))}
          </Grid2>
        </CardContent>
      </Card>

      {/* ── 学段画像卡片 ── */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
            <SchoolIcon sx={{ color: '#1565c0' }} />
            <Typography variant="h6" sx={{ fontWeight: 700 }}>
              学段画像
            </Typography>
          </Box>
          <Grid2 container spacing={2}>
            {LEVEL_PROFILES.map((profile) => (
              <Grid2 size={{ xs: 12, sm: 4 }} key={profile.level}>
                <Box
                  sx={{
                    p: 2,
                    borderRadius: 2,
                    background: profile.bg,
                    border: '1px solid',
                    borderColor: 'divider',
                  }}
                >
                  <Typography
                    variant="subtitle2"
                    sx={{ fontWeight: 700, color: profile.color, mb: 0.5 }}
                  >
                    {profile.level} · {profile.title}
                  </Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.6 }}>
                    {profile.focus}
                  </Typography>
                </Box>
              </Grid2>
            ))}
          </Grid2>
        </CardContent>
      </Card>

      {/* ── 10维度概览 ── */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
            <DashboardIcon sx={{ color: '#2e7d32' }} />
            <Typography variant="h6" sx={{ fontWeight: 700 }}>
              10维度概览（总分100）
            </Typography>
          </Box>
          <Grid2 container spacing={1.5}>
            {DIMENSIONS_OVERVIEW.map((dim) => {
              const catColor = CATEGORY_COLORS[dim.category] || '#757575';
              return (
                <Grid2 size={{ xs: 12, sm: 6 }} key={dim.name}>
                  <Box
                    sx={{
                      p: 1.5,
                      borderRadius: 2,
                      bgcolor: 'action.hover',
                      border: '1px solid',
                      borderColor: 'divider',
                    }}
                  >
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.5 }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <Box sx={{ width: 10, height: 10, borderRadius: '50%', bgcolor: catColor }} />
                        <Typography variant="body2" sx={{ fontWeight: 700 }}>
                          {dim.name}
                        </Typography>
                        {dim.sourceType === 'vision' && (
                          <Chip label="视觉" size="small" sx={{ height: 18, fontSize: '0.65rem', bgcolor: '#e3f2fd', color: '#1565c0' }} />
                        )}
                        {dim.sourceType === 'vision_enhanced' && (
                          <Chip label="视觉增强" size="small" sx={{ height: 18, fontSize: '0.65rem', bgcolor: '#fff3e0', color: '#e65100' }} />
                        )}
                      </Box>
                      <Typography variant="caption" color="text.secondary">
                        {dim.maxScore}分 × {dim.weight}
                      </Typography>
                    </Box>
                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
                      {dim.desc}
                    </Typography>
                    {dim.subDimensions.length > 0 && (
                      <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
                        {dim.subDimensions.map((sub) => (
                          <Chip
                            key={sub}
                            label={sub}
                            size="small"
                            variant="outlined"
                            sx={{ height: 20, fontSize: '0.65rem' }}
                          />
                        ))}
                      </Box>
                    )}
                  </Box>
                </Grid2>
              );
            })}
          </Grid2>
        </CardContent>
      </Card>

      {/* ── 评分纪律 ── */}
      <Card sx={{ mb: 3, border: '2px solid', borderColor: '#4527a0' }}>
        <CardContent>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
            <GavelIcon sx={{ color: '#4527a0' }} />
            <Typography variant="h6" sx={{ fontWeight: 700, color: '#4527a0' }}>
              评分纪律（7条硬约束）
            </Typography>
          </Box>
          {SCORING_DISCIPLINE.map((item) => (
            <Box key={item.id} sx={{ mb: 1.5, display: 'flex', gap: 1.5, alignItems: 'flex-start' }}>
              <Chip
                label={item.id}
                size="small"
                sx={{
                  bgcolor: '#4527a0',
                  color: 'white',
                  fontWeight: 700,
                  minWidth: 28,
                  height: 24,
                  '& .MuiChip-label': { px: 0.5 },
                }}
              />
              <Typography variant="body2" sx={{ lineHeight: 1.7 }}>
                {item.rule}
              </Typography>
            </Box>
          ))}
        </CardContent>
      </Card>

      {/* ── 等级制说明 ── */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
            <EmojiEventsIcon sx={{ color: '#ed6c02' }} />
            <Typography variant="h6" sx={{ fontWeight: 700 }}>
              等级制说明
            </Typography>
          </Box>
          <Grid2 container spacing={2}>
            {GRADE_LEVELS.map((grade) => (
              <Grid2 size={{ xs: 12, sm: 6, md: 3 }} key={grade.name}>
                <Box
                  sx={{
                    p: 2,
                    borderRadius: 2,
                    bgcolor: 'action.hover',
                    border: '2px solid',
                    borderColor: grade.color,
                    textAlign: 'center',
                  }}
                >
                  <Typography
                    variant="h4"
                    sx={{ fontWeight: 800, color: grade.color, lineHeight: 1.2 }}
                  >
                    {grade.name}
                  </Typography>
                  <Typography variant="h6" sx={{ color: grade.color, mb: 1 }}>
                    {grade.range} 分
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {grade.desc}
                  </Typography>
                </Box>
              </Grid2>
            ))}
          </Grid2>
        </CardContent>
      </Card>

      {/* ── 数学课专项5项检查 ── */}
      <Card sx={{ mb: 3, background: 'linear-gradient(135deg, #fff8e1 0%, #ffecb3 100%)' }}>
        <CardContent>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
            <CalculateIcon sx={{ color: '#e65100' }} />
            <Typography variant="h6" sx={{ fontWeight: 700, color: '#e65100' }}>
              数学课专项5项检查
            </Typography>
          </Box>
          {MATH_SPECIAL_CHECKS.map((item) => (
            <Box key={item.id} sx={{ mb: 1.5, display: 'flex', gap: 1.5, alignItems: 'flex-start' }}>
              <Chip
                label={`M${item.id}`}
                size="small"
                sx={{
                  bgcolor: '#e65100',
                  color: 'white',
                  fontWeight: 700,
                  minWidth: 36,
                  height: 24,
                  '& .MuiChip-label': { px: 0.5 },
                }}
              />
              <Box>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>
                  {item.item}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {item.desc}
                </Typography>
              </Box>
            </Box>
          ))}
        </CardContent>
      </Card>

      {/* ── 各班型评分标准（可折叠） ── */}
      <Typography variant="h6" sx={{ fontWeight: 700, mb: 2 }}>
        各班型评分细则
      </Typography>
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

      {/* 等级制（API返回的） */}
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
