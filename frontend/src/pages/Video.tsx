import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, Youtube, ExternalLink } from 'lucide-react';
import { youtubeApi } from '@/services/api';
import type { Document } from '@/types'; // Assuming youtube videos will have a similar structure
import { formatRelativeTime, formatNumber, getStatusBadgeClass } from '@/utils/format';

export default function Videos() {
  const navigate = useNavigate();
  const [videos, setVideos] = useState<Document[]>([]);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchVideos();
  }, [statusFilter, search]);

  async function fetchVideos() {
    try {
      setLoading(true);
      const response = await youtubeApi.list({
        status: statusFilter === 'all' ? undefined : statusFilter,
        // search: search || undefined, // Add when backend supports search for videos
        limit: 50,
      });
      setVideos(response.documents); // Assuming the list is in a 'documents' property
    } catch (error) {
      console.error('Failed to fetch videos:', error);
    } finally {
      setLoading(false);
    }
  }

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    fetchVideos();
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold">Video Library</h1>
        <p className="text-gray-600 mt-1">Browse and manage ingested YouTube videos</p>
      </div>

      {/* Search and Filters */}
      <div className="card">
        <form onSubmit={handleSearch} className="flex gap-4 mb-4">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search videos..."
              className="input w-full pl-10"
            />
          </div>
          <button type="submit" className="btn-primary">Search</button>
        </form>

        <div className="flex gap-2">
          {['all', 'processing', 'completed', 'failed'].map((status) => (
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

      {/* Videos Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {loading ? (
          <div className="col-span-full text-center py-12 text-gray-500">Loading...</div>
        ) : videos.length === 0 ? (
          <div className="col-span-full card text-center py-12 text-gray-500">
            <Youtube className="w-12 h-12 mx-auto mb-4 text-gray-300" />
            <p>No videos found</p>
          </div>
        ) : (
          videos.map((video) => (
            <div
              key={video.id}
              className="card hover:shadow-md transition-shadow cursor-pointer"
              onClick={() => navigate(`/videos/${video.id}`)}
            >
              <div className="flex items-start justify-between mb-3">
                <div className="flex-1">
                  <h3 className="font-semibold text-lg">{video.title}</h3>
                  <p className="text-sm text-gray-500 mt-1">{video.channel_name}</p>
                </div>
                <span className={getStatusBadgeClass(video.status)}>{video.status}</span>
              </div>

              {video.summary && (
                <p className="text-sm text-gray-600 mb-4 line-clamp-2">{video.summary}</p>
              )}

              <div className="grid grid-cols-2 gap-4 text-sm mb-4">
                <div>
                  <span className="text-gray-500">Duration:</span>
                  <span className="ml-2 font-medium">{video.duration_seconds ? `${Math.floor(video.duration_seconds / 60)}m ${video.duration_seconds % 60}s` : 'N/A'}</span>
                </div>
                <div>
                  <span className="text-gray-500">Chunks:</span>
                  <span className="ml-2 font-medium">{formatNumber(video.total_chunks)}</span>
                </div>
              </div>

              {video.tags && video.tags.length > 0 && (
                <div className="flex flex-wrap gap-2 mb-3">
                  {video.tags.map((tag, i) => (
                    <span
                      key={i}
                      className="px-2 py-1 bg-gray-100 text-gray-700 rounded text-xs"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              )}

              <div className="text-xs text-gray-500 border-t pt-3 flex items-center justify-between">
                <span>
                  Processed {formatRelativeTime(video.processed_at)}
                  {video.ingestion_cost_usd && ` • Cost: $${video.ingestion_cost_usd.toFixed(4)}`}
                </span>
                {video.source_url && (
                  <a
                    href={video.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={(e) => e.stopPropagation()}
                    className="flex items-center gap-1 text-blue-600 hover:text-blue-700 font-medium"
                    title="View on YouTube"
                  >
                    <Youtube className="w-4 h-4" />
                    <span className="text-xs">YouTube</span>
                    <ExternalLink className="w-3 h-3" />
                  </a>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
