import { useCallback, useRef, useState } from 'react';
import { FileText, FileImage, File, Upload, Trash2, Download, X } from 'lucide-react';
import { clsx } from 'clsx';
import { Spinner } from '@/components/common/Spinner';
import {
  type Attachment,
  uploadAttachment,
  deleteAttachment,
  getDownloadUrl,
} from '@/api/attachments';
import { useTicketStore } from '@/stores/ticketStore';
import { formatRelativeTime } from '@/utils/formatters';

interface TicketAttachmentsProps {
  ticketId: string;
  attachments: Attachment[];
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function getFileIcon(contentType: string) {
  if (contentType.startsWith('image/')) {
    return <FileImage className="h-5 w-5 text-purple-500" />;
  }
  if (
    contentType.includes('pdf') ||
    contentType.includes('text') ||
    contentType.includes('document') ||
    contentType.includes('spreadsheet')
  ) {
    return <FileText className="h-5 w-5 text-blue-500" />;
  }
  return <File className="h-5 w-5 text-gray-400" />;
}

export function TicketAttachments({ ticketId, attachments }: TicketAttachmentsProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [dragOver, setDragOver] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  const { addAttachment, removeAttachment } = useTicketStore();

  const handleUpload = useCallback(
    async (files: FileList | null) => {
      if (!files || files.length === 0) return;

      setUploading(true);
      setUploadProgress(0);

      try {
        for (let i = 0; i < files.length; i++) {
          setUploadProgress(Math.round(((i) / files.length) * 100));
          const attachment = await uploadAttachment(ticketId, files[i]);
          addAttachment(attachment);
        }
        setUploadProgress(100);
      } catch {
        // Upload error is handled silently; the user sees the file didn't appear
      } finally {
        setUploading(false);
        setUploadProgress(0);
        if (fileInputRef.current) {
          fileInputRef.current.value = '';
        }
      }
    },
    [ticketId, addAttachment],
  );

  const handleDelete = useCallback(
    async (id: string) => {
      setDeletingId(id);
      try {
        await deleteAttachment(id);
        removeAttachment(id);
      } catch {
        // silent
      } finally {
        setDeletingId(null);
      }
    },
    [removeAttachment],
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      handleUpload(e.dataTransfer.files);
    },
    [handleUpload],
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
  }, []);

  return (
    <div className="space-y-4">
      {/* Upload dropzone */}
      <div
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        className={clsx(
          'relative flex flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 transition-colors',
          dragOver
            ? 'border-brand-400 bg-brand-50'
            : 'border-gray-300 bg-gray-50 hover:border-gray-400',
        )}
      >
        <Upload
          className={clsx(
            'h-8 w-8 mb-2',
            dragOver ? 'text-brand-500' : 'text-gray-400',
          )}
        />
        <p className="text-sm text-gray-600">
          Drag and drop files here, or{' '}
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="font-medium text-brand-600 hover:text-brand-700 underline"
          >
            browse
          </button>
        </p>
        <p className="mt-1 text-xs text-gray-400">Any file type up to 25 MB</p>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          className="hidden"
          onChange={(e) => handleUpload(e.target.files)}
        />

        {/* Upload progress bar */}
        {uploading && (
          <div className="absolute inset-x-0 bottom-0 px-4 pb-2">
            <div className="flex items-center gap-2">
              <div className="flex-1 h-1.5 rounded-full bg-gray-200 overflow-hidden">
                <div
                  className="h-full rounded-full bg-brand-500 transition-all duration-300"
                  style={{ width: `${uploadProgress}%` }}
                />
              </div>
              <span className="text-xs text-gray-500 tabular-nums">{uploadProgress}%</span>
            </div>
          </div>
        )}
      </div>

      {/* Attachment list */}
      {attachments.length === 0 ? (
        <div className="text-center py-8 text-sm text-gray-400">
          No attachments yet. Upload files to get started.
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {attachments.map((att) => {
            const isImage = att.content_type.startsWith('image/');
            return (
              <div
                key={att.id}
                className="group relative flex items-start gap-3 rounded-lg border border-gray-200 bg-white p-3 hover:shadow-sm transition-shadow"
              >
                {/* Thumbnail / icon */}
                <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-gray-50 overflow-hidden">
                  {isImage ? (
                    <button
                      type="button"
                      onClick={() => setPreviewUrl(getDownloadUrl(att.id))}
                      className="h-full w-full"
                    >
                      <img
                        src={getDownloadUrl(att.id)}
                        alt={att.filename}
                        className="h-full w-full object-cover rounded-lg"
                      />
                    </button>
                  ) : (
                    getFileIcon(att.content_type)
                  )}
                </div>

                {/* Info */}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-900 truncate" title={att.filename}>
                    {att.filename}
                  </p>
                  <div className="flex items-center gap-2 text-xs text-gray-400 mt-0.5">
                    <span>{formatFileSize(att.file_size)}</span>
                    <span>&middot;</span>
                    <span>{formatRelativeTime(att.created_at)}</span>
                  </div>
                </div>

                {/* Actions */}
                <div className="flex shrink-0 items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                  <a
                    href={getDownloadUrl(att.id)}
                    download={att.filename}
                    className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
                    title="Download"
                  >
                    <Download className="h-4 w-4" />
                  </a>
                  <button
                    type="button"
                    onClick={() => handleDelete(att.id)}
                    disabled={deletingId === att.id}
                    className="rounded p-1 text-gray-400 hover:bg-red-50 hover:text-red-600 disabled:opacity-50"
                    title="Delete"
                  >
                    {deletingId === att.id ? (
                      <Spinner size="sm" />
                    ) : (
                      <Trash2 className="h-4 w-4" />
                    )}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Image preview overlay */}
      {previewUrl && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-8"
          onClick={() => setPreviewUrl(null)}
        >
          <div className="relative max-h-full max-w-4xl" onClick={(e) => e.stopPropagation()}>
            <button
              type="button"
              onClick={() => setPreviewUrl(null)}
              className="absolute -top-3 -right-3 rounded-full bg-white p-1 shadow-lg hover:bg-gray-100"
            >
              <X className="h-5 w-5 text-gray-700" />
            </button>
            <img
              src={previewUrl}
              alt="Preview"
              className="max-h-[80vh] rounded-lg shadow-2xl object-contain"
            />
          </div>
        </div>
      )}
    </div>
  );
}
