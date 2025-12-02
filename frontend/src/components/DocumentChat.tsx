import { useState, useRef, useEffect } from 'react';
import { Send, BookOpen, Loader2, ExternalLink } from 'lucide-react';
import axios from 'axios';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { MarkdownRenderer } from './MarkdownRenderer';

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api';

interface Citation {
  chunk_id: string;
  content: string;
  page_number: number;
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

interface DocumentChatProps {
  docId: string;
  documentTitle: string;
  gdriveLink?: string | null;
  onPageChange?: (page: number) => void;  // Callback to notify parent of page navigation
}

export default function DocumentChat({ docId, documentTitle, onPageChange }: DocumentChatProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [selectedCitation, setSelectedCitation] = useState<Citation | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const handleCitationClick = (citation: Citation) => {
    // Notify parent to change PDF page
    if (onPageChange) {
      onPageChange(citation.page_number);
    }
    // Also show citation modal
    setSelectedCitation(citation);
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

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
      // Use multimodal endpoint for better context and images/tables
      const response = await axios.post(`${API_BASE_URL}/chat/multimodal/`, {
        doc_id: docId,
        question: input,
        chat_history: messages.map(m => ({ role: m.role, content: m.content })),
        top_k: 5,
        use_images: true,
        use_tables: true,
        context_window: 2,
      });

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

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <div className="flex flex-col h-full bg-white rounded-lg shadow-lg">
      {/* Header */}
      <div className="bg-gradient-to-r from-blue-600 to-blue-700 text-white px-6 py-4 rounded-t-lg">
        <div className="flex items-center gap-3">
          <BookOpen className="w-6 h-6" />
          <div>
            <h2 className="text-xl font-semibold">Chat with Document</h2>
            <p className="text-sm text-blue-100 mt-0.5">{documentTitle}</p>
          </div>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        {messages.length === 0 && (
          <div className="text-center text-gray-500 py-12">
            <BookOpen className="w-16 h-16 mx-auto mb-4 text-gray-300" />
            <h3 className="text-lg font-medium mb-2">Start a conversation</h3>
            <p className="text-sm">Ask questions about this document and get answers with citations.</p>
            <div className="mt-6 space-y-2 text-left max-w-md mx-auto">
              <p className="text-sm font-medium text-gray-700">Try asking:</p>
              <ul className="text-sm text-gray-600 space-y-1">
                <li className="flex items-start gap-2">
                  <span className="text-blue-600 mt-0.5">•</span>
                  <span>"What is the main topic of this document?"</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-blue-600 mt-0.5">•</span>
                  <span>"Summarize the key findings"</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-blue-600 mt-0.5">•</span>
                  <span>"What does it say about [specific topic]?"</span>
                </li>
              </ul>
            </div>
          </div>
        )}

        {messages.map((message, idx) => (
          <div
            key={idx}
            className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-3xl rounded-lg px-4 py-3 ${
                message.role === 'user'
                  ? 'bg-blue-600 text-white'
                  : 'bg-white border-2 border-gray-200 text-gray-900'
              }`}
            >
              {message.role === 'assistant' ? (
                <MarkdownRenderer
                  content={message.content}
                  onCitationClick={(index) => {
                    const citation = message.citations?.[index];
                    if (citation) handleCitationClick(citation);
                  }}
                />
              ) : (
                <p className="whitespace-pre-wrap">{message.content}</p>
              )}

              {/* Enhanced Citations */}
              {message.citations && message.citations.length > 0 && (
                <div className="mt-4 pt-4 border-t-2 border-blue-200">
                  <div className="flex items-center gap-2 mb-3">
                    <BookOpen className="w-4 h-4 text-blue-600" />
                    <p className="text-sm font-bold text-gray-800">
                      📚 Sources & References ({message.citations.length})
                    </p>
                  </div>
                  <div className="space-y-3">
                    {message.citations.map((citation, citIdx) => (
                      <div
                        key={citIdx}
                        className="bg-gradient-to-r from-blue-50 to-white rounded-lg border-2 border-blue-200 overflow-hidden hover:shadow-md transition-all"
                      >
                        <button
                          onClick={() => handleCitationClick(citation)}
                          className="text-left w-full p-4 hover:bg-blue-50 transition-all"
                        >
                          <div className="flex items-start gap-3">
                            <div className="flex-shrink-0 w-8 h-8 bg-blue-600 text-white rounded-full flex items-center justify-center font-bold text-sm">
                              {citIdx + 1}
                            </div>
                            <div className="flex-1">
                              <div className="font-bold text-blue-700 mb-1 flex items-center gap-2 flex-wrap">
                                <span>📄 Page {citation.page_number}</span>
                                {citation.section_path && citation.section_path.length > 0 && (
                                  <span className="text-xs text-gray-600 font-normal bg-gray-100 px-2 py-1 rounded">
                                    📂 {citation.section_path[citation.section_path.length - 1]}
                                  </span>
                                )}
                                <span className="text-xs text-green-700 font-normal bg-green-100 px-2 py-1 rounded ml-auto">
                                  {(citation.similarity_score * 100).toFixed(1)}% match
                                </span>
                              </div>
                              <div className="text-gray-700 text-sm line-clamp-3 bg-white p-2 rounded border border-gray-200 italic">
                                "{citation.content.slice(0, 200)}..."
                              </div>
                              <div className="mt-2 flex items-center gap-3 text-xs text-gray-500">
                                {citation.images && citation.images.length > 0 && (
                                  <span className="flex items-center gap-1 bg-green-100 text-green-700 px-2 py-1 rounded">
                                    📸 {citation.images.length} image{citation.images.length > 1 ? 's' : ''}
                                  </span>
                                )}
                                {citation.tables && citation.tables.length > 0 && (
                                  <span className="flex items-center gap-1 bg-purple-100 text-purple-700 px-2 py-1 rounded">
                                    📊 {citation.tables.length} table{citation.tables.length > 1 ? 's' : ''}
                                  </span>
                                )}
                                <span className="ml-auto flex items-center gap-1 text-blue-600 font-medium">
                                  Click to view full context <ExternalLink className="w-3 h-3" />
                                </span>
                              </div>
                            </div>
                          </div>
                        </button>

                        {/* Preview Images */}
                        {citation.images && citation.images.length > 0 && (
                          <div className="px-4 pb-3 bg-green-50 border-t border-green-200">
                            <div className="grid grid-cols-3 gap-2 mt-2">
                              {citation.images.slice(0, 3).map((img: any) => (
                                <div
                                  key={img.id}
                                  className="border-2 border-green-300 rounded overflow-hidden bg-white cursor-pointer hover:scale-105 transition-transform"
                                  onClick={() => handleCitationClick(citation)}
                                >
                                  <img
                                    src={img.url}
                                    alt={img.caption || 'Document image'}
                                    className="w-full h-20 object-cover"
                                    loading="lazy"
                                  />
                                </div>
                              ))}
                            </div>
                            {citation.images.length > 3 && (
                              <p className="text-xs text-green-700 mt-1 text-center">
                                +{citation.images.length - 3} more image{citation.images.length - 3 > 1 ? 's' : ''} (click to view all)
                              </p>
                            )}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Token usage */}
              {message.tokens_used && (
                <div className="mt-2 text-xs text-gray-500">
                  {message.tokens_used} tokens used
                </div>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="bg-gray-100 rounded-lg px-4 py-3 flex items-center gap-2">
              <Loader2 className="w-4 h-4 animate-spin text-blue-600" />
              <span className="text-sm text-gray-600">Searching document...</span>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="border-t border-gray-200 p-4 bg-gray-50 rounded-b-lg">
        <div className="flex gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Ask a question about this document..."
            className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
            rows={2}
            disabled={loading}
          />
          <button
            onClick={sendMessage}
            disabled={loading || !input.trim()}
            className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed flex items-center gap-2 transition-colors"
          >
            {loading ? (
              <Loader2 className="w-5 h-5 animate-spin" />
            ) : (
              <Send className="w-5 h-5" />
            )}
          </button>
        </div>
        <p className="text-xs text-gray-500 mt-2">
          Press Enter to send, Shift+Enter for new line
        </p>
      </div>

      {/* Enhanced Citation Modal */}
      {selectedCitation && (
        <div
          className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50"
          onClick={() => setSelectedCitation(null)}
        >
          <div
            className="bg-white rounded-lg max-w-4xl w-full max-h-[90vh] overflow-y-auto shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="bg-blue-600 text-white px-6 py-4 sticky top-0 z-10 flex justify-between items-center">
              <div>
                <h3 className="text-xl font-semibold">
                  📄 Page {selectedCitation.page_number}
                </h3>
                {selectedCitation.section_path && selectedCitation.section_path.length > 0 && (
                  <p className="text-sm text-blue-100 mt-1">
                    📂 {selectedCitation.section_path.join(' › ')}
                  </p>
                )}
              </div>
              <button
                onClick={() => setSelectedCitation(null)}
                className="text-white hover:bg-blue-700 rounded-full p-2 transition-colors"
              >
                ✕
              </button>
            </div>

            {/* Content Section */}
            <div className="p-6 space-y-4">
              {/* Main Citation Text */}
              <div className="bg-yellow-50 border-l-4 border-yellow-400 p-4 rounded">
                <div className="text-xs font-semibold text-yellow-800 mb-2 uppercase">Citation Content</div>
                <div className="text-gray-800 whitespace-pre-wrap leading-relaxed">
                  {selectedCitation.content}
                </div>
              </div>

              {/* Images */}
              {selectedCitation.images && selectedCitation.images.length > 0 && (
                <div className="bg-green-50 border-l-4 border-green-400 p-4 rounded">
                  <div className="text-xs font-semibold text-green-800 mb-3 uppercase">
                    📸 Referenced Images ({selectedCitation.images.length})
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {selectedCitation.images.map((img: any) => (
                      <div key={img.id} className="bg-white border rounded-lg overflow-hidden shadow-sm">
                        <img
                          src={img.url}
                          alt={img.caption || 'Document image'}
                          className="w-full h-48 object-contain bg-gray-50"
                          loading="lazy"
                        />
                        {img.caption && (
                          <div className="p-2 bg-white border-t">
                            <p className="text-xs text-gray-700 font-medium">{img.caption}</p>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Tables */}
              {selectedCitation.tables && selectedCitation.tables.length > 0 && (
                <div className="bg-purple-50 border-l-4 border-purple-400 p-4 rounded">
                  <div className="text-xs font-semibold text-purple-800 mb-3 uppercase">
                    📊 Referenced Tables ({selectedCitation.tables.length})
                  </div>
                  <div className="space-y-3">
                    {selectedCitation.tables.map((table: any) => (
                      <div key={table.id} className="bg-white border rounded p-3">
                        {table.description && (
                          <p className="text-sm font-medium text-gray-700 mb-2">{table.description}</p>
                        )}
                        <div className="overflow-x-auto">
                          <div className="prose prose-sm max-w-none">
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

              {/* Metadata Footer */}
              <div className="flex items-center justify-between pt-4 border-t text-xs text-gray-500">
                <span>Relevance Score: {(selectedCitation.similarity_score * 100).toFixed(1)}%</span>
                <span>Chunk ID: {selectedCitation.chunk_id.slice(0, 16)}...</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
