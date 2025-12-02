import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';

interface MarkdownRendererProps {
  content: string;
  onCitationClick?: (index: number) => void;
}

/**
 * Reusable markdown renderer with consistent styling across all chat interfaces.
 * Supports: headings, lists, code blocks, tables, citations, images, blockquotes.
 */
export function MarkdownRenderer({ content, onCitationClick }: MarkdownRendererProps) {
  return (
    <div className="markdown-content">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // Headings with proper spacing and hierarchy
          h1: ({ children }) => (
            <h1 className="text-3xl font-bold text-gray-900 mt-8 mb-4 pb-3 border-b-2 border-blue-200">
              {children}
            </h1>
          ),
          h2: ({ children }) => (
            <h2 className="text-2xl font-bold text-gray-900 mt-6 mb-3 pb-2 border-b border-gray-200">
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3 className="text-xl font-semibold text-gray-800 mt-5 mb-2">
              {children}
            </h3>
          ),
          h4: ({ children }) => (
            <h4 className="text-lg font-semibold text-gray-800 mt-4 mb-2">
              {children}
            </h4>
          ),

          // Paragraphs with proper spacing
          p: ({ children }) => (
            <p className="text-gray-800 leading-relaxed my-4">
              {children}
            </p>
          ),

          // Lists with better styling
          ul: ({ children }) => (
            <ul className="list-disc list-outside ml-6 space-y-2 my-4 text-gray-800">
              {children}
            </ul>
          ),
          ol: ({ children }) => (
            <ol className="list-decimal list-outside ml-6 space-y-2 my-4 text-gray-800">
              {children}
            </ol>
          ),
          li: ({ children }) => (
            <li className="text-gray-800 leading-relaxed pl-2">
              {children}
            </li>
          ),

          // Code blocks with syntax highlighting
          code({ className, children }: any) {
            const match = /language-(\w+)/.exec(className || '');
            const inline = !match;

            return !inline ? (
              <SyntaxHighlighter
                style={vscDarkPlus as any}
                language={match[1]}
                PreTag="div"
                className="rounded-lg my-4 shadow-md"
              >
                {String(children).replace(/\n$/, '')}
              </SyntaxHighlighter>
            ) : (
              <code className="bg-blue-50 text-blue-700 px-2 py-0.5 rounded font-mono text-sm font-semibold">
                {children}
              </code>
            );
          },

          // Tables with full styling
          table: ({ children }) => (
            <div className="overflow-x-auto my-6 shadow-md rounded-lg">
              <table className="min-w-full border-collapse border border-gray-300">
                {children}
              </table>
            </div>
          ),
          thead: ({ children }) => (
            <thead className="bg-gray-100">{children}</thead>
          ),
          tbody: ({ children }) => (
            <tbody className="bg-white">{children}</tbody>
          ),
          tr: ({ children }) => (
            <tr className="border-b border-gray-300 hover:bg-gray-50 transition-colors">
              {children}
            </tr>
          ),
          th: ({ children }) => (
            <th className="border border-gray-300 px-4 py-3 text-left font-semibold text-gray-900">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="border border-gray-300 px-4 py-3 text-gray-800">
              {children}
            </td>
          ),

          // Blockquotes
          blockquote: ({ children }) => (
            <blockquote className="border-l-4 border-blue-500 pl-4 py-2 my-4 bg-blue-50 italic text-gray-700">
              {children}
            </blockquote>
          ),

          // Strong/Bold
          strong: ({ children }) => (
            <strong className="font-bold text-gray-900">
              {children}
            </strong>
          ),

          // Emphasis/Italic
          em: ({ children }) => (
            <em className="italic text-gray-800">
              {children}
            </em>
          ),

          // Links - with special handling for citations
          a: ({ href, children }) => {
            const text = children?.toString() || '';
            const citationMatch = text.match(/^\[(\d+)\]$/);

            // If it's a citation like [1], [2], make it clickable
            if (citationMatch && onCitationClick) {
              const index = parseInt(citationMatch[1]) - 1;
              return (
                <button
                  onClick={() => onCitationClick(index)}
                  className="inline-flex items-center text-blue-600 hover:text-blue-800 font-semibold underline mx-0.5 transition-colors"
                  title={`View source ${citationMatch[1]}`}
                >
                  {text}
                </button>
              );
            }

            // Regular links
            return (
              <a
                href={href}
                className="text-blue-600 hover:text-blue-800 underline transition-colors"
                target="_blank"
                rel="noopener noreferrer"
              >
                {children}
              </a>
            );
          },

          // Horizontal rules
          hr: () => (
            <hr className="my-8 border-t-2 border-gray-200" />
          ),

          // Images embedded in markdown
          img: ({ src, alt }) => (
            <div className="my-6">
              <img
                src={src}
                alt={alt || ''}
                className="rounded-lg shadow-lg max-w-full h-auto"
                loading="lazy"
              />
              {alt && (
                <p className="text-sm text-gray-600 mt-2 text-center italic">
                  {alt}
                </p>
              )}
            </div>
          ),

          // Preformatted text (for non-code blocks)
          pre: ({ children }) => (
            <pre className="bg-gray-100 border border-gray-300 rounded p-4 overflow-x-auto my-4 text-sm">
              {children}
            </pre>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
