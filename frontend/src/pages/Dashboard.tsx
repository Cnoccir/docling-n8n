import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { FileText, Clock, CheckCircle, XCircle, DollarSign, Activity } from 'lucide-react';
import StatCard from '@/components/StatCard';
import ProgressBar from '@/components/ProgressBar';
import { jobsApi, analyticsApi } from '@/services/api';
import { websocketClient } from '@/services/websocket';
import { useAppStore } from '@/store';
import type { Job } from '@/types';
import { formatRelativeTime, formatCurrency, getStatusBadgeClass } from '@/utils/format';

export default function Dashboard() {
  const { queueStats, setQueueStats } = useAppStore();
  const [recentJobs, setRecentJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [queryStats, setQueryStats] = useState<any>(null);

  useEffect(() => {
    fetchData();
    websocketClient.connect();

    const unsubscribe = websocketClient.onJobUpdate((update) => {
      // Update job in recent jobs list
      setRecentJobs((prev) =>
        prev.map((job) =>
          job.id === update.job_id
            ? { ...job, status: update.status, progress: update.progress, current_step: update.current_step }
            : job
        )
      );
      
      // Refresh stats when job completes or fails
      if (update.status === 'completed' || update.status === 'failed') {
        fetchStats();
      }
    });

    return () => {
      unsubscribe();
    };
  }, []);

  async function fetchData() {
    try {
      setLoading(true);
      await Promise.all([fetchStats(), fetchRecentJobs(), fetchQueryStats()]);
    } catch (error) {
      console.error('Failed to fetch dashboard data:', error);
    } finally {
      setLoading(false);
    }
  }

  async function fetchStats() {
    try {
      const stats = await jobsApi.getQueueStats();
      setQueueStats(stats);
    } catch (error) {
      console.error('Failed to fetch queue stats:', error);
    }
  }

  async function fetchRecentJobs() {
    try {
      const response = await jobsApi.list({ page: 1, page_size: 5 });
      setRecentJobs(response.jobs);
    } catch (error) {
      console.error('Failed to fetch recent jobs:', error);
    }
  }

  async function fetchQueryStats() {
    try {
      const summary = await analyticsApi.getSummary();
      setQueryStats(summary);
    } catch (error) {
      console.error('Failed to fetch query stats:', error);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500">Loading...</div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold">Dashboard</h1>
        <p className="text-gray-600 mt-1">Monitor document ingestion queue and statistics</p>
      </div>

      {/* Stats Grid - Ingestion */}
      <div>
        <h2 className="text-lg font-semibold mb-4 text-gray-700">Ingestion Pipeline</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          <StatCard
            title="Total Jobs"
            value={queueStats?.total_jobs || 0}
            icon={FileText}
            color="blue"
          />
          <StatCard
            title="Processing"
            value={queueStats?.processing_jobs || 0}
            icon={Activity}
            color="blue"
          />
          <StatCard
            title="Queued"
            value={queueStats?.queued_jobs || 0}
            icon={Clock}
            color="yellow"
          />
          <StatCard
            title="Completed"
            value={queueStats?.completed_jobs || 0}
            icon={CheckCircle}
            color="green"
          />
          <StatCard
            title="Failed"
            value={queueStats?.failed_jobs || 0}
            icon={XCircle}
            color="red"
          />
          <StatCard
            title="Ingestion Cost"
            value={formatCurrency(queueStats?.total_cost_usd || 0)}
            icon={DollarSign}
            color="gray"
          />
        </div>
      </div>

      {/* Query Analytics Stats */}
      {queryStats && (
        <div>
          <h2 className="text-lg font-semibold mb-4 text-gray-700">Query Analytics (Chat & Search)</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            <StatCard
              title="Total Queries"
              value={queryStats.total_queries || 0}
              icon={Activity}
              color="blue"
            />
            <StatCard
              title="Query Cost"
              value={formatCurrency(queryStats.total_cost_usd || 0)}
              icon={DollarSign}
              color="blue"
            />
            <StatCard
              title="Avg Cost/Query"
              value={formatCurrency(queryStats.avg_cost_per_query || 0)}
              icon={DollarSign}
              color="gray"
            />
            <StatCard
              title="Success Rate"
              value={`${queryStats.total_queries > 0 ? ((queryStats.successful_queries / queryStats.total_queries) * 100).toFixed(1) : 0}%`}
              icon={CheckCircle}
              color="green"
            />
          </div>
        </div>
      )}

      {/* Recent Jobs */}
      <div className="card">
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-xl font-semibold">Recent Jobs</h2>
          <Link to="/queue" className="text-blue-600 hover:text-blue-700 text-sm font-medium">
            View All →
          </Link>
        </div>

        <div className="space-y-4">
          {recentJobs.length === 0 ? (
            <p className="text-center text-gray-500 py-8">No jobs yet. Upload a document to get started!</p>
          ) : (
            recentJobs.map((job) => (
              <div key={job.id} className="border border-gray-200 rounded-lg p-4 hover:border-blue-300 transition-colors">
                <div className="flex items-start justify-between mb-3">
                  <div className="flex-1">
                    <h3 className="font-medium text-gray-900">{job.filename}</h3>
                    <p className="text-sm text-gray-500 mt-1">
                      {job.current_step ? job.current_step.replace(/_/g, ' ') : 'Queued'} • {formatRelativeTime(job.queued_at)}
                    </p>
                  </div>
                  <span className={getStatusBadgeClass(job.status)}>{job.status}</span>
                </div>
                
                {job.status === 'processing' && (
                  <ProgressBar progress={job.progress} showPercentage size="sm" />
                )}

                {job.status === 'failed' && job.error_message && (
                  <p className="text-sm text-red-600 mt-2">Error: {job.error_message}</p>
                )}
              </div>
            ))
          )}
        </div>
      </div>

      {/* Quick Actions */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Link to="/upload" className="card hover:shadow-md transition-shadow cursor-pointer">
          <h3 className="text-lg font-semibold mb-2">Upload Documents</h3>
          <p className="text-gray-600">Upload PDFs for processing and ingestion</p>
        </Link>
        
        <Link to="/documents" className="card hover:shadow-md transition-shadow cursor-pointer">
          <h3 className="text-lg font-semibold mb-2">Browse Documents</h3>
          <p className="text-gray-600">View and manage your document library</p>
        </Link>
      </div>
    </div>
  );
}
