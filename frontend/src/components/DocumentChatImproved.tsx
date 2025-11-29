import { useState, useRef, useEffect } from 'react';
import { Send, BookOpen, Loader2, ExternalLink, Copy, Check, RefreshCw, ChevronDown, ChevronUp, Youtube } from 'lucide-react';
import axios from 'axios';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api';

interface Citation {
  chunk_id: string;
  content: string;
  page_number?: number; // Optional for videos
  timestamp?: number; // For videos
  timestamp_formatted?: string; // For videos
  video_url?: string; // For videos
  source_type: 'pdf' | 'youtube'; // New field
  section_id: string | null;
  section_path?: string[];
  similarity_score: number;
  images?: Array<{
    id: string;
    url: string;
    caption?: string;
    page_number: number;
  }>;
  tables?: Array<{
    id: string;
    description?: string;
    markdown: string;
    page_number: number;
  }>;
}

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  citations?: Citation[];
  tokens_used?: number;
}

interface UnifiedChatProps {
  docId?: string; // Optional for unified chat (if not filtering by specific doc)
  documentTitle: string;
  onTimestampClick?: (seconds: number) => void; // For video timestamp navigation
  isVideo?: boolean; // Flag to indicate this is a video document
}

export default function DocumentChatImproved({
  docId,
  documentTitle,
  onTimestampClick,
  isVideo = false
}: UnifiedChatProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [selectedCitation, setSelectedCitation] = useState<Citation | null>(null);
  const [copiedMessageIndex, setCopiedMessageIndex] = useState<number | null>(null);
  const [expandedCitations, setExpandedCitations] = useState<Set<number>>(new Set());
  // When viewing a specific doc/video, ground chat to ONLY that content type
  const [selectedSourceType, setSelectedSourceType] = useState<'all' | 'pdf' | 'youtube'>(
    docId ? (isVideo ? 'youtube' : 'pdf') : 'all'
  );
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleCitationClick = (citation: Citation) => {
    if (citation.source_type === 'pdf' && citation.page_number) {
      // Logic to navigate PDF viewer to page if onPageChange was passed
      // For now, just log or rely on the modal to show context
      console.log(`Navigate to PDF page ${citation.page_number}`);
    } else if (citation.source_type === 'youtube' || isVideo) {
      // Extract timestamp from video_url if available
      let timestamp = citation.timestamp;

      if (!timestamp && citation.video_url) {
        // Parse timestamp from URL like &t=123s or &t=123
        const match = citation.video_url.match(/[&?]t=(\d+)s?/);
        if (match) {
          timestamp = parseInt(match[1]);
        }
      }

      // If we have a timestamp and callback, use it (for side-by-side video chat)
      if (timestamp !== undefined && onTimestampClick) {
        onTimestampClick(timestamp);
      } else if (citation.video_url) {
        // Otherwise open in new tab
        window.open(citation.video_url, '_blank');
      }
    }
    setSelectedCitation(citation);
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = textareaRef.current.scrollHeight + 'px';
    }
  }, [input]);

  const copyToClipboard = async (text: string, index: number) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedMessageIndex(index);
      setTimeout(() => setCopiedMessageIndex(null), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  const toggleCitations = (index: number) => {
    const newExpanded = new Set(expandedCitations);
    if (newExpanded.has(index)) {
      newExpanded.delete(index);
    } else {
      newExpanded.add(index);
    }
    setExpandedCitations(newExpanded);
  };

  const sendMessage = async () => {
    if (!input.trim() || loading) return;

    const userMessage: ChatMessage = {
      role: 'user',
      content: input,
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setLoading(true);

    try {
      const payload: any = {
        question: input,
        chat_history: messages.map(m => ({ role: m.role, content: m.content })),
        top_k_per_source: 5,
        use_images: true,
        use_tables: true,
        context_window: 2,
        source_types: selectedSourceType === 'all' ? ['pdf', 'youtube'] : [selectedSourceType],
      };
      if (docId) {
        payload.doc_ids = [docId];
      }

      const response = await axios.post(`${API_BASE_URL}/chat/unified/`, payload);

      const assistantMessage: ChatMessage = {
        role: 'assistant',
        content: response.data.answer,
        citations: response.data.citations,
        tokens_used: response.data.tokens_used,
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (error) {
      console.error('Failed to send message:', error);
      const errorMessage: ChatMessage = {
        role: 'assistant',
        content: 'Sorry, I encountered an error processing your question. Please try again.',
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  };

  const regenerateResponse = async (messageIndex: number) => {
    const userMessage = messages[messageIndex - 1];
    if (!userMessage || userMessage.role !== 'user') return;

    // Remove the assistant's response
    setMessages((prev) => prev.slice(0, messageIndex));
    setLoading(true);

    try {
      const chatHistory = messages.slice(0, messageIndex - 1);
      const payload: any = {
        question: userMessage.content,
        chat_history: chatHistory.map(m => ({ role: m.role, content: m.content })),
        top_k_per_source: 5,
        use_images: true,
        use_tables: true,
        context_window: 2,
        source_types: selectedSourceType === 'all' ? ['pdf', 'youtube'] : [selectedSourceType],
      };
      if (docId) {
        payload.doc_ids = [docId];
      }

      const response = await axios.post(`${API_BASE_URL}/chat/unified/`, payload);

      const assistantMessage: ChatMessage = {
        role: 'assistant',
        content: response.data.answer,
        citations: response.data.citations,
        tokens_used: response.data.tokens_used,
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (error) {
      console.error('Failed to regenerate:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <div className="flex flex-col h-full bg-gradient-to-b from-gray-50 to-white rounded-lg shadow-lg">
      {/* Header */}
      <div className="bg-gradient-to-r from-blue-600 to-indigo-700 text-white px-6 py-4 rounded-t-lg shadow-md">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-white/10 rounded-lg backdrop-blur-sm">
            {selectedSourceType === 'youtube' ? <Youtube className="w-5 h-5" /> : <BookOpen className="w-5 h-5" />}
          </div>
          <div>
            <h2 className="text-lg font-semibold">Chat with {selectedSourceType === 'youtube' ? 'Video' : 'Content'}</h2>
            <p className="text-sm text-blue-100 mt-0.5 truncate max-w-md">{documentTitle}</p>
          </div>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {messages.length === 0 && (
          <div className="text-center text-gray-500 py-12 px-4">
            <div className="inline-block p-4 bg-blue-50 rounded-full mb-4">
              {selectedSourceType === 'youtube' ? <Youtube className="w-12 h-12 text-blue-500" /> : <BookOpen className="w-12 h-12 text-blue-500" />}
            </div>
            <h3 className="text-xl font-semibold mb-2 text-gray-800">Start a conversation</h3>
            <p className="text-sm text-gray-600 mb-6">Ask questions and get detailed answers with citations from the {selectedSourceType === 'youtube' ? 'video' : 'content'}.</p>
            <div className="max-w-md mx-auto bg-white rounded-lg shadow-sm border border-gray-200 p-6">
              <p className="text-sm font-semibold text-gray-700 mb-3 text-left">💡 Try asking:</p>
              <ul className="text-sm text-left space-y-3">
                <li className="flex items-start gap-3 p-3 bg-blue-50 rounded-lg hover:bg-blue-100 transition-colors cursor-pointer"
                    onClick={() => setInput(`What is the main topic of this ${selectedSourceType === 'youtube' ? 'video' : 'content'}?`)}>
                  <span className="text-blue-600 font-bold text-lg">→</span>
                  <span className="text-gray-700">"What is the main topic of this {selectedSourceType === 'youtube' ? 'video' : 'content'}?"</span>
                </li>
                <li className="flex items-start gap-3 p-3 bg-green-50 rounded-lg hover:bg-green-100 transition-colors cursor-pointer"
                    onClick={() => setInput("Summarize the key findings")}>
                  <span className="text-green-600 font-bold text-lg">→</span>
                  <span className="text-gray-700">"Summarize the key findings"</span>
                </li>
                <li className="flex items-start gap-3 p-3 bg-purple-50 rounded-lg hover:bg-purple-100 transition-colors cursor-pointer"
                    onClick={() => setInput("What are the main components described?")}>
                  <span className="text-purple-600 font-bold text-lg">→</span>
                  <span className="text-gray-700">"What are the main components described?"</span>
                </li>
              </ul>
            </div>
          </div>
        )}

        {messages.map((message, idx) => (
          <div
            key={idx}
            className={`flex gap-3 ${message.role === 'user' ? 'justify-end' : 'justify-start'} animate-fadeIn`}
          >
            {/* Assistant Avatar */}
            {message.role === 'assistant' && (
              <div className="flex-shrink-0 w-10 h-10 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-full flex items-center justify-center text-white font-bold shadow-md">
                AI
              </div>
            )}

            <div
              className={`max-w-3xl rounded-2xl shadow-md ${
                message.role === 'user'
                  ? 'bg-gradient-to-r from-blue-600 to-indigo-600 text-white'
                  : 'bg-white border border-gray-200 text-gray-900'
              }`}
            >
              {/* Message Content */}
              <div className="px-6 py-5">
                {message.role === 'assistant' ? (
                  <div className="prose prose-base max-w-none
                    prose-headings:font-extrabold prose-headings:text-gray-900 prose-headings:mb-4 prose-headings:mt-6 prose-headings:border-b-2 prose-headings:border-blue-200 prose-headings:pb-2
                    prose-h1:text-2xl prose-h2:text-xl prose-h3:text-lg prose-h3:border-b-0
                    prose-p:text-gray-800 prose-p:leading-loose prose-p:mb-4 prose-p:text-base
                    prose-strong:text-gray-900 prose-strong:font-bold prose-strong:bg-yellow-50 prose-strong:px-1
                    prose-ul:text-gray-800 prose-ul:my-4 prose-ul:space-y-2 prose-ol:text-gray-800 prose-ol:my-4 prose-ol:space-y-2
                    prose-li:text-gray-800 prose-li:leading-loose prose-li:text-base
                    prose-a:text-blue-600 prose-a:no-underline hover:prose-a:underline hover:prose-a:text-blue-700
                    prose-code:text-blue-700 prose-code:bg-blue-50 prose-code:px-2 prose-code:py-1 prose-code:rounded prose-code:font-mono prose-code:text-sm prose-code:font-medium
                    prose-pre:bg-gray-900 prose-pre:text-gray-100 prose-pre:p-4 prose-pre:rounded-lg prose-pre:overflow-x-auto prose-pre:my-4
                    prose-blockquote:border-l-4 prose-blockquote:border-blue-500 prose-blockquote:pl-4 prose-blockquote:italic prose-blockquote:text-gray-700 prose-blockquote:my-4
                    prose-table:text-sm prose-table:border-collapse prose-table:my-4
                    prose-th:border prose-th:border-gray-300 prose-th:bg-gray-100 prose-th:px-4 prose-th:py-2 prose-th:font-semibold
                    prose-td:border prose-td:border-gray-300 prose-td:px-4 prose-td:py-2
                    prose-img:rounded-lg prose-img:shadow-md prose-img:my-4">
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      components={{
                        // Render images properly
                        img: ({ node, ...props }) => (
                          <img
                            {...props}
                            className="w-full max-w-md mx-auto rounded-lg shadow-md border border-gray-200 my-4"
                            loading="lazy"
                            onError={(e) => {
                              // Hide broken images gracefully
                              (e.target as HTMLImageElement).style.display = 'none';
                            }}
                          />
                        ),
                        // Make citation numbers clickable
                        a: ({ node, ...props }) => {
                          const text = props.children?.toString() || '';
                          const citationMatch = text.match(/^\[(\d+)\]$/);
                          if (citationMatch && message.citations) {
                                                      const citationIndex = parseInt(citationMatch[1]) - 1;
                                                      const citation = message.citations[citationIndex];
                                                      if (citation) {
                                                        return (
                                                          <button
                                                            onClick={() => handleCitationClick(citation)}
                                                            className="inline-flex items-center px-2.5 py-1 text-sm font-extrabold text-white bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 rounded-full shadow-md hover:shadow-lg transition-all transform hover:-translate-y-0.5 mx-0.5"
                                                            title={`View source (${
                                                              citation.source_type === 'pdf' && citation.page_number
                                                                ? `Page ${citation.page_number}`
                                                                : citation.source_type === 'youtube' && citation.timestamp_formatted
                                                                ? `Video ${citation.timestamp_formatted}`
                                                                : 'Source'
                                                            })`}
                                                          >
                                                            {text}
                                                          </button>
                                                        );
                                                      }                          }
                          return (
                            <a
                              {...props}
                              className="text-blue-600 hover:text-blue-800 underline"
                              target="_blank"
                              rel="noopener noreferrer"
                            />
                          );
                        },
                        // Better code blocks
                        code: ({ node, ...props }) => {
                          // @ts-ignore - inline prop exists but not in types
                          const isInline = props.inline;
                          if (isInline) {
                            return <code {...props} className="px-2 py-0.5 bg-blue-50 text-blue-700 rounded font-mono text-xs" />;
                          }
                          return (
                            <code
                              {...props}
                              className="block p-4 bg-gray-900 text-gray-100 rounded-lg overflow-x-auto font-mono text-sm"
                            />
                          );
                        },
                      }}
                    >
                      {message.content}
                    </ReactMarkdown>
                  </div>
                ) : (
                  <p className="whitespace-pre-wrap text-base leading-relaxed">{message.content}</p>
                )}
              </div>

              {/* Action Buttons (Assistant only) */}
              {message.role === 'assistant' && (
                <div className="px-5 pb-3 flex items-center gap-2 border-t border-gray-100 pt-3">
                  <button
                    onClick={() => copyToClipboard(message.content, idx)}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-gray-600 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                    title="Copy response"
                  >
                    {copiedMessageIndex === idx ? (
                      <>
                        <Check className="w-3.5 h-3.5" />
                        <span>Copied!</span>
                      </>
                    ) : (
                      <>
                        <Copy className="w-3.5 h-3.5" />
                        <span>Copy</span>
                      </>
                    )}
                  </button>
                  <button
                    onClick={() => regenerateResponse(idx)}
                    disabled={loading}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-gray-600 hover:text-green-600 hover:bg-green-50 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    title="Regenerate response"
                  >
                    <RefreshCw className="w-3.5 h-3.5" />
                    <span>Regenerate</span>
                  </button>
                  {message.citations && message.citations.length > 0 && (
                    <button
                      onClick={() => toggleCitations(idx)}
                      className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-gray-600 hover:text-purple-600 hover:bg-purple-50 rounded-lg transition-colors ml-auto"
                    >
                      <BookOpen className="w-3.5 h-3.5" />
                      <span>{message.citations.length} {message.citations.length === 1 ? 'Source' : 'Sources'}</span>
                      {expandedCitations.has(idx) ? (
                        <ChevronUp className="w-3.5 h-3.5" />
                      ) : (
                        <ChevronDown className="w-3.5 h-3.5" />
                      )}
                    </button>
                  )}
                  {message.tokens_used && (
                    <span className="text-xs text-gray-400 ml-2">
                      {message.tokens_used.toLocaleString()} tokens
                    </span>
                  )}
                </div>
              )}

              {/* Citations Section */}
              {message.role === 'assistant' && message.citations && message.citations.length > 0 && expandedCitations.has(idx) && (
                <div className="px-5 pb-4 border-t border-gray-100">
                  <div className="pt-4 space-y-3">
                    {message.citations.map((citation, citIdx) => (
                      <button
                        key={citIdx}
                        onClick={() => handleCitationClick(citation)}
                        className="w-full text-left bg-gradient-to-r from-blue-50 to-indigo-50 hover:from-blue-100 hover:to-indigo-100 rounded-xl border border-blue-200 overflow-hidden transition-all shadow-sm hover:shadow-md"
                      >
                        <div className="p-4">
                          <div className="flex items-start gap-3">
                            <div className="flex-shrink-0 w-8 h-8 bg-gradient-to-br from-blue-600 to-indigo-600 text-white rounded-lg flex items-center justify-center font-bold text-sm shadow-md">
                              {citIdx + 1}
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 flex-wrap mb-2">
                                {citation.source_type === 'pdf' ? (
                                  <span className="inline-flex items-center px-2.5 py-1 bg-blue-600 text-white text-xs font-semibold rounded-full">
                                    📄 Page {citation.page_number}
                                  </span>
                                ) : (
                                  <span className="inline-flex items-center px-2.5 py-1 bg-red-600 text-white text-xs font-semibold rounded-full">
                                    ▶ {citation.timestamp_formatted || `${Math.floor((citation.timestamp || 0) / 60)}:${String(Math.floor((citation.timestamp || 0) % 60)).padStart(2, '0')}`}
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
                              <div className="text-sm text-gray-700 leading-relaxed bg-white p-3 rounded-lg border border-gray-200 italic line-clamp-2">
                                "{citation.content.slice(0, 150)}..."
                              </div>
                              {(citation.images && citation.images.length > 0) || (citation.tables && citation.tables.length > 0) && (
                                <div className="mt-2 flex items-center gap-2 text-xs">
                                  {citation.images && citation.images.length > 0 && (
                                    <span className="inline-flex items-center gap-1 px-2 py-1 bg-green-100 text-green-700 rounded-full font-medium">
                                      📸 {citation.images.length}
                                    </span>
                                  )}
                                  {citation.tables && citation.tables.length > 0 && (
                                    <span className="inline-flex items-center gap-1 px-2 py-1 bg-purple-100 text-purple-700 rounded-full font-medium">
                                      📊 {citation.tables.length}
                                    </span>
                                  )}
                                  <span className="ml-auto flex items-center gap-1 text-blue-600 font-medium">
                                    View <ExternalLink className="w-3 h-3" />
                                  </span>
                                </div>
                              )}
                            </div>
                          </div>
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* User Avatar */}
            {message.role === 'user' && (
              <div className="flex-shrink-0 w-10 h-10 bg-gradient-to-br from-gray-600 to-gray-800 rounded-full flex items-center justify-center text-white font-bold shadow-md">
                U
              </div>
            )}
          </div>
        ))}

        {loading && (
          <div className="flex justify-start gap-3 animate-fadeIn">
            <div className="flex-shrink-0 w-10 h-10 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-full flex items-center justify-center text-white font-bold shadow-md">
              AI
            </div>
            <div className="bg-white border border-gray-200 rounded-2xl px-5 py-4 flex items-center gap-3 shadow-md">
              <Loader2 className="w-5 h-5 animate-spin text-blue-600" />
              <span className="text-sm text-gray-600">Analyzing document...</span>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="border-t border-gray-200 bg-white p-6 rounded-b-lg">
        <div className="flex items-center gap-3 mb-4">
          <div className="text-sm font-medium text-gray-700">Search In:</div>
          <div className="flex rounded-md shadow-sm">
            <button
              onClick={() => setSelectedSourceType('all')}
              className={`px-4 py-2 text-sm font-medium rounded-l-md border ${
                selectedSourceType === 'all'
                  ? 'bg-blue-600 text-white border-blue-600'
                  : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
              }`}
            >
              All
            </button>
            <button
              onClick={() => setSelectedSourceType('pdf')}
              className={`px-4 py-2 text-sm font-medium border-t border-b ${
                selectedSourceType === 'pdf'
                  ? 'bg-blue-600 text-white border-blue-600'
                  : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
              }`}
            >
              PDFs
            </button>
            <button
              onClick={() => setSelectedSourceType('youtube')}
              className={`px-4 py-2 text-sm font-medium rounded-r-md border ${
                selectedSourceType === 'youtube'
                  ? 'bg-blue-600 text-white border-blue-600'
                  : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
              }`}
            >
              Videos
            </button>
          </div>
        </div>

        <div className="flex gap-3">
          <div className="flex-1 relative">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder={`Ask a question about this ${docId ? (selectedSourceType === 'youtube' ? 'video' : 'document') : 'content'}...`}
              className="w-full px-4 py-3 pr-24 border-2 border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none min-h-[50px] max-h-[200px] transition-all"
              rows={1}
              disabled={loading}
            />
            <div className="absolute right-3 bottom-3 text-xs text-gray-400">
              {input.length > 0 && `${input.length} chars`}
            </div>
          </div>
          <button
            onClick={sendMessage}
            disabled={loading || !input.trim()}
            className="px-6 py-3 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white rounded-xl disabled:from-gray-300 disabled:to-gray-400 disabled:cursor-not-allowed flex items-center gap-2 transition-all shadow-md hover:shadow-lg transform hover:-translate-y-0.5 disabled:transform-none disabled:hover:shadow-md"
          >
            {loading ? (
              <Loader2 className="w-5 h-5 animate-spin" />
            ) : (
              <Send className="w-5 h-5" />
            )}
            <span className="font-medium">Send</span>
          </button>
        </div>
        <p className="text-xs text-gray-500 mt-3 flex items-center gap-4">
          <span>💡 Press <kbd className="px-2 py-0.5 bg-gray-100 rounded border border-gray-300">Enter</kbd> to send</span>
          <span>• <kbd className="px-2 py-0.5 bg-gray-100 rounded border border-gray-300">Shift + Enter</kbd> for new line</span>
        </p>
      </div>

      {/* Citation Modal */}
      {selectedCitation && (
        <div
          className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 z-50 animate-fadeIn"
          onClick={() => setSelectedCitation(null)}
        >
          <div
            className="bg-white rounded-2xl max-w-5xl w-full max-h-[90vh] overflow-y-auto shadow-2xl animate-scaleIn"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="bg-gradient-to-r from-blue-600 to-indigo-700 text-white px-8 py-6 sticky top-0 z-10 flex justify-between items-center rounded-t-2xl">
              <div>
                <h3 className="text-2xl font-bold flex items-center gap-2">
                  {selectedCitation?.source_type === 'pdf' ? `📄 Page ${selectedCitation.page_number}` : `▶ ${selectedCitation?.timestamp_formatted}`}
                </h3>
                {selectedCitation?.source_type === 'youtube' && selectedCitation?.video_url && (
                   <a 
                     href={selectedCitation.video_url} 
                     target="_blank" 
                     rel="noopener noreferrer" 
                     className="text-sm text-blue-100 mt-2 flex items-center gap-1 hover:underline"
                   >
                     View Video <ExternalLink className="w-3 h-3" />
                   </a>
                )}
                {selectedCitation?.section_path && selectedCitation.section_path.length > 0 && (
                  <p className="text-sm text-blue-100 mt-2 flex items-center gap-1">
                    📂 {selectedCitation.section_path.join(' › ')}
                  </p>
                )}
              </div>
              <button
                onClick={() => setSelectedCitation(null)}
                className="text-white hover:bg-white/20 rounded-full p-2 transition-colors"
              >
                <span className="text-2xl">×</span>
              </button>
            </div>

            {/* Modal Content */}
            <div className="p-8 space-y-6">
              {/* Citation Text */}
              <div className="bg-yellow-50 border-l-4 border-yellow-500 p-6 rounded-lg shadow-sm">
                <div className="text-xs font-bold text-yellow-800 mb-3 uppercase tracking-wide flex items-center gap-2">
                  <span>📝</span> Citation Content
                </div>
                <div className="text-gray-800 whitespace-pre-wrap leading-relaxed text-base">
                  {selectedCitation?.content}
                </div>
              </div>

              {/* Images */}
              {selectedCitation?.images && selectedCitation.images.length > 0 && (
                <div className="bg-green-50 border-l-4 border-green-500 p-6 rounded-lg shadow-sm">
                  <div className="text-xs font-bold text-green-800 mb-4 uppercase tracking-wide flex items-center gap-2">
                    <span>📸</span> Referenced Images ({selectedCitation.images.length})
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {selectedCitation.images.map((img: any) => (
                      <div key={img.id} className="bg-white border-2 border-green-200 rounded-lg overflow-hidden shadow-md hover:shadow-lg transition-shadow">
                        <img
                          src={img.url}
                          alt={img.caption || 'Document image'}
                          className="w-full h-56 object-contain bg-gray-50"
                          loading="lazy"
                        />
                        {img.caption && (
                          <div className="p-3 bg-white border-t border-green-200">
                            <p className="text-sm text-gray-700 font-medium">{img.caption}</p>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Tables */}
              {selectedCitation?.tables && selectedCitation.tables.length > 0 && (
                <div className="bg-purple-50 border-l-4 border-purple-500 p-6 rounded-lg shadow-sm">
                  <div className="text-xs font-bold text-purple-800 mb-4 uppercase tracking-wide flex items-center gap-2">
                    <span>📊</span> Referenced Tables ({selectedCitation.tables.length})
                  </div>
                  <div className="space-y-4">
                    {selectedCitation.tables.map((table: any) => (
                      <div key={table.id} className="bg-white border-2 border-purple-200 rounded-lg p-4 shadow-md">
                        {table.description && (
                          <p className="text-sm font-semibold text-gray-700 mb-3 pb-3 border-b border-purple-200">{table.description}</p>
                        )}
                        <div className="overflow-x-auto">
                          <div className="prose prose-sm max-w-none prose-table:w-full">
                            <ReactMarkdown remarkPlugins={[remarkGfm]}>
                              {table.markdown}
                            </ReactMarkdown>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Metadata */}
              <div className="flex items-center justify-between pt-6 border-t border-gray-200 text-sm text-gray-500">
                <span className="flex items-center gap-2">
                  <span className="font-semibold text-gray-700">Relevance:</span>
                  <span className="px-3 py-1 bg-green-100 text-green-700 rounded-full font-semibold">
                    {(selectedCitation.similarity_score * 100).toFixed(1)}%
                  </span>
                </span>
                <span className="font-mono text-xs bg-gray-100 px-3 py-1 rounded">
                  {selectedCitation.chunk_id.slice(0, 20)}...
                </span>
              </div>
            </div>
          </div>
        </div>
      )}

      <style>{`
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(10px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @keyframes scaleIn {
          from { opacity: 0; transform: scale(0.95); }
          to { opacity: 1; transform: scale(1); }
        }
        .animate-fadeIn {
          animation: fadeIn 0.3s ease-out;
        }
        .animate-scaleIn {
          animation: scaleIn 0.2s ease-out;
        }

        /* Custom scrollbar styling */
        .overflow-y-auto::-webkit-scrollbar {
          width: 8px;
        }
        .overflow-y-auto::-webkit-scrollbar-track {
          background: #f1f5f9;
          border-radius: 10px;
        }
        .overflow-y-auto::-webkit-scrollbar-thumb {
          background: linear-gradient(to bottom, #3b82f6, #6366f1);
          border-radius: 10px;
          border: 2px solid #f1f5f9;
        }
        .overflow-y-auto::-webkit-scrollbar-thumb:hover {
          background: linear-gradient(to bottom, #2563eb, #4f46e5);
        }

        /* Custom bullet styling for lists */
        .prose ul > li::marker {
          color: #3b82f6;
          font-size: 1.2em;
        }
        .prose ol > li::marker {
          color: #3b82f6;
          font-weight: 700;
        }
      `}</style>
    </div>
  );
}
