import React, { useContext, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Card,
  Chip,
  CircularProgress,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';

import { ToastContext } from '../App';
import { getTaskList, type TaskListItem, type TaskStatusType } from '../api/client';

const STATUS_COLORS: Record<TaskStatusType, 'default' | 'primary' | 'success' | 'error' | 'warning' | 'info'> = {
  pending: 'default',
  extracting: 'info',
  transcribing: 'info',
  analyzing: 'primary',
  scoring: 'primary',
  completed: 'success',
  failed: 'error',
};

const STATUS_LABELS: Record<TaskStatusType, string> = {
  pending: '等待开始',
  extracting: '提取音频',
  transcribing: '语音转写',
  analyzing: '智能分析',
  scoring: '生成报告',
  completed: '已完成',
  failed: '失败',
};

const gradeColor = (grade: string | null) => {
  if (!grade) return 'text.secondary';
  if (['优', '良'].includes(grade)) return 'success.main';
  if (grade.includes('不') || grade === '差') return 'error.main';
  return 'warning.main';
};

const formatDate = (dateStr: string | null): string => {
  if (!dateStr) return '-';
  const date = new Date(dateStr);
  if (Number.isNaN(date.getTime())) return dateStr;
  return date.toLocaleString('zh-CN');
};

const HistoryPage: React.FC = () => {
  const navigate = useNavigate();
  const { showToast } = useContext(ToastContext);
  const [tasks, setTasks] = useState<TaskListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [keyword, setKeyword] = useState('');
  const [loading, setLoading] = useState(true);

  const fetchTasks = async (p: number, ps: number, kw: string) => {
    setLoading(true);
    try {
      const data = await getTaskList(p, ps, kw);
      setTasks(data.items);
      setTotal(data.total);
    } catch {
      showToast('获取分析记录失败', 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTasks(page, pageSize, keyword);
  }, [page, pageSize]);

  const openTask = (task: TaskListItem) => {
    if (task.status === 'completed') navigate(`/tasks/${task.id}/dashboard`);
    else if (task.status !== 'failed') navigate(`/tasks/${task.id}/analyzing`);
  };

  return (
    <Box sx={{ maxWidth: 1120, mx: 'auto', px: 3, py: 4 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 2, alignItems: 'center', mb: 3 }}>
        <Box>
          <Typography variant="h4">分析记录</Typography>
          <Typography color="text.secondary">按课程视频追踪质量分析结果。</Typography>
        </Box>
        <TextField
          size="small"
          placeholder="搜索文件名"
          value={keyword}
          onChange={(event) => setKeyword(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              setPage(1);
              fetchTasks(1, pageSize, keyword);
            }
          }}
          InputProps={{ startAdornment: <SearchIcon sx={{ color: 'text.secondary', mr: 1 }} /> }}
        />
      </Box>

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}>
          <CircularProgress />
        </Box>
      ) : (
        <Card>
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell sx={{ fontWeight: 700 }}>视频文件</TableCell>
                  <TableCell sx={{ fontWeight: 700 }}>创建时间</TableCell>
                  <TableCell sx={{ fontWeight: 700 }}>状态</TableCell>
                  <TableCell sx={{ fontWeight: 700, textAlign: 'center' }}>等级</TableCell>
                  <TableCell sx={{ fontWeight: 700, textAlign: 'right' }}>分数</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {tasks.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={5} sx={{ textAlign: 'center', py: 6 }}>
                      <Typography color="text.secondary">暂无分析记录</Typography>
                    </TableCell>
                  </TableRow>
                ) : tasks.map((task) => (
                  <TableRow key={task.id} hover onClick={() => openTask(task)} sx={{ cursor: 'pointer' }}>
                    <TableCell>
                      <Typography variant="body2" sx={{ fontWeight: 600, maxWidth: 380, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {task.filename}
                      </Typography>
                    </TableCell>
                    <TableCell>{formatDate(task.created_at)}</TableCell>
                    <TableCell>
                      <Chip label={STATUS_LABELS[task.status] || task.status} color={STATUS_COLORS[task.status]} size="small" variant="outlined" />
                    </TableCell>
                    <TableCell sx={{ textAlign: 'center' }}>
                      <Typography sx={{ fontWeight: 700, color: gradeColor(task.grade) }}>{task.grade || '-'}</Typography>
                    </TableCell>
                    <TableCell sx={{ textAlign: 'right' }}>
                      <Typography sx={{ fontWeight: 700 }}>{task.total_score !== null ? task.total_score.toFixed(1) : '-'}</Typography>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
          <TablePagination
            component="div"
            count={total}
            page={page - 1}
            rowsPerPage={pageSize}
            onPageChange={(_, p) => setPage(p + 1)}
            onRowsPerPageChange={(event) => {
              setPageSize(parseInt(event.target.value, 10));
              setPage(1);
            }}
            rowsPerPageOptions={[5, 10, 20]}
            labelRowsPerPage="每页行数"
          />
        </Card>
      )}
    </Box>
  );
};

export default HistoryPage;
