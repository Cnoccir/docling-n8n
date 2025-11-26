import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, FileText, Image as ImageIcon, Table, ChevronRight, ChevronDown, Eye, ExternalLink, MessageSquare } from 'lucide-react';
import { documentsApi } from '@/services/api';
import type { Document } from '@/types';
import { formatNumber, formatRelativeTime, getStatusBadgeClass } from '@/utils/format';
import DocumentChatImproved from '@/components/DocumentChatImproved';

interface Section {
  id: string;
  title: string;
  level: number;
  start_page: number;
  end_page: number;
  chunk_ids: string[];
  child_section_ids: string[];
  parent_section_id: string | null;
  metadata: {
    chunk_count: number;
    chunk_range: number[];
    chunk_start: string;
    chunk_end: string;
    section_path: string[];
    section_number: string | null;
  };
}

interface Chunk {
  id: string;
  content: string;
  page_number: number;
  bbox?: any;
  metadata?: any;
}

interface ImageData {
  id: string;
  page_number: number;
  s3_url: string;
  caption: string | null;
  image_type: string | null;
  basic_summary: string | null;
}

interface TableData {
  id: string;
  page_number: number;
  markdown: string;
  description: string | null;
  key_insights: string[] | null;
}

interface HierarchyData {
  doc_id: string;
  hierarchy: {
    pages?: any[];
    sections?: Section[];
  };
  page_index?: any;
  asset_index?: any;
}

