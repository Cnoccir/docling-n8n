import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, FileText, ExternalLink } from 'lucide-react';
import { documentsApi } from '@/services/api';
import type { Document } from '@/types';
import { formatNumber, formatRelativeTime, getStatusBadgeClass } from '@/utils/format';
import DocumentChatImproved from '@/components/DocumentChatImproved';

export default function DocumentDetail() {
  const { docId } = useParams<{ docId: string }>();
  const navigate = useNavigate();

  const [document, setDocument] = useState<Document | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (docId) {
      fetchDocumentData();
    }
  }, [docId]);

  async function fetchDocumentData() {
    try {
      setLoading(true);
      const doc = await documentsApi.get(docId!);
      setDocument(doc);
    } catch (error) {
      console.error('Failed to fetch document:', error);
    } finally {
      setLoading(false);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500">Loading document...</div>
      </div>
    );
  }

  if (!document) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500">Document not found</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start gap-4">
        <button
          onClick={() => navigate('/documents')}
          className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
        >
          <ArrowLeft className="w-5 h-5" />
        </button>
        <div className="flex-1">
          <div className="flex items-center gap-3 mb-2">
            <h1 className="text-3xl font-bold">{document.title}</h1>
            <span className={getStatusBadgeClass(document.status)}>{document.status}</span>
          </div>
          <p className="text-gray-600">{document.filename}</p>
          <div className="flex gap-4 mt-2 text-sm text-gray-500">
            <span>Processed {formatRelativeTime(document.processed_at)}</span>
            {document.ingestion_cost_usd && <span>• Cost: ${document.ingestion_cost_usd.toFixed(4)}</span>}
            {document.processing_duration_seconds && (
              <span>• Duration: {Math.round(document.processing_duration_seconds / 60)}m</span>
            )}
          </div>
          {document.gdrive_link && (
            <a
              href={document.gdrive_link}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 mt-3 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium"
            >
              <ExternalLink className="w-4 h-4" />
              Open in Google Drive
            </a>
          )}
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="card">
          <div className="text-sm text-gray-500 mb-1">Pages</div>
          <div className="text-2xl font-bold">{formatNumber(document.total_pages)}</div>
        </div>
        <div className="card">
          <div className="text-sm text-gray-500 mb-1">Chunks</div>
          <div className="text-2xl font-bold">{formatNumber(document.total_chunks)}</div>
        </div>
        <div className="card">
          <div className="text-sm text-gray-500 mb-1">Images</div>
          <div className="text-2xl font-bold">{formatNumber(document.total_images)}</div>
        </div>
        <div className="card">
          <div className="text-sm text-gray-500 mb-1">Tables</div>
          <div className="text-2xl font-bold">{formatNumber(document.total_tables)}</div>
        </div>
      </div>

      {/* Tags */}
      {document.tags && document.tags.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {document.tags.map((tag, i) => (
            <span key={i} className="px-3 py-1 bg-blue-100 text-blue-700 rounded-full text-sm">
              {tag}
            </span>
          ))}
        </div>
      )}

      {/* Main Content: Side-by-side PDF + Chat */}
      <div className="flex gap-6 h-[800px]">
        {/* Left: PDF Viewer */}
        <div className="w-1/2 flex flex-col gap-4">
          {/* PDF Viewer */}
          {document.gdrive_file_id ? (
            <div className="card p-0 overflow-hidden flex-1">
              <div className="flex items-center justify-between p-4 border-b bg-gray-50">
                <h3 className="font-semibold flex items-center gap-2">
                  <FileText className="w-4 h-4" />
                  PDF Preview
                </h3>
                <a
                  href={document.gdrive_link || ''}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm text-blue-600 hover:text-blue-700 flex items-center gap-1"
                >
                  Open in new tab
                  <ExternalLink className="w-3 h-3" />
                </a>
              </div>
              <div className="relative bg-gray-100 h-full">
                <iframe
                  src={`https://drive.google.com/file/d/${document.gdrive_file_id}/preview`}
                  className="w-full h-full border-0"
                  allow="autoplay"
                  title={`Preview of ${document.title}`}
                />
              </div>
            </div>
          ) : (
            <div className="card flex-1 flex items-center justify-center text-gray-500">
              <div className="text-center">
                <FileText className="w-12 h-12 mx-auto mb-3 text-gray-400" />
                <p>PDF preview not available</p>
                <p className="text-sm mt-1">Document may not be uploaded to Google Drive</p>
              </div>
            </div>
          )}
        </div>

        {/* Right: Chat */}
        <div className="w-1/2">
          <DocumentChatImproved
            docId={docId!}
            documentTitle={document.title}
            isVideo={false}
          />
        </div>
      </div>
    </div>
  );
}
