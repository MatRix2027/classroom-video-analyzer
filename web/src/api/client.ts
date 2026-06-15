import axios from 'axios';

// ── API 基础实例 ──
const api = axios.create({
  baseURL: '/api',
  timeout: 300000, // 5 分钟（大文件上传）
});

// ── TypeScript 类型定义 ──

export type TaskStatusType =
  | 'pending'
  | 'extracting'
  | 'transcribing'
  | 'analyzing'
  | 'scoring'
  | 'completed'
  | 'failed';

export interface ScoringPoint {
  type: string;
  reason: string;
  quote: string;
  at: number | null;
  duration: number | null;
}

export interface ScoreDimension {
  name: string;
  score: number;
  max_score: number;
  weight: number;
  evidence: string;
  details: string;
  grade: string;
  timestamp: number | null;
  score_std: number | null;
  round_scores: number[];
  scoring_points: ScoringPoint[];
  /** 评分来源："text"（文本模型）或 "vision"（视觉模型） */
  source_model?: 'text' | 'vision';
}

export interface ScoreCard {
  dimensions: ScoreDimension[];
  total_score: number;
  total_max: number;
  grade: string;
  red_line_violation: boolean;
  level: string;
  num_rounds: number;
}

export interface TaskCreated {
  id: string;
}

export interface TaskStatus {
  id: string;
  status: TaskStatusType;
  progress: number;
  current_stage: string;
}

export interface TaskDetail {
  id: string;
  filename: string;
  video_path: string;
  status: TaskStatusType;
  progress: number;
  current_stage: string;
  total_score: number | null;
  grade: string | null;
  scoring_data: ScoreCard | null;
  created_at: string | null;
  completed_at: string | null;
}

export interface TaskListItem {
  id: string;
  filename: string;
  status: TaskStatusType;
  total_score: number | null;
  grade: string | null;
  created_at: string | null;
}

