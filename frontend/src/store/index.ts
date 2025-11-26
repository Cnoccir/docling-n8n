import { create } from 'zustand';
import type { Job, QueueStats, WorkerInfo } from '@/types';

interface AppState {
  // Jobs
  jobs: Job[];
  selectedJob: Job | null;
  
  // Queue stats
  queueStats: QueueStats | null;
  workers: WorkerInfo[];
  
  // UI state
  isLoading: boolean;
  error: string | null;
  
  // Actions
  setJobs: (jobs: Job[]) => void;
  updateJob: (jobId: string, updates: Partial<Job>) => void;
  setSelectedJob: (job: Job | null) => void;
  setQueueStats: (stats: QueueStats) => void;
  setWorkers: (workers: WorkerInfo[]) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
}

export const useAppStore = create<AppState>((set) => ({
  // Initial state
  jobs: [],
  selectedJob: null,
  queueStats: null,
  workers: [],
  isLoading: false,
  error: null,

  // Actions
  setJobs: (jobs) => set({ jobs }),
  
  updateJob: (jobId, updates) =>
    set((state) => ({
      jobs: state.jobs.map((job) =>
        job.id === jobId ? { ...job, ...updates } : job
      ),
      selectedJob:
        state.selectedJob?.id === jobId
          ? { ...state.selectedJob, ...updates }
          : state.selectedJob,
    })),
  
  setSelectedJob: (job) => set({ selectedJob: job }),
  setQueueStats: (queueStats) => set({ queueStats }),
  setWorkers: (workers) => set({ workers }),
  setLoading: (isLoading) => set({ isLoading }),
  setError: (error) => set({ error }),
}));
