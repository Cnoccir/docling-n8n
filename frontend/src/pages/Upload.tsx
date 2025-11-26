import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useDropzone } from 'react-dropzone';
import { Upload as UploadIcon, X, File, CheckCircle, AlertCircle, Youtube as YoutubeIcon } from 'lucide-react';
import { uploadApi, youtubeApi } from '@/services/api';

interface UploadedFile {
  file: File;
  status: 'pending' | 'uploading' | 'success' | 'error';
  jobId?: string;
  error?: string;
}

export default function Upload() {
  const navigate = useNavigate();
  const [files, setFiles] = useState<UploadedFile[]>([]);
  const [documentType, setDocumentType] = useState('');
  const [tags, setTags] = useState('');
  const [reprocess, setReprocess] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadSource, setUploadSource] = useState<'file' | 'youtube'>('file');
  const [youtubeUrl, setYoutubeUrl] = useState('');

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept: { 'application/pdf': ['.pdf'] },
    onDrop: (acceptedFiles) => {
      const newFiles = acceptedFiles.map((file) => ({
        file,
        status: 'pending' as const,
      }));
      setFiles((prev) => [...prev, ...newFiles]);
    },
  });

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const uploadFiles = async () => {
    if (files.length === 0) return;

    setUploading(true);

    try {
      const metadata = {
        document_type: documentType || undefined,
        tags: tags || undefined,
        reprocess: reprocess,
      };

      if (files.length === 1) {
        // Single file upload
        setFiles((prev) =>
          prev.map((f, i) => (i === 0 ? { ...f, status: 'uploading' } : f))
        );

        const response = await uploadApi.single(files[0].file, metadata);

        setFiles((prev) =>
          prev.map((f, i) =>
            i === 0
              ? { ...f, status: 'success', jobId: response.job_id }
              : f
          )
        );

        // Navigate to queue after 1 second
        setTimeout(() => navigate('/queue'), 1000);
      } else {
        // Bulk upload
        setFiles((prev) => prev.map((f) => ({ ...f, status: 'uploading' })));

        const response = await uploadApi.bulk(
          files.map((f) => f.file),
          metadata
        );

        setFiles((prev) =>
          prev.map((f, i) => {
            const result = response.results[i];
            return {
              ...f,
              status: result.status === 'queued' ? 'success' : 'error',
              jobId: result.job_id,
              error: result.error,
            };
          })
        );

        // Navigate to queue after 2 seconds
        setTimeout(() => navigate('/queue'), 2000);
      }
    } catch (error: any) {
      setFiles((prev) =>
        prev.map((f) => ({
          ...f,
          status: 'error',
          error: error.message || 'Upload failed',
        }))
      );
    } finally {
      setUploading(false);
    }
  };

  const uploadYoutubeUrl = async () => {
    if (!youtubeUrl) return;

    setUploading(true);
    try {
      const metadata = {
        tags: tags ? tags.split(',').map(t => t.trim()) : undefined,
        reprocess: reprocess,
      };
      await youtubeApi.upload(youtubeUrl, metadata);
      // Navigate to queue after 1 second
      setTimeout(() => navigate('/queue'), 1000);
    } catch (error: any) {
      // Handle error, maybe show a notification
      console.error("YouTube upload failed", error);
    } finally {
      setUploading(false);
    }
  };

  const handleSubmit = () => {
    if (uploadSource === 'file') {
      uploadFiles();
    } else {
      uploadYoutubeUrl();
    }
  };


  return (
    <div className="max-w-4xl mx-auto space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold">Upload Content</h1>
        <p className="text-gray-600 mt-1">Upload PDF documents or add YouTube videos for processing</p>
      </div>

      {/* Upload Form */}
      <div className="card space-y-6">
        {/* Upload source toggle */}
        <div className="flex justify-center gap-2 rounded-md bg-gray-100 p-1">
          <button
            onClick={() => setUploadSource('file')}
            className={`w-full px-4 py-2 text-sm font-medium rounded-md transition-colors ${
              uploadSource === 'file' ? 'bg-white text-gray-900 shadow' : 'text-gray-600 hover:bg-gray-200'
            }`}
          >
            File Upload
          </button>
          <button
            onClick={() => setUploadSource('youtube')}
            className={`w-full px-4 py-2 text-sm font-medium rounded-md transition-colors ${
              uploadSource === 'youtube' ? 'bg-white text-gray-900 shadow' : 'text-gray-600 hover:bg-gray-200'
            }`}
          >
            YouTube URL
          </button>
        </div>


        {uploadSource === 'file' ? (
          <>
            {/* Dropzone */}
            <div
              {...getRootProps()}
              className={`
                border-2 border-dashed rounded-lg p-12 text-center cursor-pointer transition-colors
                ${
                  isDragActive
                    ? 'border-blue-500 bg-blue-50'
                    : 'border-gray-300 hover:border-gray-400'
                }
              `}
            >
              <input {...getInputProps()} />
              <UploadIcon className="w-12 h-12 mx-auto text-gray-400 mb-4" />
              {isDragActive ? (
                <p className="text-lg font-medium text-blue-600">Drop files here...</p>
              ) : (
                <>
                  <p className="text-lg font-medium text-gray-900 mb-2">
                    Drop PDF files here, or click to select
                  </p>
                  <p className="text-sm text-gray-500">
                    Support for single or multiple files (max 50 files)
                  </p>
                </>
              )}
            </div>

            {/* File List */}
            {files.length > 0 && (
              <div className="space-y-2">
                <h3 className="font-medium text-gray-900">Files ({files.length})</h3>
                <div className="space-y-2">
                  {files.map((item, index) => (
                    <div
                      key={index}
                      className="flex items-center justify-between p-3 border border-gray-200 rounded-lg"
                    >
                      <div className="flex items-center gap-3 flex-1">
                        <File className="w-5 h-5 text-gray-400" />
                        <div className="flex-1">
                          <p className="font-medium text-gray-900 text-sm">{item.file.name}</p>
                          <p className="text-xs text-gray-500">
                            {(item.file.size / 1024 / 1024).toFixed(2)} MB
                          </p>
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        {item.status === 'success' && (
                          <CheckCircle className="w-5 h-5 text-green-600" />
                        )}
                        {item.status === 'error' && (
                          <AlertCircle className="w-5 h-5 text-red-600" />
                        )}
                        {item.status === 'pending' && (
                          <button
                            onClick={() => removeFile(index)}
                            className="p-1 hover:bg-gray-100 rounded"
                            disabled={uploading}
                          >
                            <X className="w-4 h-4 text-gray-500" />
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        ) : (
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                YouTube URL
              </label>
              <div className="relative">
                <YoutubeIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
                <input
                  type="text"
                  value={youtubeUrl}
                  onChange={(e) => setYoutubeUrl(e.target.value)}
                  placeholder="e.g., https://www.youtube.com/watch?v=..."
                  className="input w-full pl-10"
                  disabled={uploading}
                />
              </div>
            </div>
          </div>
        )}

        {/* Metadata */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {uploadSource === 'file' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Document Type (optional)
              </label>
              <input
                type="text"
                value={documentType}
                onChange={(e) => setDocumentType(e.target.value)}
                placeholder="e.g., manual, report, guide"
                className="input w-full"
                disabled={uploading}
              />
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Tags (optional)
            </label>
            <input
              type="text"
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              placeholder="comma-separated tags"
              className="input w-full"
              disabled={uploading}
            />
          </div>
        </div>

        {/* Reprocess Option */}
        <div className="flex items-center gap-3 p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
          <input
            type="checkbox"
            id="reprocess"
            checked={reprocess}
            onChange={(e) => setReprocess(e.target.checked)}
            className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
            disabled={uploading}
          />
          <label htmlFor="reprocess" className="flex-1 cursor-pointer">
            <div className="text-sm font-medium text-gray-900">
              Allow Reprocessing
            </div>
            <div className="text-xs text-gray-600">
              If a document with the same content already exists, create a new version instead of failing
            </div>
          </label>
        </div>

        {/* Upload Button */}
        <button
          onClick={handleSubmit}
          disabled={
            (uploadSource === 'file' && files.length === 0) ||
            (uploadSource === 'youtube' && !youtubeUrl) ||
            uploading
          }
          className="btn-primary w-full"
        >
          {uploading
            ? 'Uploading...'
            : `Upload ${
                uploadSource === 'file'
                  ? files.length + ' file(s)'
                  : 'YouTube Video'
              }`}
        </button>
      </div>
    </div>
  );
}