export interface TaskListResponse {
  items: TaskListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface StandardDimension {
  name: string;
  category: string;
  weight: number;
  max_score: number;
  criteria_excellent: string;
  criteria_good: string;
  criteria_average: string;
  criteria_poor: string;
}

export interface StandardLevel {
  description: string;
  student_focus: string;
  dimensions: StandardDimension[];
  quality_checklist: string[];
}

export interface StandardsResponse {
  levels: Record<string, StandardLevel>;
  red_lines: Array<{
    id: string;
    name: string;
    description: string;
    severity: string;
  }>;
  grade_system: Array<{
    name: string;
    min: number;
    max: number;
    color: string;
  }>;
}

// ── API 函数 ──

/** 上传视频并创建分析任务（旧版单次上传，仅作备用，大文件请使用 uploadVideoChunked） */
export const uploadVideo = async (
  file: File,
  level: string = 'L4_L6',
  onProgress?: (pct: number) => void,
): Promise<TaskCreated> => {
  const formData = new FormData();
  formData.append('file', file);

  const response = await api.post<TaskCreated>('/tasks', formData, {
    params: { level, auto_start: true },
    // 不要手动设置 Content-Type，让浏览器自动添加含 boundary 的 multipart/form-data
    onUploadProgress: (event) => {
      if (event.total && onProgress) {
        const pct = Math.round((event.loaded / event.total) * 100);
        onProgress(pct);
      }
    },
  });

  return response.data;
};

/** 获取任务状态（轮询用） */
export const getTaskStatus = async (id: string): Promise<TaskStatus> => {
  const response = await api.get<TaskStatus>(`/tasks/${id}/status`);
  return response.data;
};

/** 获取任务详情 */
export const getTaskDetail = async (id: string): Promise<TaskDetail> => {
  const response = await api.get<TaskDetail>(`/tasks/${id}`);
  return response.data;
};

/** 获取任务列表 */
export const getTaskList = async (
  page: number = 1,
  pageSize: number = 10,
  keyword: string = '',
): Promise<TaskListResponse> => {
  const response = await api.get<TaskListResponse>('/tasks', {
    params: { page, page_size: pageSize, keyword },
  });
  return response.data;
};

/** 获取标准 */
export const getStandards = async (): Promise<StandardsResponse> => {
  const response = await api.get<StandardsResponse>('/standards');
  return response.data;
};

// ── 分块上传（解决 Cloudflare 100s 超时） ──

const CHUNK_SIZE = 1 * 1024 * 1024; // 1MB 每块（慢速网络友好）
const CHUNK_UPLOAD_TIMEOUT = 120_000; // 单块上传超时 120s
const MAX_CHUNK_RETRIES = 2; // 单块最大重试次数
const PARALLEL_UPLOADS = 5; // 并发上传数（5 路并行，理论上 5 倍提速）

export interface ChunkInitResponse {
  upload_id: string;
  chunk_size: number;
}

/** 初始化分块上传会话 */
export const initChunkedUpload = async (
  filename: string,
  extension: string,
  totalSize: number,
): Promise<ChunkInitResponse> => {
  const response = await api.post<ChunkInitResponse>('/tasks/upload/init', {
    filename,
    extension,
    total_size: totalSize,
  });
  return response.data;
};

/** 上传单个分块（含重试） */
export const uploadChunk = async (
  uploadId: string,
  chunkIndex: number,
  chunk: Blob,
): Promise<void> => {
  const formData = new FormData();
  formData.append('file', chunk, `chunk_${chunkIndex}`);

  let lastError: unknown = null;
  for (let attempt = 1; attempt <= MAX_CHUNK_RETRIES; attempt++) {
    try {
      await api.post(`/tasks/upload/${uploadId}/${chunkIndex}`, formData, {
        // 不要手动设置 Content-Type，让浏览器自动添加含 boundary 的 multipart/form-data
        timeout: CHUNK_UPLOAD_TIMEOUT,
      });
      return; // 上传成功
    } catch (err: unknown) {
      lastError = err;
      console.warn(
        `[分块上传] 分块 ${chunkIndex} 第 ${attempt}/${MAX_CHUNK_RETRIES} 次上传失败:`,
        err,
      );
      if (attempt < MAX_CHUNK_RETRIES) {
        // 指数退避：1s, 2s, 4s...
        await new Promise((r) => setTimeout(r, 1000 * Math.pow(2, attempt - 1)));
      }
    }
  }
  throw lastError;
};

/** 完成分块上传，组装并创建任务 */
export const completeChunkedUpload = async (
  uploadId: string,
  level: string,
): Promise<TaskCreated> => {
  const response = await api.post<TaskCreated>(
    `/tasks/upload/${uploadId}/complete`,
    { level },
  );
  return response.data;
};

/**
 * 分块上传完整流程：init → parallel chunks → complete
 * 返回 TaskCreated，与 uploadVideo 接口兼容
 *
 * @param onProgress 进度回调 (0-100) + 状态文字
 */
export const uploadVideoChunked = async (
  file: File,
  level: string = 'QC-v4',
  onProgress?: (pct: number, statusMsg?: string) => void,
): Promise<TaskCreated> => {
  const ext = file.name.split('.').pop()?.toLowerCase() || '';
  const totalChunks = Math.ceil(file.size / CHUNK_SIZE);

  // Step 1: 初始化
  const sizeMB = (file.size / 1024 / 1024).toFixed(1);
  console.log(`[分块上传] 初始化，${sizeMB} MB，${totalChunks} 块，${PARALLEL_UPLOADS} 路并发`);
  onProgress?.(0, `准备上传 ${sizeMB} MB（${totalChunks} 块）...`);
  const { upload_id } = await initChunkedUpload(file.name, ext, file.size);

  // Step 2: 并行上传（信号量控制并发数）
  let completed = 0;
  let failed = 0;
  const errors: Array<{ index: number; err: unknown }> = [];

  const uploadOne = async (i: number): Promise<void> => {
    const start = i * CHUNK_SIZE;
    const end = Math.min(start + CHUNK_SIZE, file.size);
    const chunk = file.slice(start, end);

    try {
      await uploadChunk(upload_id, i, chunk);
      completed++;
      const pct = Math.round((completed / totalChunks) * 100);
      const speedHint =
        completed > 1 && completed < totalChunks
          ? `（${PARALLEL_UPLOADS} 路并发中）`
          : '';
      onProgress?.(pct, `${completed}/${totalChunks} 块完成${speedHint}`);
    } catch (err) {
      failed++;
      errors.push({ index: i, err });
      // 单个块失败不阻断其他块
    }
  };

  // 并发池：用一个游标分配任务到 N 个 worker
  let cursor = 0;
  const worker = async (): Promise<void> => {
    while (cursor < totalChunks && failed === 0) {
      const i = cursor++;
      await uploadOne(i);
    }
  };

  // 启动 PARALLEL_UPLOADS 个 worker
  const workers = Array.from({ length: Math.min(PARALLEL_UPLOADS, totalChunks) }, () =>
    worker(),
  );
  await Promise.all(workers);

  // 有失败的块？
  if (failed > 0) {
    const firstErr = errors[0];
    console.error(`[分块上传] ${failed}/${totalChunks} 块失败，首个: 块#${firstErr.index}`, firstErr.err);
    throw new Error(
      `${failed}/${totalChunks} 个分块上传失败（块#${errors.map((e) => e.index).join(',')}），请检查网络后重试`,
    );
  }

  // Step 3: 组装完成
  console.log('[分块上传] 全部块上传完成，正在组装...');
  onProgress?.(100, '正在组装文件...');
  return await completeChunkedUpload(upload_id, level);
};

/** 获取视频 URL */
export const getVideoUrl = (taskId: string): string => {
  return `/api/tasks/${taskId}/video`;
};

/** 获取报告 URL */
export const getReportUrl = (taskId: string): string => {
  return `/api/tasks/${taskId}/report/pdf`;
};

export default api;
