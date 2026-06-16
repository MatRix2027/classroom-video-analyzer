import React, { useContext, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Divider,
  Typography,
} from '@mui/material';
import OpenInNewIcon from '@mui/icons-material/OpenInNew';

import { ToastContext } from '../App';
import { getCalibrationFeedbackList, type CalibrationFeedback } from '../api/client';

const TYPE_LABELS: Record<string, string> = {
  overall_score: '整体结论',
  dimension_score: '维度评分',
  visual_evidence: '视觉证据',
  text_evidence: '文本证据',
  report_wording: '报告表达',
};

const FeedbackPage: React.FC = () => {
  const navigate = useNavigate();
  const { showToast } = useContext(ToastContext);
  const [items, setItems] = useState<CalibrationFeedback[]>([]);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);

  useEffect(() => {
    getCalibrationFeedbackList()
      .then((data) => {
        setItems(data.items);
        setTotal(data.total);
      })
      .catch(() => showToast('获取校对记录失败', 'error'))
      .finally(() => setLoading(false));
  }, [showToast]);

  if (loading) {
    return <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}><CircularProgress /></Box>;
  }

  return (
    <Box sx={{ maxWidth: 1120, mx: 'auto', px: 3, py: 4 }}>
      <Box sx={{ mb: 3 }}>
        <Typography variant="h4">人工校对记录</Typography>
        <Typography color="text.secondary">
          共 {total} 条校对反馈，用于沉淀评分偏差、视觉证据偏差和报告表达优化案例。
        </Typography>
      </Box>

      {items.length === 0 ? (
        <Card>
          <CardContent>
            <Typography color="text.secondary">
              暂无校对反馈。完成分析后，可在看板或报告页点击“人工校对”提交。
            </Typography>
          </CardContent>
        </Card>
      ) : (
        <Box sx={{ display: 'grid', gap: 1.5 }}>
          {items.map((item) => (
            <Card key={item.id}>
              <CardContent>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 2, alignItems: 'flex-start' }}>
                  <Box sx={{ minWidth: 0 }}>
                    <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mb: 1 }}>
                      <Chip size="small" label={TYPE_LABELS[item.feedback_type] || item.feedback_type} color="primary" />
                      <Chip size="small" label={item.status === 'new' ? '待处理' : item.status} variant="outlined" />
                      {item.dimension_name && <Chip size="small" label={item.dimension_name} variant="outlined" />}
                    </Box>
                    <Typography variant="subtitle1" sx={{ fontWeight: 800 }} noWrap>
                      {item.filename || item.task_id}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      任务编号：{item.task_id}
                    </Typography>
                  </Box>
                  <Button
                    size="small"
                    endIcon={<OpenInNewIcon />}
                    onClick={() => navigate(`/tasks/${item.task_id}/dashboard`)}
                  >
                    打开任务
                  </Button>
                </Box>

                <Divider sx={{ my: 1.5 }} />

                <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '180px 1fr' }, gap: 1.5 }}>
                  <Box>
                    <Typography variant="caption" color="text.secondary">评分差异</Typography>
                    <Typography variant="body2" sx={{ fontWeight: 700 }}>
                      工具 {formatScore(item.ai_score)} → 人工 {formatScore(item.human_score)}
                    </Typography>
                    {item.human_grade && (
                      <Typography variant="body2" color="text.secondary">
                        建议等级：{item.human_grade}
                      </Typography>
                    )}
                    {item.time_range && (
                      <Typography variant="body2" color="text.secondary">
                        时间点：{item.time_range}
                      </Typography>
                    )}
                  </Box>
                  <Box>
                    <Typography variant="body2" sx={{ lineHeight: 1.7 }}>
                      {item.issue_summary}
                    </Typography>
                    {item.correction_suggestion && (
                      <Typography variant="body2" color="text.secondary" sx={{ mt: 0.75, lineHeight: 1.7 }}>
                        建议：{item.correction_suggestion}
                      </Typography>
                    )}
                    {item.evidence_note && (
                      <Typography variant="body2" color="text.secondary" sx={{ mt: 0.75, lineHeight: 1.7 }}>
                        证据：{item.evidence_note}
                      </Typography>
                    )}
                  </Box>
                </Box>

                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
                  提交人：{item.reviewer || '-'} · 提交时间：{item.created_at || '-'}
                </Typography>
              </CardContent>
            </Card>
          ))}
        </Box>
      )}
    </Box>
  );
};

function formatScore(score?: number | null): string {
  return typeof score === 'number' ? score.toFixed(1) : '-';
}

export default FeedbackPage;
