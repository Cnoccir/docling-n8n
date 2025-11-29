import { useState } from 'react';
import { Search, FileText, Youtube, Loader2, ExternalLink, Play, Image as ImageIcon } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { unifiedChatApi } from '@/services/api';
import { useNavigate } from 'react-router-dom';

interface Citation {
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
}

interface RelatedImage {
  url: string;
  caption?: string;
  image_type?: string;
  page_number?: number;
  timestamp?: number;
}

interface SearchResult {
  answer: string;
  citations: Citation[];
  sources_searched: string[];
  total_sources_found: number;
  model_used: string;
  tokens_used: number;
  related_images?: RelatedImage[];
}

export default function UnifiedSearch() {
  const [query, setQuery] = useState('');
  const [searchPDFs, setSearchPDFs] = useState(true);
  const [searchVideos, setSearchVideos] = useState(true);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<SearchResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  const handleSearch = async () => {
    if (!query.trim()) {
      setError('Please enter a search query');
      return;
    }

    if (!searchPDFs && !searchVideos) {
      setError('Please select at least one source type');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      // Determine source types
      let source_types: Array<'pdf' | 'youtube' | 'all'>;
      if (searchPDFs && searchVideos) {
        source_types = ['all'];
      } else if (searchPDFs) {
        source_types = ['pdf'];
      } else {
        source_types = ['youtube'];
      }

      const response = await unifiedChatApi.chat({
        question: query,
        source_types,
        top_k_per_source: 5,
        use_images: true,
      });

      setResult(response);
    } catch (err: any) {
      console.error('Search failed:', err);
      setError(err.response?.data?.detail || err.message || 'Search failed');
    } finally {
      setLoading(false);
    }
  };

  const handleCitationClick = (citation: Citation) => {
    if (citation.source_type === 'pdf') {
      navigate(`/documents/${citation.doc_id}`);
    } else if (citation.source_type === 'youtube') {
      if (citation.video_url) {
        window.open(citation.video_url, '_blank');
      } else {
        navigate(`/videos/${citation.doc_id}`);
      }
    }
  };

  const formatTimestamp = (seconds: number) => {
    const minutes = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${minutes}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="text-center space-y-3">
        <h1 className="text-4xl font-bold bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">
          AME Knowledge Search
        </h1>
        <p className="text-gray-600 text-lg">
          Your technical knowledge repository - search across documents, videos, and more
        </p>
      </div>

      {/* Search Box */}
      <div className="card p-6 space-y-4">
        <div className="flex gap-4">
          <div className="flex-1 relative">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && !loading && handleSearch()}
              placeholder="Ask a question across all your content..."
              className="w-full px-4 py-3 pl-12 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
            <Search className="absolute left-4 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
          </div>

          <button
            onClick={handleSearch}
            disabled={loading || !query.trim()}
            className="px-8 py-3 bg-gradient-to-r from-blue-600 to-purple-600 text-white font-semibold rounded-lg hover:from-blue-700 hover:to-purple-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 transition-all shadow-lg hover:shadow-xl"
          >
            {loading ? (
              <>
                <Loader2 className="w-5 h-5 animate-spin" />
                Searching...
              </>
            ) : (
              <>
                <Search className="w-5 h-5" />
                Search
              </>
            )}
          </button>
        </div>

        {/* Source Type Filters */}
        <div className="flex items-center gap-6">
          <span className="text-sm font-medium text-gray-700">Search in:</span>

          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={searchPDFs}
              onChange={(e) => setSearchPDFs(e.target.checked)}
              className="w-4 h-4 text-blue-600 rounded focus:ring-2 focus:ring-blue-500"
            />
            <FileText className="w-4 h-4 text-blue-600" />
            <span className="text-sm text-gray-700">Documents (PDFs)</span>
          </label>

          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={searchVideos}
              onChange={(e) => setSearchVideos(e.target.checked)}
              className="w-4 h-4 text-red-600 rounded focus:ring-2 focus:ring-red-500"
            />
            <Youtube className="w-4 h-4 text-red-600" />
            <span className="text-sm text-gray-700">Videos (YouTube)</span>
          </label>
        </div>

        {/* Error Message */}
        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
            {error}
          </div>
        )}
      </div>

      {/* Results */}
      {result && (
        <div className="space-y-6">
          {/* Answer Section */}
          <div className="card p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold text-gray-900">Answer</h2>
              <div className="flex items-center gap-4 text-sm text-gray-500">
                <span>Model: {result.model_used}</span>
                <span>•</span>
                <span>{result.tokens_used.toLocaleString()} tokens</span>
                <span>•</span>
                <span>{result.total_sources_found} sources found</span>
              </div>
            </div>

            <div className="prose prose-lg max-w-none">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  code({ className, children }: any) {
                    const match = /language-(\w+)/.exec(className || '');
                    const inline = !match;
                    return !inline ? (
                      <SyntaxHighlighter
                        style={vscDarkPlus as any}
                        language={match[1]}
                        PreTag="div"
                      >
                        {String(children).replace(/\n$/, '')}
                      </SyntaxHighlighter>
                    ) : (
                      <code className="bg-gray-100 px-1.5 py-0.5 rounded text-sm font-mono text-pink-600">
                        {children}
                      </code>
                    );
                  },
                  h2: ({ children }) => (
                    <h2 className="text-2xl font-bold text-gray-900 mt-8 mb-4 border-b pb-2">{children}</h2>
                  ),
                  h3: ({ children }) => (
                    <h3 className="text-xl font-semibold text-gray-800 mt-6 mb-3">{children}</h3>
                  ),
                  blockquote: ({ children }) => (
                    <blockquote className="border-l-4 border-blue-500 pl-4 py-2 bg-blue-50 italic text-gray-700 my-4">
                      {children}
                    </blockquote>
                  ),
                  ul: ({ children }) => (
                    <ul className="list-disc list-inside space-y-2 my-4">{children}</ul>
                  ),
                  ol: ({ children }) => (
                    <ol className="list-decimal list-inside space-y-2 my-4">{children}</ol>
                  ),
                  li: ({ children }) => (
                    <li className="text-gray-700 leading-relaxed">{children}</li>
                  ),
                  p: ({ children }) => (
                    <p className="text-gray-800 leading-relaxed my-3">{children}</p>
                  ),
                  strong: ({ children }) => (
                    <strong className="font-bold text-gray-900">{children}</strong>
                  ),
                  a: ({ href, children }) => (
                    <a href={href} className="text-blue-600 hover:text-blue-800 underline" target="_blank" rel="noopener noreferrer">
                      {children}
                    </a>
                  ),
                }}
              >
                {result.answer}
              </ReactMarkdown>
            </div>

            {/* Related Images */}
            {result.related_images && result.related_images.length > 0 && (
              <div className="mt-8 border-t pt-6">
                <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
                  <ImageIcon className="w-5 h-5 text-blue-600" />
                  Related Visual Content ({result.related_images.length})
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {result.related_images.map((image, idx) => (
                    <div key={idx} className="border border-gray-200 rounded-lg overflow-hidden hover:shadow-lg transition-shadow bg-white">
                      <div className="aspect-video bg-gray-100 relative overflow-hidden">
                        <img
                          src={image.url}
                          alt={image.caption || `Related image ${idx + 1}`}
                          className="w-full h-full object-contain hover:scale-105 transition-transform duration-200"
                          loading="lazy"
                        />
                      </div>
                      {(image.caption || image.page_number || image.timestamp !== undefined) && (
                        <div className="p-3 bg-gray-50">
                          {image.caption && (
                            <p className="text-xs text-gray-700 line-clamp-2 mb-2">{image.caption}</p>
                          )}
                          <div className="flex items-center gap-2 flex-wrap">
                            {image.page_number && (
                              <span className="inline-flex items-center px-2 py-0.5 bg-blue-100 text-blue-700 text-xs rounded-full">
                                📄 Page {image.page_number}
                              </span>
                            )}
                            {image.timestamp !== undefined && (
                              <span className="inline-flex items-center px-2 py-0.5 bg-red-100 text-red-700 text-xs rounded-full">
                                ▶ {formatTimestamp(image.timestamp)}
                              </span>
                            )}
                            {image.image_type && (
                              <span className="inline-flex items-center px-2 py-0.5 bg-gray-200 text-gray-700 text-xs rounded-full capitalize">
                                {image.image_type}
                              </span>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Citations Section */}
          {result.citations.length > 0 && (
            <div className="card p-6">
              <h2 className="text-xl font-semibold text-gray-900 mb-4">
                Sources ({result.citations.length})
              </h2>

              <div className="space-y-3">
                {result.citations.map((citation, idx) => (
                  <button
                    key={idx}
                    onClick={() => handleCitationClick(citation)}
                    className="w-full text-left bg-gradient-to-r from-gray-50 to-blue-50 hover:from-gray-100 hover:to-blue-100 rounded-xl border border-gray-200 overflow-hidden transition-all shadow-sm hover:shadow-md p-4"
                  >
                    <div className="flex items-start gap-4">
                      {/* Citation Number */}
                      <div className="flex-shrink-0 w-10 h-10 bg-gradient-to-br from-blue-600 to-purple-600 text-white rounded-lg flex items-center justify-center font-bold text-sm shadow-md">
                        {idx + 1}
                      </div>

                      {/* Thumbnail for Videos */}
                      {citation.source_type === 'youtube' && citation.thumbnail_url && (
                        <div className="flex-shrink-0 w-32 h-20 rounded-lg overflow-hidden bg-black relative">
                          <img
                            src={citation.thumbnail_url}
                            alt="Video thumbnail"
                            className="w-full h-full object-cover"
                          />
                          <div className="absolute inset-0 flex items-center justify-center">
                            <Play className="w-8 h-8 text-white opacity-80" />
                          </div>
                        </div>
                      )}

                      {/* Citation Content */}
                      <div className="flex-1 min-w-0">
                        {/* Header */}
                        <div className="flex items-center gap-2 flex-wrap mb-2">
                          {citation.source_type === 'pdf' ? (
                            <>
                              <span className="inline-flex items-center px-2.5 py-1 bg-blue-600 text-white text-xs font-semibold rounded-full">
                                📄 Page {citation.page_number}
                              </span>
                            </>
                          ) : (
                            <>
                              <span className="inline-flex items-center px-2.5 py-1 bg-red-600 text-white text-xs font-semibold rounded-full">
                                ▶ {citation.timestamp_formatted || formatTimestamp(citation.timestamp || 0)}
                              </span>
                            </>
                          )}

                          {citation.section_path && citation.section_path.length > 0 && (
                            <span className="inline-flex items-center px-2.5 py-1 bg-gray-100 text-gray-700 text-xs font-medium rounded-full">
                              📂 {citation.section_path[citation.section_path.length - 1]}
                            </span>
                          )}

                          <span className="inline-flex items-center px-2.5 py-1 bg-green-100 text-green-700 text-xs font-semibold rounded-full ml-auto">
                            {(citation.similarity_score * 100).toFixed(0)}% match
                          </span>
                        </div>

                        {/* Document Title */}
                        <h3 className="font-semibold text-gray-900 mb-2">
                          {citation.doc_title}
                        </h3>

                        {/* Content Preview */}
                        <div className="text-sm text-gray-700 leading-relaxed bg-white p-3 rounded-lg border border-gray-200 italic line-clamp-2">
                          "{citation.content.slice(0, 200)}{citation.content.length > 200 ? '...' : ''}"
                        </div>

                        {/* View Link */}
                        <div className="mt-2 flex items-center gap-1 text-xs text-blue-600 font-medium">
                          View {citation.source_type === 'pdf' ? 'Document' : 'Video'} <ExternalLink className="w-3 h-3" />
                        </div>
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Empty State */}
      {!result && !loading && (
        <div className="card p-12 text-center">
          <div className="inline-block p-6 bg-gradient-to-br from-blue-100 to-purple-100 rounded-full mb-6">
            <Search className="w-16 h-16 text-blue-600" />
          </div>
          <h3 className="text-2xl font-semibold mb-3 text-gray-800">Search Your Knowledge Base</h3>
          <p className="text-gray-600 max-w-md mx-auto mb-6">
            Ask questions and get answers from all your documents and videos in one unified search.
          </p>

          <div className="max-w-lg mx-auto bg-white rounded-lg shadow-sm border border-gray-200 p-6">
            <p className="text-sm font-semibold text-gray-700 mb-3 text-left">💡 Example queries:</p>
            <ul className="text-sm text-left space-y-3">
              {[
                "What are the main features discussed?",
                "How do I configure authentication?",
                "Explain the deployment process step by step",
              ].map((example, idx) => (
                <li
                  key={idx}
                  onClick={() => setQuery(example)}
                  className="flex items-start gap-3 p-3 bg-gradient-to-r from-blue-50 to-purple-50 rounded-lg hover:from-blue-100 hover:to-purple-100 transition-colors cursor-pointer"
                >
                  <span className="text-blue-600 font-bold text-lg">→</span>
                  <span className="text-gray-700">"{example}"</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}
