import { useEffect, useState } from 'react';
import { Search, FileText, FolderOpen, ExternalLink } from 'lucide-react';
import { documentsApi } from '@/services/api';
import type { Document } from '@/types';
import { formatRelativeTime, formatNumber, getStatusBadgeClass } from '@/utils/format';

export default function Documents() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [semanticMode, setSemanticMode] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchDocuments();
  }, [statusFilter]);

  async function fetchDocuments() {
    try {
      setLoading(true);
      const response = await documentsApi.list({
        status: statusFilter === 'all' ? undefined : statusFilter,
        search: search || undefined,
        semantic: semanticMode,
        page_size: 50,
      });
      setDocuments(response.documents);
    } catch (error) {
      console.error('Failed to fetch documents:', error);
    } finally {
      setLoading(false);
    }
  }

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    fetchDocuments();
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold">Document Library</h1>
        <p className="text-gray-600 mt-1">Browse and manage ingested documents</p>
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
              placeholder={semanticMode ? "Search by meaning (e.g., 'HVAC setup')..." : "Search documents..."}
              className="input w-full pl-10"
            />
          </div>
          <button type="submit" className="btn-primary">Search</button>
        </form>

        {/* Search Mode Toggle */}
        <div className="flex gap-4 text-sm mb-4 pb-4 border-b border-gray-200">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="radio"
              checked={!semanticMode}
              onChange={() => setSemanticMode(false)}
              className="cursor-pointer w-4 h-4"
            />
            <span className={!semanticMode ? 'font-semibold text-gray-900' : 'text-gray-600'}>
              Keyword search
            </span>
            <span className="text-xs text-gray-500">(filename & title)</span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="radio"
              checked={semanticMode}
              onChange={() => setSemanticMode(true)}
              className="cursor-pointer w-4 h-4"
            />
            <span className={semanticMode ? 'font-semibold text-gray-900' : 'text-gray-600'}>
              Semantic search
            </span>
            <span className="text-xs text-gray-500">(AI-powered meaning)</span>
          </label>
        </div>

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

      {/* Documents Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {loading ? (
          <div className="col-span-full text-center py-12 text-gray-500">Loading...</div>
        ) : documents.length === 0 ? (
          <div className="col-span-full card text-center py-12 text-gray-500">
            <FileText className="w-12 h-12 mx-auto mb-4 text-gray-300" />
            <p>No documents found</p>
          </div>
        ) : (
          documents.map((doc) => (
            <div
              key={doc.id}
              className="card hover:shadow-md transition-shadow cursor-pointer"
              onClick={() => window.location.href = `/documents/${doc.id}`}
            >
              <div className="flex items-start justify-between mb-3">
                <div className="flex-1">
                  <h3 className="font-semibold text-lg">{doc.title}</h3>
                  <p className="text-sm text-gray-500 mt-1">{doc.filename}</p>
                  {semanticMode && doc.relevance_score && doc.relevance_score > 0 && (
                    <p className="text-xs text-blue-600 mt-1 font-medium">
                      Relevance: {(doc.relevance_score * 100).toFixed(1)}%
                    </p>
                  )}
                </div>
                <span className={getStatusBadgeClass(doc.status)}>{doc.status}</span>
              </div>

              {doc.summary && (
                <p className="text-sm text-gray-600 mb-4 line-clamp-2">{doc.summary}</p>
              )}

              <div className="grid grid-cols-2 gap-4 text-sm mb-4">
                <div>
                  <span className="text-gray-500">Pages:</span>
                  <span className="ml-2 font-medium">{formatNumber(doc.total_pages)}</span>
                </div>
                <div>
                  <span className="text-gray-500">Chunks:</span>
                  <span className="ml-2 font-medium">{formatNumber(doc.total_chunks)}</span>
                </div>
                <div>
                  <span className="text-gray-500">Images:</span>
                  <span className="ml-2 font-medium">{formatNumber(doc.total_images)}</span>
                </div>
                <div>
                  <span className="text-gray-500">Tables:</span>
                  <span className="ml-2 font-medium">{formatNumber(doc.total_tables)}</span>
                </div>
              </div>

              {doc.tags && doc.tags.length > 0 && (
                <div className="flex flex-wrap gap-2 mb-3">
                  {doc.tags.map((tag, i) => (
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
                  Processed {formatRelativeTime(doc.processed_at)}
                  {doc.ingestion_cost_usd && ` • Cost: $${doc.ingestion_cost_usd.toFixed(4)}`}
                </span>
                {doc.gdrive_link && (
                  <a
                    href={doc.gdrive_link}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={(e) => e.stopPropagation()}
                    className="flex items-center gap-1 text-blue-600 hover:text-blue-700 font-medium"
                    title="View in Google Drive"
                  >
                    <FolderOpen className="w-4 h-4" />
                    <span className="text-xs">Drive</span>
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
