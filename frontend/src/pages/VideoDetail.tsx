import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Youtube as YoutubeIcon } from 'lucide-react';
import { youtubeApi } from '@/services/api';
import type { Document } from '@/types';
import { formatNumber, formatRelativeTime, getStatusBadgeClass } from '@/utils/format';
import DocumentChatImproved from '@/components/DocumentChatImproved';

interface VideoData extends Document {
  youtube_id: string;
  source_url: string;
  duration_seconds: number;
  channel_name: string;
  // Add any other video-specific fields
}

interface TranscriptSegment {
  timestamp_start: number;
  timestamp_formatted: string;
  content: string;
  video_url: string;
}

export default function VideoDetail() {
  const { videoId } = useParams<{ videoId: string }>();
  const navigate = useNavigate();

  const [video, setVideo] = useState<VideoData | null>(null);
  const [transcript, setTranscript] = useState<TranscriptSegment[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (videoId) {
      fetchVideoData();
    }
  }, [videoId]);

  async function fetchVideoData() {
    try {
      setLoading(true);

      const response = await youtubeApi.get(videoId!);
      setVideo(response);  // Response is the video object itself
      setTranscript(response.transcript || []);

    } catch (error) {
      console.error('Failed to fetch video:', error);
      // Set video to null on error so we show "Video not found"
      setVideo(null);
    } finally {
      setLoading(false);
    }
  }

  // Function to format seconds into HH:MM:SS
  const formatSeconds = (seconds: number) => {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    const parts = [m, s];
    if (h > 0) parts.unshift(h);
    return parts.map(v => v < 10 ? '0' + v : v).join(':');
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500">Loading video details...</div>
      </div>
    );
  }

  if (!video) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500">Video not found</div>
      </div>
    );
  }

  const youtubeEmbedUrl = `https://www.youtube.com/embed/${video.youtube_id}?autoplay=0&rel=0`;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start gap-4">
        <button
          onClick={() => navigate('/videos')} // Navigate back to video list
          className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
        >
          <ArrowLeft className="w-5 h-5" />
        </button>
        <div className="flex-1">
          <div className="flex items-center gap-3 mb-2">
            <h1 className="text-3xl font-bold">{video.title}</h1>
            <span className={getStatusBadgeClass(video.status)}>{video.status}</span>
          </div>
          <p className="text-gray-600">{video.channel_name}</p>
          <div className="flex gap-4 mt-2 text-sm text-gray-500">
            <span>Processed {formatRelativeTime(video.processed_at)}</span>
            {video.ingestion_cost_usd && <span>• Cost: ${video.ingestion_cost_usd.toFixed(4)}</span>}
            {video.processing_duration_seconds && (
              <span>• Duration: {formatSeconds(video.duration_seconds)}</span>
            )}
          </div>
          {video.source_url && (
            <a
              href={video.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 mt-3 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors text-sm font-medium"
            >
              <YoutubeIcon className="w-4 h-4" />
              Watch on YouTube
            </a>
          )}
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="card">
          <div className="text-sm text-gray-500 mb-1">Duration</div>
          <div className="text-2xl font-bold">{formatSeconds(video.duration_seconds)}</div>
        </div>
        <div className="card">
          <div className="text-sm text-gray-500 mb-1">Chunks</div>
          <div className="text-2xl font-bold">{formatNumber(video.total_chunks)}</div>
        </div>
        <div className="card">
          <div className="text-sm text-gray-500 mb-1">Images</div>
          <div className="text-2xl font-bold">{formatNumber(video.total_images)}</div>
        </div>
      </div>

      {/* Tags */}
      {video.tags && video.tags.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {video.tags.map((tag, i) => (
            <span key={i} className="px-3 py-1 bg-red-100 text-red-700 rounded-full text-sm">
              {tag}
            </span>
          ))}
        </div>
      )}

      {/* Main Content: Side-by-side Video + Chat */}
      <div className="flex gap-6 h-[800px]">
        {/* Left: Video & Transcript */}
        <div className="w-1/2 flex flex-col gap-4">
          {/* Video Player */}
          <div className="card p-0 overflow-hidden flex-shrink-0" style={{ height: '450px' }}>
            <iframe
              className="w-full h-full"
              src={youtubeEmbedUrl}
              frameBorder="0"
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
              allowFullScreen
              title={video.title}
            ></iframe>
          </div>

          {/* Transcript Below Video */}
          {transcript.length > 0 && (
            <div className="card flex-1 overflow-hidden flex flex-col">
              <h3 className="text-lg font-semibold mb-3">Transcript</h3>
              <div className="flex-1 overflow-y-auto space-y-2 pr-2">
                {transcript.map((segment, index) => (
                  <div key={index} className="text-sm hover:bg-gray-50 p-2 rounded transition-colors">
                    <a
                      href={segment.video_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-blue-600 hover:underline font-medium mr-2"
                    >
                      {segment.timestamp_formatted}
                    </a>
                    <span className="text-gray-700">{segment.content}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Right: Chat */}
        <div className="w-1/2">
          <DocumentChatImproved
            docId={videoId!}
            documentTitle={video.title}
            isVideo={true}
          />
        </div>
      </div>
    </div>
  );
}
