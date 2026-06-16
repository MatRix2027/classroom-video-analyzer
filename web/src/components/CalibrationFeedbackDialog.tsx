import React, { useEffect, useState } from 'react';
import {
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  TextField,
  Typography,
} from '@mui/material';

import type { CalibrationFeedbackCreate, ScoreDimension, TaskDetail } from '../api/client';

interface CalibrationFeedbackDialogProps {
  open: boolean;
  task: TaskDetail | null;
  dimension?: ScoreDimension | null;
  onClose: () => void;
  onSubmit: (payload: CalibrationFeedbackCreate) => Promise<void>;
}

const FEEDBACK_TYPES = [
  { value: 'overall_score', label: '总分/整体结论不一致' },
  { value: 'dimension_score', label: '单项维度评分不一致' },
  { value: 'visual_evidence', label: '关键帧/视觉证据不准确' },
  { value: 'text_evidence', label: '转写/文本证据影响判断' },
  { value: 'report_wording', label: '报告表达需要修正' },
];

const GRADES = ['优', '良', '待改进', '不合格'];

const CalibrationFeedbackDialog: React.FC<CalibrationFeedbackDialogProps> = ({
  open,
  task,
  dimension,
  onClose,
  onSubmit,
}) => {
  const [feedbackType, setFeedbackType] = useState('overall_score');
  const [humanScore, setHumanScore] = useState('');
  const [humanGrade, setHumanGrade] = useState('');
  const [timeRange, setTimeRange] = useState('');
  const [issueSummary, setIssueSummary] = useState('');
  const [correctionSuggestion, setCorrectionSuggestion] = useState('');
  const [evidenceNote, setEvidenceNote] = useState('');
  const [reviewer, setReviewer] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    setFeedbackType(dimension ? 'dimension_score' : 'overall_score');
    setHumanScore('');
    setHumanGrade('');
    setTimeRange('');
    setIssueSummary('');
    setCorrectionSuggestion('');
    setEvidenceNote('');
    setReviewer('');
  }, [open, dimension]);

  const aiScore = dimension?.score ?? task?.total_score ?? null;
  const maxScore = dimension?.max_score ?? task?.scoring_data?.total_max ?? 100;

  const handleSubmit = async () => {
    if (!issueSummary.trim()) return;
    setSubmitting(true);
    try {
      await onSubmit({
        feedback_type: feedbackType,
        dimension_name: dimension?.name || null,
        ai_score: aiScore,
        human_score: humanScore ? Number(humanScore) : null,
        human_grade: humanGrade || null,
        time_range: timeRange.trim() || null,
        issue_summary: issueSummary.trim(),
        correction_suggestion: correctionSuggestion.trim() || null,
        evidence_note: evidenceNote.trim() || null,
        reviewer: reviewer.trim() || null,
      });
      onClose();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>人工校对</DialogTitle>
      <DialogContent>
        <Box sx={{ display: 'grid', gap: 2, pt: 1 }}>
          <Box sx={{ p: 1.5, border: '1px solid #e5e7eb', borderRadius: 1, bgcolor: '#f8fafc' }}>
            <Typography variant="body2" color="text.secondary">
              {task?.filename || '当前任务'}
            </Typography>
            <Typography variant="subtitle2" sx={{ fontWeight: 800 }}>
              {dimension ? dimension.name : '整体报告'}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              工具评分：{aiScore !== null ? aiScore.toFixed(1) : '-'} / {maxScore.toFixed(0)}
            </Typography>
          </Box>

          <FormControl fullWidth>
            <InputLabel>校对类型</InputLabel>
            <Select
              value={feedbackType}
              label="校对类型"
              onChange={(event) => setFeedbackType(event.target.value)}
            >
              {FEEDBACK_TYPES.map((item) => (
                <MenuItem key={item.value} value={item.value}>{item.label}</MenuItem>
              ))}
            </Select>
          </FormControl>

          <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr' }, gap: 1.5 }}>
            <TextField
              label="人工建议评分"
              type="number"
              value={humanScore}
              onChange={(event) => setHumanScore(event.target.value)}
              inputProps={{ min: 0, max: maxScore, step: 0.5 }}
            />
            <FormControl fullWidth>
              <InputLabel>人工建议等级</InputLabel>
              <Select
                value={humanGrade}
                label="人工建议等级"
                onChange={(event) => setHumanGrade(event.target.value)}
              >
                {GRADES.map((grade) => (
                  <MenuItem key={grade} value={grade}>{grade}</MenuItem>
                ))}
              </Select>
            </FormControl>
          </Box>

          <TextField
            label="相关时间点"
            placeholder="例如：08:30-10:20"
            value={timeRange}
            onChange={(event) => setTimeRange(event.target.value)}
          />
          <TextField
            label="差异说明"
            required
            multiline
            minRows={3}
            value={issueSummary}
            onChange={(event) => setIssueSummary(event.target.value)}
            placeholder="说明人工质检与工具分析不一致的地方"
          />
          <TextField
            label="建议调整"
            multiline
            minRows={2}
            value={correctionSuggestion}
            onChange={(event) => setCorrectionSuggestion(event.target.value)}
            placeholder="例如：该维度应降低到 6 分，因为..."
          />
          <TextField
            label="证据说明"
            multiline
            minRows={2}
            value={evidenceNote}
            onChange={(event) => setEvidenceNote(event.target.value)}
            placeholder="补充人工判断依据、关键帧或课堂片段"
          />
          <TextField
            label="校对人"
            value={reviewer}
            onChange={(event) => setReviewer(event.target.value)}
          />
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>取消</Button>
        <Button variant="contained" onClick={handleSubmit} disabled={!issueSummary.trim() || submitting}>
          {submitting ? '提交中' : '提交校对'}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default CalibrationFeedbackDialog;
