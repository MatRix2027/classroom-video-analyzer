import React, { useEffect, useState, useContext } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Card,
  CardContent,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
  TextField,
  Chip,
  CircularProgress,
  TablePagination,
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import { getTaskList, type TaskListItem, type TaskStatusType } from '../api/client';
import { ToastContext } from '../App';

// 状态标签颜色
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
  transcribing: '语音识别',
  analyzing: '智能分析',
  scoring: '生成报告',
  completed: '已完成',
  failed: '失败',
};

// 等级颜色
const GRADE_COLORS: Record<string, string> = {
  '优': '#2e7d32',
  '良': '#1565c0',
  '创新': '#2e7d32',
  '挑战': '#1565c0',
  '博学': '#ed6c02',
  '待改进': '#ed6c02',
  '不合格': '#c62828',
  '不达标': '#c62828',
  '不达标（红线违规）': '#c62828',
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

  // 加载数据
  const fetchTasks = async (p: number, ps: number, kw: string) => {
    setLoading(true);
    try {
      const data = await getTaskList(p, ps, kw);
      setTasks(data.items);
      setTotal(data.total);
    } catch (err: any) {
      showToast('获取历史记录失败', 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTasks(page, pageSize, keyword);
  }, [page, pageSize]);

  // 搜索
  const handleSearch = () => {
    setPage(1);
    fetchTasks(1, pageSize, keyword);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleSearch();
  };

  // 点击行
  const handleRowClick = (task: TaskListItem) => {
    if (task.status === 'completed') {
      navigate(`/tasks/${task.id}/dashboard`);
    } else if (
      task.status === 'extracting' ||
      task.status === 'transcribing' ||
      task.status === 'analyzing' ||
      task.status === 'scoring'
    ) {
      navigate(`/tasks/${task.id}/analyzing`);
    }
  };

  const formatDate = (dateStr: string | null): string => {
    if (!dateStr) return '—';
    try {
      const d = new Date(dateStr);
      return d.toLocaleString('zh-CN');
    } catch {
      return dateStr;
    }
  };

  return (
    <Box sx={{ maxWidth: 1000, mx: 'auto', py: 3, px: 2 }}>
      <Typography variant="h4" sx={{ mb: 3 }}>
        历史记录
      </Typography>

      {/* 搜索栏 */}
      <Box sx={{ display: 'flex', gap: 2, mb: 3 }}>
        <TextField
          size="small"
          placeholder="搜索文件名..."
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          onKeyDown={handleKeyDown}
          sx={{ flexGrow: 1 }}
          slotProps={{
            input: {
              startAdornment: <SearchIcon sx={{ color: 'text.secondary', mr: 1 }} />,
            },
          }}
        />
      </Box>

      {/* 表格 */}
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
                  <TableCell sx={{ fontWeight: 600 }}>文件名</TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>创建时间</TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>状态</TableCell>
                  <TableCell sx={{ fontWeight: 600, textAlign: 'center' }}>等级</TableCell>
                  <TableCell sx={{ fontWeight: 600, textAlign: 'right' }}>分数</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {tasks.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={5} sx={{ textAlign: 'center', py: 6 }}>
                      <Typography variant="body1" color="text.secondary">
                        暂无分析记录
                      </Typography>
                    </TableCell>
                  </TableRow>
                ) : (
                  tasks.map((task) => (
                    <TableRow
                      key={task.id}
                      hover
                      onClick={() => handleRowClick(task)}
                      sx={{ cursor: 'pointer' }}
                    >
                      <TableCell>
                        <Typography variant="body2" sx={{ fontWeight: 500, maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {task.filename}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2" color="text.secondary">
                          {formatDate(task.created_at)}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Chip
                          label={STATUS_LABELS[task.status] || task.status}
                          color={STATUS_COLORS[task.status]}
                          size="small"
                          variant="outlined"
                        />
                      </TableCell>
                      <TableCell sx={{ textAlign: 'center' }}>
                        {task.grade ? (
                          <Typography
                            variant="body2"
                            sx={{ fontWeight: 600, color: GRADE_COLORS[task.grade] || 'text.primary' }}
                          >
                            {task.grade}
                          </Typography>
                        ) : (
                          <Typography variant="body2" color="text.secondary">—</Typography>
                        )}
                      </TableCell>
                      <TableCell sx={{ textAlign: 'right' }}>
                        {task.total_score !== null ? (
                          <Typography variant="body2" sx={{ fontWeight: 600 }}>
                            {task.total_score.toFixed(1)}
                          </Typography>
                        ) : (
                          <Typography variant="body2" color="text.secondary">—</Typography>
                        )}
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </TableContainer>
          <TablePagination
            component="div"
            count={total}
            page={page - 1}
            onPageChange={(_, p) => setPage(p + 1)}
            rowsPerPage={pageSize}
            onRowsPerPageChange={(e) => {
              setPageSize(parseInt(e.target.value, 10));
              setPage(1);
            }}
            rowsPerPageOptions={[5, 10, 20]}
            labelRowsPerPage="每页行数："
            labelDisplayedRows={({ from, to, count }) => `${from}-${to} / 共 ${count} 条`}
          />
        </Card>
      )}
    </Box>
  );
};

export default HistoryPage;