export default function DocumentDetail() {
  const { docId } = useParams<{ docId: string }>();
  const navigate = useNavigate();
  
  const [document, setDocument] = useState<Document | null>(null);
  const [hierarchy, setHierarchy] = useState<HierarchyData | null>(null);
  const [chunks, setChunks] = useState<Chunk[]>([]);
  const [images, setImages] = useState<ImageData[]>([]);
  const [tables, setTables] = useState<TableData[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'overview' | 'chat' | 'preview' | 'hierarchy' | 'chunks' | 'images' | 'tables'>('overview');
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (docId) {
      fetchDocumentData();
    }
  }, [docId]);

  async function fetchDocumentData() {
    try {
      setLoading(true);
      
      // Fetch document details
      const doc = await documentsApi.get(docId!);
      setDocument(doc);

      // Fetch hierarchy
      try {
        const hierarchyData = await fetch(`/api/documents/${docId}/hierarchy`).then(r => r.json());
        setHierarchy(hierarchyData);
      } catch (e) {
        console.error('Failed to fetch hierarchy:', e);
      }

      // Fetch chunks
      try {
        const chunksData = await fetch(`/api/documents/${docId}/chunks?limit=200`).then(r => r.json());
        setChunks(chunksData.chunks || []);
      } catch (e) {
        console.error('Failed to fetch chunks:', e);
      }

      // Fetch images
      try {
        const imagesData = await documentsApi.getImages(docId!);
        setImages(imagesData);
      } catch (e) {
        console.error('Failed to fetch images:', e);
      }

      // Fetch tables
      try {
        const tablesData = await documentsApi.getTables(docId!);
        setTables(tablesData);
      } catch (e) {
        console.error('Failed to fetch tables:', e);
      }

    } catch (error) {
      console.error('Failed to fetch document:', error);
    } finally {
      setLoading(false);
    }
  }

  const toggleSection = (sectionId: string) => {
    setExpandedSections(prev => {
      const next = new Set(prev);
      if (next.has(sectionId)) {
        next.delete(sectionId);
      } else {
        next.add(sectionId);
      }
      return next;
    });
  };

  const renderSection = (section: Section, _index: number, depth: number = 0) => {
    const sectionId = section.id;
    const isExpanded = expandedSections.has(sectionId);

    // Get images and tables for this section from asset_index
    const sectionImages = hierarchy?.asset_index?.images
      ? Object.entries(hierarchy.asset_index.images)
          .filter(([_, asset]: [string, any]) => asset.section_id === section.id)
          .map(([imageId, asset]: [string, any]) => ({
            id: imageId,
            page: asset.page_number || 0
          }))
      : [];

    const sectionTables = hierarchy?.asset_index?.tables
      ? Object.entries(hierarchy.asset_index.tables)
          .filter(([_, asset]: [string, any]) => asset.section_id === section.id)
          .map(([tableId, asset]: [string, any]) => ({
            id: tableId,
            page: asset.page_number || 0
          }))
      : [];

    const hasContent = section.chunk_ids.length > 0 || sectionImages.length > 0 || sectionTables.length > 0;

    // Get child sections
    const childSections = hierarchy?.hierarchy?.sections?.filter(
      s => section.child_section_ids.includes(s.id)
    ) || [];

    return (
      <div key={sectionId} style={{ marginLeft: `${depth * 20}px` }} className="mb-2">
        <div
          className="flex items-start gap-2 p-3 hover:bg-gray-50 rounded cursor-pointer border border-gray-200"
          onClick={() => toggleSection(sectionId)}
        >
          {hasContent ? (
            isExpanded ? <ChevronDown className="w-4 h-4 mt-1 flex-shrink-0" /> : <ChevronRight className="w-4 h-4 mt-1 flex-shrink-0" />
          ) : (
            <div className="w-4 h-4" />
          )}
          <div className="flex-1">
            <div className="font-medium text-gray-900">{section.title}</div>
            <div className="text-xs text-gray-600 mt-1 flex items-center gap-3">
              <span>Pages {section.start_page}-{section.end_page}</span>
              {section.chunk_ids.length > 0 && (
                <span className="text-blue-600">
                  • Chunks {section.chunk_ids.length} ({section.metadata.chunk_range[0]}-{section.metadata.chunk_range[1]})
                </span>
              )}
              {sectionImages.length > 0 && (
                <span className="text-green-600">• Images {sectionImages.length}</span>
              )}
              {sectionTables.length > 0 && (
                <span className="text-purple-600">• Tables {sectionTables.length}</span>
              )}
            </div>
          </div>
        </div>

        {isExpanded && hasContent && (
          <div className="mt-2 ml-6 space-y-2 text-sm">
            {/* Chunk IDs */}
            {section.chunk_ids.length > 0 && (
              <div className="p-2 bg-blue-50 rounded">
                <div className="font-medium text-blue-900 mb-1">Chunks ({section.chunk_ids.length}):</div>
                <div className="text-xs text-blue-700 space-y-1">
                  {section.chunk_ids.map((chunkId, i) => (
                    <div key={chunkId}>
                      {i + 1}. {chunkId}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Images */}
            {sectionImages.length > 0 && (
              <div className="p-2 bg-green-50 rounded">
                <div className="font-medium text-green-900 mb-1">Images ({sectionImages.length}):</div>
                <div className="text-xs text-green-700 space-y-1">
                  {sectionImages.map((img, i) => (
                    <div key={img.id}>
                      {i + 1}. {img.id} (Page {img.page})
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Tables */}
            {sectionTables.length > 0 && (
              <div className="p-2 bg-purple-50 rounded">
                <div className="font-medium text-purple-900 mb-1">Tables ({sectionTables.length}):</div>
                <div className="text-xs text-purple-700 space-y-1">
                  {sectionTables.map((tbl, i) => (
                    <div key={tbl.id}>
                      {i + 1}. {tbl.id} (Page {tbl.page})
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Child sections */}
        {childSections.length > 0 && (
          <div className="mt-2">
            {childSections.map((child, i) => renderSection(child, i, depth + 1))}
          </div>
        )}
      </div>
    );
  };

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

      {/* Tabs */}
      <div className="border-b">
        <div className="flex gap-4">
          {[
            { id: 'overview', label: 'Overview', icon: FileText },
            { id: 'chat', label: 'Chat with Doc', icon: MessageSquare },
            ...(document.gdrive_file_id ? [{ id: 'preview', label: 'PDF Preview', icon: Eye }] : []),
            { id: 'hierarchy', label: 'Hierarchy', icon: ChevronRight },
            { id: 'chunks', label: `Chunks (${chunks.length})`, icon: FileText },
            { id: 'images', label: `Images (${images.length})`, icon: ImageIcon },
            { id: 'tables', label: `Tables (${tables.length})`, icon: Table },
          ].map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={`flex items-center gap-2 px-4 py-3 border-b-2 transition-colors ${
                activeTab === tab.id
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-gray-600 hover:text-gray-900'
              }`}
            >
              <tab.icon className="w-4 h-4" />
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Tab Content */}
      <div className="space-y-6">
        {activeTab === 'overview' && (
          <div className="card">
            <h2 className="text-xl font-semibold mb-4">Document Summary</h2>
            <div className="prose max-w-none">
              <p className="text-gray-700 whitespace-pre-wrap">{document.summary}</p>
            </div>
          </div>
        )}

        {activeTab === 'chat' && (
          <div className="flex gap-4 h-[800px]">
            {/* Right: Chat */}
            <div className="w-full">
              <DocumentChatImproved
                docId={docId!}
                documentTitle={document.title}
              />
            </div>
          </div>
        )}

        {activeTab === 'preview' && document.gdrive_file_id && (
          <div className="card">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold">PDF Preview</h2>
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
            <div className="relative bg-gray-100 rounded-lg overflow-hidden" style={{ height: '80vh' }}>
              <iframe
                src={`https://drive.google.com/file/d/${document.gdrive_file_id}/preview`}
                className="w-full h-full border-0"
                allow="autoplay"
                title={`Preview of ${document.title}`}
              />
            </div>
          </div>
        )}

        {activeTab === 'hierarchy' && (
          <div className="card">
            <h2 className="text-xl font-semibold mb-4">Document Hierarchy</h2>
            {hierarchy?.hierarchy?.sections && hierarchy.hierarchy.sections.length > 0 ? (
              <div className="space-y-2">
                {hierarchy.hierarchy.sections.map((section, i) => renderSection(section, i))}
              </div>
            ) : (
              <p className="text-gray-500">No hierarchy data available</p>
            )}
          </div>
        )}

        {activeTab === 'chunks' && (
          <div className="space-y-4">
            {chunks.map((chunk, i) => (
              <div key={chunk.id} className="card">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium text-gray-500">Chunk #{i + 1}</span>
                  <span className="text-xs text-gray-400">Page {chunk.page_number}</span>
                </div>
                <p className="text-sm text-gray-700 whitespace-pre-wrap">{chunk.content}</p>
              </div>
            ))}
          </div>
        )}

        {activeTab === 'images' && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {images.map(image => (
              <div key={image.id} className="card">
                <div className="aspect-video bg-gray-100 rounded-lg mb-3 overflow-hidden">
                  <img
                    src={image.s3_url}
                    alt={image.caption || 'Document image'}
                    className="w-full h-full object-contain"
                    loading="lazy"
                  />
                </div>
                <div className="text-xs text-gray-500 mb-2">Page {image.page_number}</div>
                {image.caption && <p className="text-sm text-gray-700 mb-2">{image.caption}</p>}
                {image.basic_summary && (
                  <p className="text-xs text-gray-600">{image.basic_summary}</p>
                )}
              </div>
            ))}
          </div>
        )}

        {activeTab === 'tables' && (
          <div className="space-y-4">
            {tables.map((table, i) => (
              <div key={table.id} className="card">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-sm font-medium text-gray-500">Table #{i + 1}</span>
                  <span className="text-xs text-gray-400">Page {table.page_number}</span>
                </div>
                {table.description && (
                  <p className="text-sm text-gray-700 mb-3">{table.description}</p>
                )}
                <div className="overflow-x-auto">
                  <div className="text-xs font-mono bg-gray-50 p-3 rounded whitespace-pre-wrap">
                    {table.markdown}
                  </div>
                </div>
                {table.key_insights && table.key_insights.length > 0 && (
                  <div className="mt-3 pt-3 border-t">
                    <div className="text-xs font-medium text-gray-500 mb-2">Key Insights:</div>
                    <ul className="text-sm text-gray-700 list-disc list-inside space-y-1">
                      {table.key_insights.map((insight, j) => (
                        <li key={j}>{insight}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
