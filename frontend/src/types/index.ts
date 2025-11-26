// Job types
export type JobStatus = 'queued' | 'processing' | 'completed' | 'failed' | 'cancelled';

export interface Job {
  id: string;
  task_id: string;
  doc_id: string | null;
  filename: string;
  status: JobStatus;
  progress: number;
  current_step: string | null;
  queued_at: string;
  started_at: string | null;
  completed_at: string | null;
  actual_duration_seconds: number | null;
  worker_id: string | null;
  total_pages: number | null;
  total_chunks: number | null;
  total_images: number | null;
  total_tables: number | null;
  tokens_used: number | null;
  ingestion_cost_usd: number | null;
  error_message: string | null;
  retry_count: number;
  max_retries: number;
}

export interface JobsResponse {
  jobs: Job[];
  total: number;
  page: number;
  page_size: number;
}

export interface QueueStats {
  total_jobs: number;
  queued_jobs: number;
  processing_jobs: number;
  completed_jobs: number;
  failed_jobs: number;
  cancelled_jobs: number;
  avg_duration_seconds: number;
  total_cost_usd: number;
}

export interface WorkerInfo {
  worker_id: string;
  current_job_id: string | null;
  current_filename: string | null;
  job_progress: number | null;
  started_at: string | null;
}

// Document types
export type DocumentStatus = 'processing' | 'completed' | 'failed';

export interface Document {
  id: string;
  version: number;
  title: string;
  filename: string;
  status: DocumentStatus;
  document_type: string | null;
  summary: string | null;
  total_pages: number;
  total_chunks: number;
  total_sections: number;
  total_images: number;
  total_tables: number;
  tags: string[];
  categories: string[];
  created_at: string;
  processed_at: string | null;
  processing_duration_seconds: number | null;
  ingestion_cost_usd: number | null;
  tokens_used: number | null;
  gdrive_file_id: string | null;
  gdrive_link: string | null;
  gdrive_folder_id: string | null;
  relevance_score?: number;  // For semantic search ranking

  // YouTube-specific fields
  channel_name?: string;
  duration_seconds?: number;
  source_url?: string;
}

export interface DocumentsResponse {
  documents: Document[];
  total: number;
  page: number;
  page_size: number;
}

export interface ImageMetadata {
  id: string;
  doc_id: string;
  page_number: number;
  s3_url: string;
  caption: string | null;
  image_type: string | null;
  basic_summary: string | null;
}

export interface TableMetadata {
  id: string;
  doc_id: string;
  page_number: number;
  markdown: string;
  description: string | null;
  key_insights: string[] | null;
}

// Upload types
export interface UploadResponse {
  job_id: string;
  task_id: string;
  doc_id: string;
  filename: string;
  status: string;
  message: string;
}

export interface BulkUploadResult {
  filename: string;
  status: string;
  job_id?: string;
  doc_id?: string;
  error?: string;
}

export interface BulkUploadResponse {
  total: number;
  successful: number;
  failed: number;
  results: BulkUploadResult[];
}

// WebSocket types
export interface JobUpdateMessage {
  type: 'job_update';
  job_id: string;
  status: JobStatus;
  progress: number;
  current_step: string;
  filename: string;
  doc_id: string | null;
  error_message: string | null;
}

export interface WebSocketMessage {
  type: 'connected' | 'job_update' | 'error' | 'ping' | 'pong';
  [key: string]: any;
}
