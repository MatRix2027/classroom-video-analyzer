import React, { useState, useCallback, useContext, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Typography,
  LinearProgress,
  Alert,
} from '@mui/material';
import CloudUploadIcon from '@mui/icons-material/CloudUpload';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import { uploadVideoChunked } from '../api/client';
import api from '../api/client';
import { ToastContext } from '../App';

// 允许的视频格式
const ALLOWED_TYPES = ['video/mp4', 'video/quicktime', 'video/x-matroska', 'video/webm'];
const ALLOWED_EXTENSIONS = ['mp4', 'mov', 'mkv', 'webm'];
const MAX_SIZE = 2 * 1024 * 1024 * 1024; // 2GB

// 班型选项
const LEVEL_OPTIONS = [
  { value: 'L1_L3', label: '学前班型（L1-L3）' },
  { value: 'L4_L6', label: '小低班型（L4-L6）' },
  { value: 'L7_L9', label: '小高班型（L7-L9）' },
  { value: 'QC-v4', label: '新版课中质检 v4' },
];

const UploadPage: React.FC = () => {
  const navigate = useNavigate();
  const { showToast } = useContext(ToastContext);

  const [file, setFile] = useState<File | null>(null);
  const [level, setLevel] = useState<string>('QC-v4');
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadStatusMsg, setUploadStatusMsg] = useState('');
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string>('');

  // 当前使用的模型配置
  const [modelConfig, setModelConfig] = useState<{
    text_model: string;
    vision_provider: string;
    vision_model: string;
    vision_enabled: boolean;
  } | null>(null);

  useEffect(() => {
    api.get('/config/models').then(r => setModelConfig(r.data)).catch(() => {});
  }, []);

  // 校验文件
  const validateFile = useCallback((f: File): string | null => {
    const ext = f.name.split('.').pop()?.toLowerCase() || '';
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
      return `不支持的视频格式：.${ext}，支持：${ALLOWED_EXTENSIONS.join(', ')}`;
    }
    if (f.size > MAX_SIZE) {
      return '文件过大，最大支持 2GB';
    }
    return null;
  }, []);

  // 拖拽事件处理
  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  }, []);

  const handleDragLeave = useCallback(() => {
    setDragOver(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const droppedFile = e.dataTransfer.files[0];
      if (droppedFile) {
        const err = validateFile(droppedFile);
        if (err) {
          setError(err);
          showToast(err, 'error');
        } else {
          setFile(droppedFile);
          setError('');
        }
      }
    },
    [validateFile, showToast],
  );

  // 点击选择文件
  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const selected = e.target.files?.[0];
      if (selected) {
        const err = validateFile(selected);
        if (err) {
          setError(err);
          showToast(err, 'error');
        } else {
          setFile(selected);
          setError('');
        }
      }
    },
    [validateFile, showToast],
  );

  // 格式化文件大小
  const formatSize = (bytes: number): string => {
    if (bytes >= 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
    if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    return `${(bytes / 1024).toFixed(0)} KB`;
  };

  // 开始分析
  const handleStartAnalysis = useCallback(async () => {
    if (!file) return;

    setUploading(true);
    setUploadProgress(0);
    setUploadStatusMsg('');
    setError('');

    try {
      const result = await uploadVideoChunked(file, level, (pct, msg) => {
        setUploadProgress(pct);
        if (msg) setUploadStatusMsg(msg);
      });
      showToast('上传成功，开始分析...', 'success');
      navigate(`/tasks/${result.id}/analyzing`);
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.message || '上传失败，请重试';
      setError(msg);
      showToast(msg, 'error');
    } finally {
      setUploading(false);
    }
  }, [file, level, navigate, showToast]);

  return (
    <Box
      sx={{
        maxWidth: 720,
        mx: 'auto',
        py: 4,
        px: 2,
      }}
    >
      <Typography variant="h4" sx={{ mb: 1, textAlign: 'center' }}>
        课堂视频分析
      </Typography>
      <Typography variant="body1" color="text.secondary" sx={{ mb: 4, textAlign: 'center' }}>
        上传课堂视频，AI 自动分析教学质量，生成评分报告
      </Typography>

      {/* 拖拽上传区域 */}
      <Card
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        sx={{
          border: '2px dashed',
          borderColor: dragOver ? 'primary.main' : 'divider',
          bgcolor: dragOver ? 'action.hover' : 'background.paper',
          cursor: 'pointer',
          transition: 'all 0.2s',
          mb: 3,
        }}
        onClick={() => document.getElementById('file-input')?.click()}
      >
        <CardContent
          sx={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            py: 6,
          }}
        >
          <CloudUploadIcon sx={{ fontSize: 64, color: 'primary.main', mb: 2 }} />
          <Typography variant="h6" color="text.secondary">
            拖拽视频文件到此处，或点击选择
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
            支持 MP4 / MOV / MKV / WebM，最大 2GB
          </Typography>
        </CardContent>
      </Card>

      <input
        id="file-input"
        type="file"
        accept=".mp4,.mov,.mkv,.webm"
        style={{ display: 'none' }}
        onChange={handleFileSelect}
      />

      {/* 文件信息 */}
      {file && (
        <Card sx={{ mb: 3 }}>
          <CardContent>
            <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>
              已选择视频
            </Typography>
            <Box sx={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
              <Box>
                <Typography variant="caption" color="text.secondary">
                  文件名
                </Typography>
                <Typography variant="body2">{file.name}</Typography>
              </Box>
              <Box>
                <Typography variant="caption" color="text.secondary">
                  文件大小
                </Typography>
                <Typography variant="body2">{formatSize(file.size)}</Typography>
              </Box>
              <Box>
                <Typography variant="caption" color="text.secondary">
                  文件类型
                </Typography>
                <Typography variant="body2">{file.type || '未知'}</Typography>
              </Box>
            </Box>
          </CardContent>
        </Card>
      )}

      {/* 错误提示 */}
      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      {/* 班型选择 + 开始分析 */}
      <Box sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
        <FormControl sx={{ minWidth: 240 }}>
          <InputLabel>班型等级</InputLabel>
          <Select value={level} label="班型等级" onChange={(e) => setLevel(e.target.value)}>
            {LEVEL_OPTIONS.map((opt) => (
              <MenuItem key={opt.value} value={opt.value}>
                {opt.label}
              </MenuItem>
            ))}
          </Select>
        </FormControl>

        <Button
          variant="contained"
          size="large"
          startIcon={<PlayArrowIcon />}
          disabled={!file || uploading}
          onClick={handleStartAnalysis}
          sx={{ px: 4, py: 1.5 }}
        >
          {uploading ? '上传中...' : '开始分析'}
        </Button>
      </Box>

      {/* 上传进度条 */}
      {uploading && (
        <Box sx={{ mt: 2 }}>
          <LinearProgress variant="determinate" value={uploadProgress} />
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            {uploadStatusMsg || `上传进度：${uploadProgress}%`}
          </Typography>
        </Box>
      )}

      {/* 当前模型配置 */}
      {modelConfig && (
        <Box sx={{ mt: 3, display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center' }}>
          <Typography variant="caption" color="text.secondary" sx={{ mr: 0.5 }}>
            当前模型：
          </Typography>
          <Chip
            label={`文本：${modelConfig.text_model}`}
            size="small"
            variant="outlined"
            color="default"
          />
          {modelConfig.vision_enabled ? (
            <Chip
              label={`视觉：${modelConfig.vision_model}`}
              size="small"
              color="primary"
              variant="outlined"
            />
          ) : (
            <Chip label="视觉：未启用" size="small" color="default" variant="outlined" />
          )}
        </Box>
      )}
    </Box>
  );
};

export default UploadPage;
