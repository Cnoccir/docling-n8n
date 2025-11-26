import { useEffect, useState } from 'react';
import { RefreshCw, XCircle, RotateCcw } from 'lucide-react';
import ProgressBar from '@/components/ProgressBar';
import { jobsApi } from '@/services/api';
import { websocketClient } from '@/services/websocket';
import type { Job } from '@/types';
import { formatRelativeTime, formatDuration, getStatusBadgeClass } from '@/utils/format';

export default function QueueManager() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchJobs();
    websocketClient.connect();

    const unsubscribe = websocketClient.onJobUpdate((update) => {
      setJobs((prev) =>
        prev.map((job) =>
          job.id === update.job_id
            ? { ...job, status: update.status, progress: update.progress, current_step: update.current_step }
            : job
        )
      );
    });

    return () => {
      unsubscribe();
    };
  }, [statusFilter]);

  async function fetchJobs() {
    try {
      setLoading(true);
      const response = await jobsApi.list({
        status: statusFilter === 'all' ? undefined : statusFilter,
        page_size: 50,
      });
      setJobs(response.jobs);
    } catch (error) {
      console.error('Failed to fetch jobs:', error);
    } finally {
      setLoading(false);
    }
  }

  async function cancelJob(jobId: string) {
    try {
      await jobsApi.cancel(jobId);
      setJobs((prev) =>
        prev.map((job) => (job.id === jobId ? { ...job, status: 'cancelled' } : job))
      );
    } catch (error) {
      console.error('Failed to cancel job:', error);
    }
  }

  async function retryJob(jobId: string) {
    try {
      await jobsApi.retry(jobId);
      fetchJobs(); // Refresh list
    } catch (error) {
      console.error('Failed to retry job:', error);
      alert('Failed to retry job: ' + (error as Error).message);
    }
  }

  async function resumeJob(jobId: string) {
    try {
      const result = await jobsApi.resume(jobId);
      alert(`Job resumed!\n\n${result.checkpoint_summary}`);
      fetchJobs(); // Refresh list
    } catch (error) {
      console.error('Failed to resume job:', error);
      alert('Failed to resume job: ' + (error as Error).message);
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold">Queue Manager</h1>
          <p className="text-gray-600 mt-1">Monitor and manage document processing jobs</p>
        </div>
        <button onClick={fetchJobs} className="btn-secondary flex items-center gap-2">
          <RefreshCw className="w-4 h-4" />
          Refresh
        </button>
      </div>

      {/* Filters */}
      <div className="card">
        <div className="flex gap-2">
          {['all', 'queued', 'processing', 'completed', 'failed', 'cancelled'].map((status) => (
            <button
              key={status}
              onClick={() => setStatusFilter(status)}
              className={`px-4 py-2 rounded-lg font-medium capitalize transition-colors ${
                statusFilter === status
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              {status}
            </button>
          ))}
        </div>
      </div>

      {/* Jobs List */}
      <div className="space-y-4">
        {loading ? (
          <div className="text-center py-12 text-gray-500">Loading...</div>
        ) : jobs.length === 0 ? (
          <div className="card text-center py-12 text-gray-500">
            No jobs found
          </div>
        ) : (
          jobs.map((job) => (
            <div key={job.id} className="card">
              <div className="flex items-start justify-between mb-4">
                <div className="flex-1">
                  <h3 className="font-semibold text-lg">{job.filename}</h3>
                  <p className="text-sm text-gray-500 mt-1">
                    Queued {formatRelativeTime(job.queued_at)}
                    {job.worker_id && ` • Worker: ${job.worker_id}`}
                  </p>
                </div>
                <span className={getStatusBadgeClass(job.status)}>{job.status}</span>
              </div>

              {job.status === 'processing' && (
                <div className="mb-4">
                  <ProgressBar
                    progress={job.progress}
                    label={job.current_step?.replace(/_/g, ' ') || 'Processing'}
                  />
                </div>
              )}

              {job.status === 'failed' && job.error_message && (
                <div className="bg-red-50 border border-red-200 rounded-lg p-3 mb-4">
                  <p className="text-sm text-red-800">
                    <span className="font-medium">Error:</span> {job.error_message}
                  </p>
                </div>
              )}

              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm mb-4">
                {job.total_pages && (
                  <div>
                    <span className="text-gray-500">Pages:</span>
                    <span className="ml-2 font-medium">{job.total_pages}</span>
                  </div>
                )}
                {job.total_chunks && (
                  <div>
                    <span className="text-gray-500">Chunks:</span>
                    <span className="ml-2 font-medium">{job.total_chunks}</span>
                  </div>
                )}
                {job.actual_duration_seconds && (
                  <div>
                    <span className="text-gray-500">Duration:</span>
                    <span className="ml-2 font-medium">{formatDuration(job.actual_duration_seconds)}</span>
                  </div>
                )}
                {job.ingestion_cost_usd && (
                  <div>
                    <span className="text-gray-500">Cost:</span>
                    <span className="ml-2 font-medium">${job.ingestion_cost_usd.toFixed(4)}</span>
                  </div>
                )}
              </div>

              {/* Actions */}
              <div className="flex gap-2">
                {(job.status === 'queued' || job.status === 'processing') && (
                  <button
                    onClick={() => cancelJob(job.id)}
                    className="btn-danger flex items-center gap-2 text-sm"
                  >
                    <XCircle className="w-4 h-4" />
                    Cancel
                  </button>
                )}
                {job.status === 'failed' && (
                  <>
                    <button
                      onClick={() => resumeJob(job.id)}
                      className="btn-primary flex items-center gap-2 text-sm"
                      title="Resume from checkpoint (saves tokens & time)"
                    >
                      <RefreshCw className="w-4 h-4" />
                      Resume
                    </button>
                    <button
                      onClick={() => retryJob(job.id)}
                      className="btn-secondary flex items-center gap-2 text-sm"
                      title="Retry from scratch"
                    >
                      <RotateCcw className="w-4 h-4" />
                      Retry
                    </button>
                  </>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
