import React, { useMemo } from 'react';
import {
  RadarChart,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  Legend,
  ResponsiveContainer,
  Tooltip,
} from 'recharts';
import type { ScoreDimension } from '../api/client';

// 4 大类目颜色
const CATEGORY_COLORS: Record<string, string> = {
  '教学内容': '#1976d2',
  '教学方法': '#2e7d32',
  '教学表现力': '#ed6c02',
  '教学规范': '#ed6c02',
  '课堂教学效果': '#9c27b0',
};

interface RadarChartProps {
  dimensions: ScoreDimension[];
  height?: number;
}

/** 十维雷达图 — 4 类目着色 */
const ScoreRadarChart: React.FC<RadarChartProps> = ({ dimensions, height = 400 }) => {
  const data = useMemo(() => {
    return dimensions.map((dim) => ({
      dimension: dim.name,
      score: dim.score,
      maxScore: dim.max_score,
      category: dim.grade || '中',
      fullMark: dim.max_score,
    }));
  }, [dimensions]);

  // 按类目分组渲染多个 Radar
  const categories = useMemo(() => {
    const cats = new Map<string, ScoreDimension[]>();
    dimensions.forEach((dim) => {
      // 通过原始维度的 category 属性分组，这里用名称推断
      const cat = getCategoryForDimension(dim.name);
      if (!cats.has(cat)) cats.set(cat, []);
      cats.get(cat)!.push(dim);
    });
    return cats;
  }, [dimensions]);

  // 简单方案：统一一个 Radar，颜色用渐变
  return (
    <ResponsiveContainer width="100%" height={height}>
      <RadarChart data={data} cx="50%" cy="50%" outerRadius="75%">
        <PolarAngleAxis
          dataKey="dimension"
          tick={{ fontSize: 12, fill: '#555' }}
        />
        <PolarRadiusAxis
          angle={90}
          domain={[0, 'auto']}
          tick={{ fontSize: 10 }}
        />
        <Radar
          name="得分"
          dataKey="score"
          stroke="#1565c0"
          fill="#1565c0"
          fillOpacity={0.25}
          strokeWidth={2}
        />
        <Radar
          name="满分"
          dataKey="maxScore"
          stroke="#e0e0e0"
          fill="#e0e0e0"
          fillOpacity={0.05}
          strokeWidth={1}
          strokeDasharray="5 5"
        />
        <Tooltip
          formatter={(value: number, name: string) => {
            if (name === '得分') return [`${value.toFixed(1)} 分`, name];
            if (name === '满分') return [`${value.toFixed(1)} 分`, name];
            return [value, name];
          }}
        />
        <Legend />
      </RadarChart>
    </ResponsiveContainer>
  );
};

/** 根据维度名称推断类目 */
function getCategoryForDimension(name: string): string {
  const contentDims = ['知识传授', '熟练程度', '重点难点'];
  const methodDims = ['启发引导', '教学灵活性', '思维方法', '教学方式方法', '教学逻辑', '教学方法灵活应用'];
  const expressionDims = ['课堂互动', '课堂节奏', '语言表达', '关注激励', '数学表达能力', '关注互动', '组织教学', '仪表教态', '语言表达及板书设计', '关注公平'];
  const effectDims = ['学习效果', '效果外化', '迁移应用', '课堂效果及整体印象', '板书设计'];

  if (contentDims.includes(name)) return '教学内容';
  if (methodDims.includes(name)) return '教学方法';
  if (expressionDims.includes(name)) return '教学规范';
  if (effectDims.includes(name)) return '课堂教学效果';
  return '其他';
}

export const getCategoryColor = getCategoryForDimension;

export default ScoreRadarChart;
