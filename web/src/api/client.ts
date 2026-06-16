import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  timeout: 300000,
});

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
  source_model?: 'text' | 'vision' | 'vision_enhanced';
  scoring_points: ScoringPoint[];
}

export interface ScoreCard {
  dimensions: ScoreDimension[];
  total_score: number;
  total_max: number;
  grade: string;
  red_line_violation: boolean;
  level: string;
  num_rounds: number;
  narrative_summary?: string;
  interaction_chains_summary?: string;
  visual_observation_summary?: string | Record<string, unknown>;
}

export interface EvidenceStatus {
  mode: 'clip' | 'full_lesson' | 'unknown';
  duration_seconds: number;
  is_clip: boolean;
  transcript_available: boolean;
  transcript_segments: number;
  speaker_count: number;
  events_available: boolean;
  event_count: number;
  keyframes_available: boolean;
  keyframe_count: number;
  visual_scored: boolean;
  visual_fallback_dimensions: string[];
  review_required: boolean;
  summary: string;
}

export interface TeachingEvent {
  event_type: string;
  subtype: string;
  start_time: number;
  end_time: number;
  start_time_display: string;
  end_time_display: string;
  description: string;
  confidence: number;
  related_text: string;
}

export interface KeyframeEvidence {
  id: string;
  url: string;
  filename: string;
  timestamp: number;
  timestamp_display: string;
  event_type: string;
  subtype: string;
  description: string;
  confidence: number;
  related_text: string;
}

