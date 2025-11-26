import axios from 'axios';
import type {
  Job,
  JobsResponse,
  QueueStats,
  WorkerInfo,
  Document,
  DocumentsResponse,
  ImageMetadata,
  TableMetadata,
  UploadResponse,
  BulkUploadResponse,
} from '@/types';

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Jobs API
export const jobsApi = {
  // List all jobs
  list: async (params?: {
    status?: string;
    page?: number;
    page_size?: number;
  }): Promise<JobsResponse> => {
    const { data } = await api.get('/jobs/', { params });
    return data;
  },

  // Get job details
  get: async (jobId: string): Promise<Job> => {
    const { data } = await api.get(`/jobs/${jobId}`);
    return data;
  },

  // Cancel job
  cancel: async (jobId: string): Promise<{ job_id: string; status: string; message: string }> => {
    const { data } = await api.post(`/jobs/${jobId}/cancel`);
    return data;
  },

  // Retry failed job
  retry: async (jobId: string): Promise<{
    job_id: string;
    task_id: string;
    status: string;
    retry_count: number;
    message: string;
  }> => {
    const { data } = await api.post(`/jobs/${jobId}/retry`);
    return data;
  },

  // Resume failed job from checkpoint
  resume: async (jobId: string): Promise<{
    job_id: string;
    task_id: string;
    status: string;
    message: string;
    checkpoint_summary: string;
  }> => {
    const { data } = await api.post(`/jobs/${jobId}/resume`);
    return data;
  },

  // Get queue statistics
  getQueueStats: async (): Promise<QueueStats> => {
    const { data } = await api.get('/jobs/stats/queue');
    return data;
  },

  // Get active workers
  getActiveWorkers: async (): Promise<WorkerInfo[]> => {
    const { data } = await api.get('/jobs/stats/workers');
    return data;
  },
};

// Documents API
export const documentsApi = {
  // List all documents
  list: async (params?: {
    status?: string;
    document_type?: string;
    search?: string;
    semantic?: boolean;
    page?: number;
    page_size?: number;
  }): Promise<DocumentsResponse> => {
    const { data } = await api.get('/documents/', { params });
    return data;
  },

  // Get document details
  get: async (docId: string): Promise<Document> => {
    const { data } = await api.get(`/documents/${docId}`);
    return data;
  },

  // Get document images
  getImages: async (docId: string): Promise<ImageMetadata[]> => {
    const { data } = await api.get(`/documents/${docId}/images`);
    return data;
  },

  // Get document tables
  getTables: async (docId: string): Promise<TableMetadata[]> => {
    const { data } = await api.get(`/documents/${docId}/tables`);
    return data;
  },

  // Delete document
  delete: async (docId: string): Promise<{ doc_id: string; status: string; message: string }> => {
    const { data } = await api.delete(`/documents/${docId}`);
    return data;
  },
};

// Upload API
export const uploadApi = {
  // Upload single file
  single: async (
    file: File,
    metadata?: {
      document_type?: string;
      tags?: string;
      categories?: string;
      priority?: number;
      reprocess?: boolean;
    }
  ): Promise<UploadResponse> => {
    const formData = new FormData();
    formData.append('file', file);

    if (metadata?.document_type) {
      formData.append('document_type', metadata.document_type);
    }
    if (metadata?.tags) {
      formData.append('tags', metadata.tags);
    }
    if (metadata?.categories) {
      formData.append('categories', metadata.categories);
    }
    if (metadata?.priority !== undefined) {
      formData.append('priority', metadata.priority.toString());
    }
    if (metadata?.reprocess !== undefined) {
      formData.append('reprocess', metadata.reprocess.toString());
    }

    const { data } = await api.post('/upload/single', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return data;
  },

  // Upload multiple files
  bulk: async (
    files: File[],
    metadata?: {
      document_type?: string;
      tags?: string;
      categories?: string;
      priority?: number;
      reprocess?: boolean;
    }
  ): Promise<BulkUploadResponse> => {
    const formData = new FormData();

    files.forEach((file) => {
      formData.append('files', file);
    });

    if (metadata?.document_type) {
      formData.append('document_type', metadata.document_type);
    }
    if (metadata?.tags) {
      formData.append('tags', metadata.tags);
    }
    if (metadata?.categories) {
      formData.append('categories', metadata.categories);
    }
    if (metadata?.priority !== undefined) {
      formData.append('priority', metadata.priority.toString());
    }
    if (metadata?.reprocess !== undefined) {
      formData.append('reprocess', metadata.reprocess.toString());
    }

    const { data } = await api.post('/upload/bulk', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return data;
  },
};

export default api;

// Analytics API
export const analyticsApi = {
  // Get query analytics summary
  getSummary: async () => {
    const { data } = await api.get('/analytics/summary');
    return data;
  },

  // Get daily cost breakdown
  getDaily: async (days: number = 7) => {
    const { data } = await api.get('/analytics/daily', { params: { days } });
    return data;
  },

  // Get cost by type
  getCostByType: async () => {
    const { data } = await api.get('/analytics/cost-by-type');
    return data;
  },
};

// YouTube API
export const youtubeApi = {
  // Upload YouTube video
  upload: async (
    url: string,
    metadata?: {
      tags?: string[];
      categories?: string[];
    }
  ): Promise<{
    job_id: string;
    video_id: string;
    youtube_id: string;
    url: string;
    message: string;
  }> => {
    const { data } = await api.post('/youtube/upload', {
      url,
      tags: metadata?.tags || [],
      categories: metadata?.categories || [],
    });
    return data;
  },

  // List YouTube videos
  list: async (params?: {
    status?: string;
    limit?: number;
    offset?: number;
  }) => {
    const { data } = await api.get('/youtube/videos', { params });
    return data;
  },

  // Get video details
  get: async (videoId: string) => {
    const { data} = await api.get(`/youtube/videos/${videoId}`);
    return data;
  },
};

// Unified Chat API (searches across PDFs and Videos)
export const unifiedChatApi = {
  // Unified chat across all sources
  chat: async (params: {
    question: string;
    source_types?: Array<'pdf' | 'youtube' | 'all'>;
    doc_ids?: string[];
    top_k_per_source?: number;
    use_images?: boolean;
    semantic_weight?: number;
    keyword_weight?: number;
  }): Promise<{
    answer: string;
    citations: Array<{
      source_type: 'pdf' | 'youtube';
      doc_id: string;
      doc_title: string;
      chunk_id: string;
      content: string;
      page_number?: number;
      timestamp?: number;
      timestamp_formatted?: string;
      video_url?: string;
      section_path: string[];
      similarity_score: number;
      thumbnail_url?: string;
    }>;
    sources_searched: string[];
    total_sources_found: number;
    model_used: string;
    tokens_used: number;
  }> => {
    const { data } = await api.post('/chat/unified/', {
      question: params.question,
      source_types: params.source_types || ['all'],
      doc_ids: params.doc_ids || [],
      top_k_per_source: params.top_k_per_source || 5,
      use_images: params.use_images || false,
      semantic_weight: params.semantic_weight || 0.5,
      keyword_weight: params.keyword_weight || 0.5,
    });
    return data;
  },
};
