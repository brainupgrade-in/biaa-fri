import React, { useState } from 'react';

interface DocumentUploaderProps {
  onUpload: (file: File) => Promise<void>;
}

export function DocumentUploader({ onUpload }: DocumentUploaderProps) {
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;

    setUploading(true);
    setProgress(0);

    try {
      // Simulate upload progress
      const interval = setInterval(() => {
        setProgress(p => Math.min(p + 10, 90));
      }, 200);

      await onUpload(file);
      
      clearInterval(interval);
      setProgress(100);
      setFile(null);
      (e.target as HTMLFormElement).reset();
    } catch (error) {
      console.error('Upload failed:', error);
      alert('Upload failed. Please try again.');
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="document-uploader bg-white rounded-lg shadow p-4 mb-6">
      <h3 className="font-semibold mb-3">Upload Financial Document</h3>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <input
            type="file"
            accept=".pdf,.html,.htm,.xbrl"
            onChange={handleFileChange}
            disabled={uploading}
            className="w-full p-2 border rounded"
          />
          {file && (
            <p className="text-sm text-gray-600 mt-1">
              Selected: {file.name} ({(file.size / 1024 / 1024).toFixed(2)} MB)
            </p>
          )}
        </div>
        
        <button
          type="submit"
          disabled={uploading || !file}
          className="w-full px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
        >
          {uploading ? `Uploading... ${progress}%` : 'Upload & Process'}
        </button>
      </form>

      <p className="text-xs text-gray-500 mt-3 text-center">
        Supported formats: PDF, HTML, XBRL. Max size: 50MB.
      </p>
    </div>
  );
}

export default DocumentUploader;