export interface EvidenceResponse {
  task_id: string;
  status: EvidenceStatus;
  events: TeachingEvent[];
  keyframes: KeyframeEvidence[];
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
  evidence_status?: EvidenceStatus | null;
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

export interface ModelConfig {
  text_model: string;
  vision_provider: string;
  vision_model: string;
  vision_enabled: boolean;
}

export interface CalibrationFeedbackCreate {
  feedback_type: string;
  dimension_name?: string | null;
  ai_score?: number | null;
  human_score?: number | null;
  human_grade?: string | null;
  time_range?: string | null;
  issue_summary: string;
  correction_suggestion?: string | null;
  evidence_note?: string | null;
  reviewer?: string | null;
}

export interface CalibrationFeedback extends CalibrationFeedbackCreate {
  id: string;
  task_id: string;
  status: string;
  created_at: string | null;
  updated_at: string | null;
  filename?: string | null;
  total_score?: number | null;
  grade?: string | null;
}

export interface CalibrationFeedbackListResponse {
  items: CalibrationFeedback[];
  total: number;
  page: number;
  page_size: number;
}

export const uploadVideo = async (
  file: File,
  level: string = 'QC-v4',
  onProgress?: (pct: number) => void,
): Promise<TaskCreated> => {
  const formData = new FormData();
  formData.append('file', file);

  const response = await api.post<TaskCreated>('/tasks', formData, {
    params: { level, auto_start: true },
    onUploadProgress: (event) => {
      if (event.total && onProgress) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    },
  });

  return response.data;
};

export const getTaskStatus = async (id: string): Promise<TaskStatus> => {
  const response = await api.get<TaskStatus>(`/tasks/${id}/status`);
  return response.data;
};

export const retryTaskAnalysis = async (
  id: string,
  level: string = 'QC-v4',
): Promise<TaskCreated> => {
  const response = await api.post<TaskCreated>(`/tasks/${id}/retry`, null, {
    params: { level },
  });
  return response.data;
};

export const getTaskDetail = async (id: string): Promise<TaskDetail> => {
  const response = await api.get<TaskDetail>(`/tasks/${id}`);
  return response.data;
};

export const getTaskEvidence = async (id: string): Promise<EvidenceResponse> => {
  const response = await api.get<EvidenceResponse>(`/tasks/${id}/evidence`);
  return response.data;
};

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

export const getStandards = async (): Promise<StandardsResponse> => {
  const response = await api.get<StandardsResponse>('/standards');
  return response.data;
};

export const getModelConfig = async (): Promise<ModelConfig> => {
  const response = await api.get<ModelConfig>('/config/models');
  return response.data;
};

export const submitCalibrationFeedback = async (
  taskId: string,
  payload: CalibrationFeedbackCreate,
): Promise<CalibrationFeedback> => {
  const response = await api.post<CalibrationFeedback>(`/tasks/${taskId}/feedback`, payload);
  return response.data;
};

export const getTaskFeedback = async (taskId: string): Promise<CalibrationFeedback[]> => {
  const response = await api.get<CalibrationFeedback[]>(`/tasks/${taskId}/feedback`);
  return response.data;
};

export const getCalibrationFeedbackList = async (
  page: number = 1,
  pageSize: number = 20,
): Promise<CalibrationFeedbackListResponse> => {
  const response = await api.get<CalibrationFeedbackListResponse>('/feedback', {
    params: { page, page_size: pageSize },
  });
  return response.data;
};

const CHUNK_SIZE = 1 * 1024 * 1024;
const CHUNK_UPLOAD_TIMEOUT = 120_000;
const MAX_CHUNK_RETRIES = 2;
const PARALLEL_UPLOADS = 5;

export interface ChunkInitResponse {
  upload_id: string;
  chunk_size: number;
}

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

export const uploadChunk = async (
  uploadId: string,
  chunkIndex: number,
  chunk: Blob,
): Promise<void> => {
  const formData = new FormData();
  formData.append('file', chunk, `chunk_${chunkIndex}`);

  let lastError: unknown = null;
  for (let attempt = 1; attempt <= MAX_CHUNK_RETRIES; attempt += 1) {
    try {
      await api.post(`/tasks/upload/${uploadId}/${chunkIndex}`, formData, {
        timeout: CHUNK_UPLOAD_TIMEOUT,
      });
      return;
    } catch (err: unknown) {
      lastError = err;
      if (attempt < MAX_CHUNK_RETRIES) {
        await new Promise((resolve) => setTimeout(resolve, 1000 * Math.pow(2, attempt - 1)));
      }
    }
  }
  throw lastError;
};

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

export const uploadVideoChunked = async (
  file: File,
  level: string = 'QC-v4',
  onProgress?: (pct: number, statusMsg?: string) => void,
): Promise<TaskCreated> => {
  const ext = file.name.split('.').pop()?.toLowerCase() || '';
  const totalChunks = Math.ceil(file.size / CHUNK_SIZE);
  const sizeMB = (file.size / 1024 / 1024).toFixed(1);

  onProgress?.(0, `准备上传 ${sizeMB} MB，共 ${totalChunks} 个分块`);
  const { upload_id } = await initChunkedUpload(file.name, ext, file.size);

  let completed = 0;
  const errors: Array<{ index: number; err: unknown }> = [];

  const uploadOne = async (i: number): Promise<void> => {
    const start = i * CHUNK_SIZE;
    const end = Math.min(start + CHUNK_SIZE, file.size);
    const chunk = file.slice(start, end);

    try {
      await uploadChunk(upload_id, i, chunk);
      completed += 1;
      const pct = Math.round((completed / totalChunks) * 100);
      onProgress?.(pct, `已上传 ${completed}/${totalChunks} 个分块`);
    } catch (err) {
      errors.push({ index: i, err });
    }
  };

  let cursor = 0;
  const worker = async (): Promise<void> => {
    while (cursor < totalChunks && errors.length === 0) {
      const i = cursor;
      cursor += 1;
      await uploadOne(i);
    }
  };

  await Promise.all(
    Array.from({ length: Math.min(PARALLEL_UPLOADS, totalChunks) }, () => worker()),
  );

  if (errors.length > 0) {
    throw new Error(`分块上传失败：${errors.map((e) => e.index).join(', ')}`);
  }

  onProgress?.(100, '文件组装中，正在创建分析任务');
  return completeChunkedUpload(upload_id, level);
};

export const getVideoUrl = (taskId: string): string => `/api/tasks/${taskId}/video`;

export const getReportUrl = (taskId: string): string => `/api/tasks/${taskId}/report/pdf`;

export default api;
