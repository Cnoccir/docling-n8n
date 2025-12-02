import { useState, useRef, useEffect } from 'react';
import { Search, FileText, Youtube, Loader2, ExternalLink, Play, Image as ImageIcon, Trash2, X, DollarSign, Settings, ChevronDown, ChevronUp } from 'lucide-react';
import { MarkdownRenderer } from '@/components/MarkdownRenderer';
import { unifiedChatApi } from '@/services/api';

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
  thumbnail_url?: string;
  caption?: string;
  image_type?: string;
  page_number?: number;
  timestamp?: number;
  relevance_score?: number;
  source_document?: string;
}

// SearchResult interface kept for reference but not used directly
// The API response type is defined in api.ts

interface Message {
  role: 'user' | 'assistant';
  content: string;
  citations?: Citation[];
  related_images?: RelatedImage[];
  model_used?: string;
  tokens_used?: number;
  total_sources_found?: number;
  follow_up_suggestions?: string[];
}

export default function UnifiedSearch() {
  const [query, setQuery] = useState('');
  const [searchPDFs, setSearchPDFs] = useState(true);
  const [searchVideos, setSearchVideos] = useState(true);
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [selectedModel, setSelectedModel] = useState<'gpt-4o-mini' | 'gpt-4o'>('gpt-4o-mini');
  const [sessionTokens, setSessionTokens] = useState(0);
  const [selectedImage, setSelectedImage] = useState<RelatedImage | null>(null);
  const [expandedCitations, setExpandedCitations] = useState<Set<number>>(new Set());
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Estimate cost based on tokens (rough estimate)
  const estimatedCost = (sessionTokens / 1000) * (selectedModel === 'gpt-4o' ? 0.005 : 0.00015);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSearch = async () => {
    if (!query.trim()) {
      setError('Please enter a search query');
      return;
    }

    if (!searchPDFs && !searchVideos) {
      setError('Please select at least one source type');
      return;
    }

    // Add user message
    const userMessage: Message = {
      role: 'user',
      content: query,
    };
    setMessages((prev) => [...prev, userMessage]);
    setQuery('');
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

      // Build chat history for follow-up context
      const chat_history = messages.map(m => ({
        role: m.role,
        content: m.content,
      }));

      const response = await unifiedChatApi.chat({
        question: query,
        source_types,
        top_k_per_source: 5,
        use_images: true,
        chat_history,
      });

      // Add assistant message
      const assistantMessage: Message = {
        role: 'assistant',
        content: response.answer,
        citations: response.citations,
        related_images: response.related_images,
        model_used: response.model_used,
        tokens_used: response.tokens_used,
        total_sources_found: response.total_sources_found,
        follow_up_suggestions: response.follow_up_suggestions || [],
      };
      setMessages((prev) => [...prev, assistantMessage]);
      
      // Track session tokens
      setSessionTokens(prev => prev + (response.tokens_used || 0));
    } catch (err: any) {
      console.error('Search failed:', err);
      setError(err.response?.data?.detail || err.message || 'Search failed');
      const errorMessage: Message = {
        role: 'assistant',
        content: 'Sorry, I encountered an error processing your search. Please try again.',
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  };

  const handleClearConversation = () => {
    setMessages([]);
    setError(null);
    setSessionTokens(0);
  };

  const handleCitationClick = (citation: Citation) => {
    // Open in new tab to preserve conversation
    if (citation.source_type === 'pdf') {
      window.open(`/documents/${citation.doc_id}`, '_blank');
    } else if (citation.source_type === 'youtube') {
      if (citation.video_url) {
        window.open(citation.video_url, '_blank');
      } else {
        window.open(`/videos/${citation.doc_id}`, '_blank');
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
          AME TechAssist
        </h1>
        <p className="text-gray-600 text-lg">
          Your technical expert • Implementation guidance from {messages.length > 0 ? 'your conversation' : 'all ingested documents & videos'}
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

          {messages.length > 0 && (
            <button
              onClick={handleClearConversation}
              disabled={loading}
              className="px-4 py-3 bg-red-100 text-red-700 font-semibold rounded-lg hover:bg-red-200 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 transition-all"
              title="Clear conversation"
            >
              <Trash2 className="w-5 h-5" />
            </button>
          )}
        </div>

        {/* Source Type Filters + Model Selection + Cost */}
        <div className="flex items-center justify-between flex-wrap gap-4">
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
              <span className="text-sm text-gray-700">Documents</span>
            </label>

            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={searchVideos}
                onChange={(e) => setSearchVideos(e.target.checked)}
                className="w-4 h-4 text-red-600 rounded focus:ring-2 focus:ring-red-500"
              />
              <Youtube className="w-4 h-4 text-red-600" />
              <span className="text-sm text-gray-700">Videos</span>
            </label>
          </div>

          <div className="flex items-center gap-4">
            {/* Model Selector */}
            <div className="flex items-center gap-2">
              <Settings className="w-4 h-4 text-gray-500" />
              <select
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value as 'gpt-4o-mini' | 'gpt-4o')}
                className="text-sm border border-gray-300 rounded-lg px-2 py-1 focus:ring-2 focus:ring-blue-500"
              >
                <option value="gpt-4o-mini">GPT-4o Mini (Fast)</option>
                <option value="gpt-4o">GPT-4o (Best)</option>
              </select>
            </div>

            {/* Session Cost */}
            {sessionTokens > 0 && (
              <div className="flex items-center gap-1 text-xs text-gray-500 bg-gray-100 px-2 py-1 rounded-full">
                <DollarSign className="w-3 h-3" />
                <span>{sessionTokens.toLocaleString()} tokens • ~${estimatedCost.toFixed(4)}</span>
              </div>
            )}
          </div>
        </div>

        {/* Error Message */}
        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
            {error}
          </div>
        )}
      </div>

      {/* Message Thread */}
      {messages.length > 0 && (
        <div className="card p-6">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-xl font-semibold text-gray-900">Conversation</h2>
            <button
              onClick={handleClearConversation}
              className="text-sm text-red-600 hover:text-red-800 flex items-center gap-1 transition-colors"
            >
              <Trash2 className="w-4 h-4" />
              Clear
            </button>
          </div>

          <div className="space-y-6">
            {messages.map((message, idx) => (
              <div key={idx} className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div className={`max-w-4xl w-full ${message.role === 'user' ? 'flex justify-end' : ''}`}>
                  {message.role === 'user' ? (
                    <div className="bg-gradient-to-r from-blue-600 to-purple-600 text-white rounded-lg px-4 py-3 max-w-2xl">
                      <p className="whitespace-pre-wrap">{message.content}</p>
                    </div>
                  ) : (
                    <div className="bg-white border-2 border-gray-200 rounded-lg p-6 w-full">
                      {/* Metadata */}
                      {(message.model_used || message.tokens_used || message.total_sources_found) && (
                        <div className="flex items-center gap-4 text-xs text-gray-500 mb-4 pb-4 border-b">
                          {message.model_used && <span>Model: {message.model_used}</span>}
                          {message.tokens_used && (
                            <>
                              <span>•</span>
                              <span>{message.tokens_used.toLocaleString()} tokens</span>
                            </>
                          )}
                          {message.total_sources_found !== undefined && (
                            <>
                              <span>•</span>
                              <span>{message.total_sources_found} sources found</span>
                            </>
                          )}
                        </div>
                      )}

                      {/* Answer */}
                      <MarkdownRenderer content={message.content} />

                      {/* Related Images */}
                      {message.related_images && message.related_images.length > 0 && (
                        <div className="mt-8 border-t pt-6">
                          <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
                            <ImageIcon className="w-5 h-5 text-blue-600" />
                            Related Visual Content ({message.related_images.length})
                          </h3>
                          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                            {message.related_images.map((image, imgIdx) => (
                              <button
                                key={imgIdx}
                                onClick={() => setSelectedImage(image)}
                                className="border border-gray-200 rounded-lg overflow-hidden hover:shadow-lg transition-shadow bg-white text-left cursor-pointer"
                              >
                                <div className="aspect-video bg-gray-100 relative overflow-hidden">
                                  <img
                                    src={image.url}
                                    alt={image.caption || `Related image ${imgIdx + 1}`}
                                    className="w-full h-full object-contain hover:scale-105 transition-transform duration-200"
                                    loading="lazy"
                                  />
                                  <div className="absolute inset-0 bg-black bg-opacity-0 hover:bg-opacity-10 transition-all flex items-center justify-center">
                                    <span className="text-white opacity-0 hover:opacity-100 text-sm font-medium bg-black bg-opacity-50 px-2 py-1 rounded">Click to enlarge</span>
                                  </div>
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
                              </button>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Citations Section - Collapsible */}
                      {message.citations && message.citations.length > 0 && (
                        <div className="mt-6 border-t pt-4">
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              setExpandedCitations(prev => {
                                const next = new Set(prev);
                                if (next.has(idx)) {
                                  next.delete(idx);
                                } else {
                                  next.add(idx);
                                }
                                return next;
                              });
                            }}
                            className="w-full flex items-center justify-between text-left hover:bg-gray-50 rounded-lg p-2 -m-2 transition-colors"
                          >
                            <h3 className="text-sm font-semibold text-gray-700">
                              📚 Sources ({message.citations.length})
                            </h3>
                            {expandedCitations.has(idx) ? (
                              <ChevronUp className="w-4 h-4 text-gray-500" />
                            ) : (
                              <ChevronDown className="w-4 h-4 text-gray-500" />
                            )}
                          </button>

                          {/* Collapsed View - Show first 2 as compact cards */}
                          {!expandedCitations.has(idx) && (
                            <div className="mt-3 space-y-2">
                              {message.citations.slice(0, 2).map((citation, citIdx) => (
                                <button
                                  key={citIdx}
                                  onClick={() => handleCitationClick(citation)}
                                  className="w-full text-left bg-gray-50 hover:bg-gray-100 rounded-lg border border-gray-200 p-3 transition-all flex items-center gap-3"
                                >
                                  <div className="flex-shrink-0 w-8 h-8 bg-gradient-to-br from-blue-600 to-purple-600 text-white rounded-lg flex items-center justify-center font-bold text-xs">
                                    {citIdx + 1}
                                  </div>
                                  <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2">
                                      <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${citation.source_type === 'pdf' ? 'bg-blue-100 text-blue-700' : 'bg-red-100 text-red-700'}`}>
                                        {citation.source_type === 'pdf' ? `Page ${citation.page_number}` : citation.timestamp_formatted || formatTimestamp(citation.timestamp || 0)}
                                      </span>
                                      <span className="text-xs text-green-600 font-medium">
                                        {(citation.similarity_score * 100).toFixed(0)}%
                                      </span>
                                    </div>
                                    <p className="text-sm text-gray-900 font-medium truncate mt-1">{citation.doc_title}</p>
                                  </div>
                                  <ExternalLink className="w-4 h-4 text-gray-400 flex-shrink-0" />
                                </button>
                              ))}
                              {message.citations.length > 2 && (
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setExpandedCitations(prev => new Set(prev).add(idx));
                                  }}
                                  className="w-full text-center text-sm text-blue-600 hover:text-blue-800 py-2"
                                >
                                  + {message.citations.length - 2} more sources
                                </button>
                              )}
                            </div>
                          )}

                          {/* Expanded View - Full citation cards */}
                          {expandedCitations.has(idx) && (
                            <div className="mt-3 space-y-3">
                              {message.citations.map((citation, citIdx) => (
                                <button
                                  key={citIdx}
                                  onClick={() => handleCitationClick(citation)}
                                  className="w-full text-left bg-gradient-to-r from-gray-50 to-blue-50 hover:from-gray-100 hover:to-blue-100 rounded-xl border border-gray-200 overflow-hidden transition-all shadow-sm hover:shadow-md p-4"
                                >
                                  <div className="flex items-start gap-4">
                                    {/* Citation Number */}
                                    <div className="flex-shrink-0 w-10 h-10 bg-gradient-to-br from-blue-600 to-purple-600 text-white rounded-lg flex items-center justify-center font-bold text-sm shadow-md">
                                      {citIdx + 1}
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
                                          <span className="inline-flex items-center px-2.5 py-1 bg-blue-600 text-white text-xs font-semibold rounded-full">
                                            📄 Page {citation.page_number}
                                          </span>
                                        ) : (
                                          <span className="inline-flex items-center px-2.5 py-1 bg-red-600 text-white text-xs font-semibold rounded-full">
                                            ▶ {citation.timestamp_formatted || formatTimestamp(citation.timestamp || 0)}
                                          </span>
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
                                      <h4 className="font-semibold text-gray-900 mb-2">
                                        {citation.doc_title}
                                      </h4>

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
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))}

            {/* Follow-up Suggestions (after last assistant message) */}
            {!loading && messages.length > 0 && messages[messages.length - 1].role === 'assistant' && messages[messages.length - 1].follow_up_suggestions && messages[messages.length - 1].follow_up_suggestions!.length > 0 && (
              <div className="flex flex-wrap gap-2 mt-4">
                <span className="text-sm text-gray-500 mr-2">Follow up:</span>
                {messages[messages.length - 1].follow_up_suggestions!.map((suggestion, idx) => (
                  <button
                    key={idx}
                    onClick={() => {
                      setQuery(suggestion);
                      // Auto-submit after a brief delay
                      setTimeout(() => {
                        const event = new KeyboardEvent('keypress', { key: 'Enter' });
                        document.querySelector('input')?.dispatchEvent(event);
                      }, 100);
                    }}
                    className="px-3 py-1.5 bg-blue-50 hover:bg-blue-100 text-blue-700 text-sm rounded-full border border-blue-200 transition-colors"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            )}

            {/* Loading State */}
            {loading && (
              <div className="flex justify-start">
                <div className="bg-gradient-to-r from-blue-50 to-purple-50 rounded-lg px-4 py-3 flex items-center gap-3 border border-blue-200">
                  <Loader2 className="w-5 h-5 animate-spin text-blue-600" />
                  <span className="text-sm text-gray-700">Expert is analyzing your question...</span>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>
        </div>
      )}

      {/* Empty State - Expert Persona */}
      {messages.length === 0 && !loading && (
        <div className="card p-12">
          <div className="max-w-2xl mx-auto text-center">
            {/* Expert Avatar */}
            <div className="inline-flex items-center justify-center w-20 h-20 bg-gradient-to-br from-blue-600 to-purple-600 rounded-full mb-6 shadow-lg">
              <span className="text-4xl">🎓</span>
            </div>
            
            <h2 className="text-3xl font-bold text-gray-900 mb-3">AME Technical Expert</h2>
            <p className="text-lg text-gray-600 mb-8">
              I'm your BAS/HVAC technical guide. I provide <strong>implementation-level guidance</strong> with exact steps, not just overviews.
            </p>

            {/* Capabilities */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8 text-left">
              <div className="bg-blue-50 rounded-lg p-4 border border-blue-200">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-xl">🛠️</span>
                  <h4 className="font-semibold text-gray-900">Configuration & Setup</h4>
                </div>
                <p className="text-sm text-gray-600">Step-by-step procedures with exact navigation paths and settings</p>
              </div>
              <div className="bg-green-50 rounded-lg p-4 border border-green-200">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-xl">🔧</span>
                  <h4 className="font-semibold text-gray-900">Troubleshooting</h4>
                </div>
                <p className="text-sm text-gray-600">Diagnostic procedures, root cause analysis, and verified solutions</p>
              </div>
              <div className="bg-purple-50 rounded-lg p-4 border border-purple-200">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-xl">🏗️</span>
                  <h4 className="font-semibold text-gray-900">Architecture & Design</h4>
                </div>
                <p className="text-sm text-gray-600">System design guidance, trade-offs, and best practices</p>
              </div>
              <div className="bg-orange-50 rounded-lg p-4 border border-orange-200">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-xl">📚</span>
                  <h4 className="font-semibold text-gray-900">Deep Knowledge</h4>
                </div>
                <p className="text-sm text-gray-600">Answers grounded in your ingested PDFs and training videos</p>
              </div>
            </div>

            {/* Example Queries */}
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
              <p className="text-sm font-semibold text-gray-700 mb-4 text-left">Try asking:</p>
              <div className="grid grid-cols-1 gap-2">
                {[
                  "How do I set up a master supervisor with building-level supervisors?",
                  "Explain System Database and how stations sync",
                  "What's the step-by-step process to configure multi-tier architecture?",
                  "Troubleshoot: graphics not updating between buildings",
                ].map((example, idx) => (
                  <button
                    key={idx}
                    onClick={() => setQuery(example)}
                    className="flex items-center gap-3 p-3 bg-gradient-to-r from-gray-50 to-blue-50 rounded-lg hover:from-blue-100 hover:to-purple-100 transition-colors text-left"
                  >
                    <span className="text-blue-600 font-bold">→</span>
                    <span className="text-gray-700 text-sm">{example}</span>
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Image Modal */}
      {selectedImage && (
        <div 
          className="fixed inset-0 bg-black bg-opacity-75 flex items-center justify-center z-50 p-4"
          onClick={() => setSelectedImage(null)}
        >
          <div 
            className="bg-white rounded-lg max-w-4xl max-h-[90vh] overflow-auto shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="flex items-center justify-between p-4 border-b border-gray-200">
              <h3 className="font-semibold text-gray-900">Image Details</h3>
              <button
                onClick={() => setSelectedImage(null)}
                className="p-1 hover:bg-gray-100 rounded-full transition-colors"
              >
                <X className="w-5 h-5 text-gray-500" />
              </button>
            </div>
            
            {/* Image */}
            <div className="p-4 bg-gray-50">
              <img
                src={selectedImage.url || selectedImage.thumbnail_url}
                alt={selectedImage.caption || 'Image'}
                className="max-w-full h-auto mx-auto rounded"
              />
            </div>
            
            {/* Metadata */}
            <div className="p-4 space-y-3">
              {selectedImage.caption && (
                <div>
                  <span className="text-xs font-semibold text-gray-500 uppercase">Caption</span>
                  <p className="text-gray-900">{selectedImage.caption}</p>
                </div>
              )}
              
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {selectedImage.image_type && (
                  <div>
                    <span className="text-xs font-semibold text-gray-500 uppercase">Type</span>
                    <p className="text-gray-900 capitalize">{selectedImage.image_type}</p>
                  </div>
                )}
                {selectedImage.page_number && (
                  <div>
                    <span className="text-xs font-semibold text-gray-500 uppercase">Page</span>
                    <p className="text-gray-900">{selectedImage.page_number}</p>
                  </div>
                )}
                {selectedImage.timestamp && (
                  <div>
                    <span className="text-xs font-semibold text-gray-500 uppercase">Timestamp</span>
                    <p className="text-gray-900">{selectedImage.timestamp}</p>
                  </div>
                )}
                {selectedImage.relevance_score && (
                  <div>
                    <span className="text-xs font-semibold text-gray-500 uppercase">Relevance</span>
                    <p className="text-gray-900">{(selectedImage.relevance_score * 100).toFixed(0)}%</p>
                  </div>
                )}
              </div>
              
              {selectedImage.source_document && (
                <div>
                  <span className="text-xs font-semibold text-gray-500 uppercase">Source</span>
                  <p className="text-gray-900 text-sm truncate">{selectedImage.source_document}</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
