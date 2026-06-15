import React, { useCallback, useContext, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  FormControl,
  LinearProgress,
  MenuItem,
  Select,
  Typography,
} from '@mui/material';
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome';
import CloudUploadIcon from '@mui/icons-material/CloudUpload';
import FactCheckIcon from '@mui/icons-material/FactCheck';
import InsightsIcon from '@mui/icons-material/Insights';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import VisibilityIcon from '@mui/icons-material/Visibility';
import WorkspacePremiumIcon from '@mui/icons-material/WorkspacePremium';

import { ToastContext } from '../App';
import { getModelConfig, uploadVideoChunked, type ModelConfig } from '../api/client';

const ALLOWED_EXTENSIONS = ['mp4', 'mov', 'mkv', 'webm', 'flv', 'avi'];
const MAX_SIZE = 2 * 1024 * 1024 * 1024;

const LEVEL_OPTIONS = [
  { value: 'QC-v4', label: '统一质检标准 QC-v4' },
  { value: 'L1_L3', label: 'L1-L3 学前班型' },
  { value: 'L4_L6', label: 'L4-L6 小低班型' },
  { value: 'L7_L9', label: 'L7-L9 小高班型' },
  { value: 'QA-v3', label: '通用巡检 QA-v3' },
];

const SCENARIOS = [
  {
    id: 'quality',
    title: '课堂质检',
    icon: <FactCheckIcon />,
    tone: '#14532d',
    summary: '面向达标判断、红线排查、维度评分。',
  },
  {
    id: 'growth',
    title: '成长反馈',
    icon: <InsightsIcon />,
    tone: '#1d4ed8',
    summary: '面向教师复盘、优势识别、训练建议。',
  },
  {
    id: 'highlight',
    title: '优秀课例',
    icon: <WorkspacePremiumIcon />,
    tone: '#b45309',
    summary: '面向亮点提取、案例沉淀、培训素材。',
  },
];

function formatSize(bytes: number): string {
  if (bytes >= 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / 1024).toFixed(0)} KB`;
}

const UploadPage: React.FC = () => {
  const navigate = useNavigate();
  const { showToast } = useContext(ToastContext);

  const [file, setFile] = useState<File | null>(null);
  const [level, setLevel] = useState('QC-v4');
  const [scenario, setScenario] = useState('quality');
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadStatus, setUploadStatus] = useState('');
  const [error, setError] = useState('');
  const [modelConfig, setModelConfig] = useState<ModelConfig | null>(null);

  useEffect(() => {
    getModelConfig().then(setModelConfig).catch(() => setModelConfig(null));
  }, []);

  const validateFile = useCallback((candidate: File): string | null => {
    const ext = candidate.name.split('.').pop()?.toLowerCase() || '';
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
      return `暂不支持 .${ext} 文件，请上传 ${ALLOWED_EXTENSIONS.join(', ')} 格式。`;
    }
    if (candidate.size > MAX_SIZE) {
      return '文件超过 2GB，请先压缩或裁剪后再上传。';
    }
    return null;
  }, []);

  const acceptFile = useCallback((candidate: File) => {
    const msg = validateFile(candidate);
    if (msg) {
      setError(msg);
      showToast(msg, 'error');
      return;
    }
    setFile(candidate);
    setError('');
  }, [showToast, validateFile]);

  const handleFileSelect = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    const selected = event.target.files?.[0];
    if (selected) acceptFile(selected);
  }, [acceptFile]);

  const handleDrop = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    setDragOver(false);
    const dropped = event.dataTransfer.files[0];
    if (dropped) acceptFile(dropped);
  }, [acceptFile]);

  const startAnalysis = useCallback(async () => {
    if (!file) return;
    setUploading(true);
    setUploadProgress(0);
    setUploadStatus('');
    setError('');

    try {
      const result = await uploadVideoChunked(file, level, (pct, msg) => {
        setUploadProgress(pct);
        if (msg) setUploadStatus(msg);
      });
      showToast('任务已创建，正在进入分析流程。', 'success');
      navigate(`/tasks/${result.id}/analyzing`);
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.message || '上传失败，请检查网络后重试。';
      setError(msg);
      showToast(msg, 'error');
    } finally {
      setUploading(false);
    }
  }, [file, level, navigate, showToast]);

  return (
    <Box sx={{ maxWidth: 1180, mx: 'auto', px: 3, py: 4 }}>
      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1.1fr 0.9fr' }, gap: 3, alignItems: 'start' }}>
        <Box>
          <Typography variant="h4" sx={{ mb: 1 }}>
            新建课堂质量分析
          </Typography>
          <Typography color="text.secondary" sx={{ mb: 3 }}>
            上传课堂视频后自动完成转写、教学事件识别、关键帧提取、视觉证据归档和授课质量初评。
          </Typography>

          <Card
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            onClick={() => document.getElementById('video-file-input')?.click()}
            sx={{
              cursor: 'pointer',
              border: '1.5px dashed',
              borderColor: dragOver ? 'primary.main' : '#cbd5e1',
              bgcolor: dragOver ? '#ecfdf5' : '#ffffff',
              mb: 2,
            }}
          >
            <CardContent sx={{ minHeight: 250, display: 'grid', placeItems: 'center', textAlign: 'center', px: 4 }}>
              <Box>
                <CloudUploadIcon sx={{ fontSize: 58, color: 'primary.main', mb: 1.5 }} />
                <Typography variant="h6" sx={{ mb: 1 }}>
                  {file ? file.name : '选择课堂视频'}
                </Typography>
                <Typography color="text.secondary">
                  {file ? `${formatSize(file.size)} · ${file.type || 'video'}` : 'MP4 / MOV / MKV / WebM / FLV / AVI，最大 2GB'}
                </Typography>
              </Box>
            </CardContent>
          </Card>

          <input
            id="video-file-input"
            type="file"
            accept=".mp4,.mov,.mkv,.webm,.flv,.avi"
            style={{ display: 'none' }}
            onChange={handleFileSelect}
          />

          {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

          <Card>
            <CardContent sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: '1fr auto' }, gap: 2, alignItems: 'center' }}>
              <Box>
                <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 0.75 }}>
                  评价标准
                </Typography>
                <FormControl fullWidth size="small">
                  <Select value={level} onChange={(e) => setLevel(e.target.value)}>
                    {LEVEL_OPTIONS.map((option) => (
                      <MenuItem key={option.value} value={option.value}>
                        {option.label}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </Box>
              <Button
                variant="contained"
                size="large"
                startIcon={<PlayArrowIcon />}
                disabled={!file || uploading}
                onClick={startAnalysis}
                sx={{ minWidth: 150, height: 42 }}
              >
                开始分析
              </Button>
            </CardContent>
          </Card>

          {uploading && (
            <Box sx={{ mt: 2 }}>
              <LinearProgress variant="determinate" value={uploadProgress} sx={{ height: 8, borderRadius: 4 }} />
              <Typography variant="body2" color="text.secondary" sx={{ mt: 0.75 }}>
                {uploadStatus || `上传进度 ${uploadProgress}%`}
              </Typography>
            </Box>
          )}
        </Box>

        <Box sx={{ display: 'grid', gap: 2 }}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                <VisibilityIcon color={modelConfig?.vision_enabled ? 'primary' : 'warning'} />
                <Typography variant="h6">运行能力</Typography>
              </Box>
              <Box sx={{ display: 'grid', gap: 1 }}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 1 }}>
                  <Typography variant="body2" color="text.secondary">Web 访问</Typography>
                  <Chip size="small" color="success" label="开箱可用" />
                </Box>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 1 }}>
                  <Typography variant="body2" color="text.secondary">关键帧提取</Typography>
                  <Chip size="small" color="success" label="默认启用" />
                </Box>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 1 }}>
                  <Typography variant="body2" color="text.secondary">视觉评分</Typography>
                  <Chip
                    size="small"
                    color={modelConfig?.vision_enabled ? 'success' : 'warning'}
                    label={modelConfig?.vision_enabled ? modelConfig.vision_model : '未配置时需复核'}
                  />
                </Box>
              </Box>
              {!modelConfig?.vision_enabled && (
                <Alert severity="warning" sx={{ mt: 2 }}>
                  当前环境可访问和上传，也会提取关键帧；视觉维度若未配置模型，会以“待复核”方式呈现，避免误判为终评。
                </Alert>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
                <AutoAwesomeIcon color="primary" />
                <Typography variant="h6">分析目标</Typography>
              </Box>
              <Box sx={{ display: 'grid', gap: 1.5 }}>
                {SCENARIOS.map((item) => {
                  const active = scenario === item.id;
                  return (
                    <Box
                      key={item.id}
                      onClick={() => setScenario(item.id)}
                      sx={{
                        display: 'grid',
                        gridTemplateColumns: '36px 1fr auto',
                        gap: 1.5,
                        alignItems: 'center',
                        p: 1.5,
                        borderRadius: 1.5,
                        border: '1px solid',
                        borderColor: active ? item.tone : '#e5e7eb',
                        bgcolor: active ? '#f8faf7' : '#ffffff',
                        cursor: 'pointer',
                      }}
                    >
                      <Box sx={{ color: item.tone, display: 'flex' }}>{item.icon}</Box>
                      <Box>
                        <Typography variant="subtitle2">{item.title}</Typography>
                        <Typography variant="body2" color="text.secondary">{item.summary}</Typography>
                      </Box>
                      {active && <Chip size="small" color="primary" label="当前" />}
                    </Box>
                  );
                })}
              </Box>
            </CardContent>
          </Card>

          <Card>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 1.5 }}>输出结构</Typography>
              {['总分与等级', '红线风险', '维度评分', '证据片段', '改进建议'].map((item) => (
                <Chip key={item} label={item} sx={{ mr: 1, mb: 1 }} variant="outlined" />
              ))}
            </CardContent>
          </Card>
        </Box>
      </Box>
    </Box>
  );
};

export default UploadPage;
