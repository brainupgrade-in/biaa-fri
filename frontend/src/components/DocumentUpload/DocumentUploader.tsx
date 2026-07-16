import React, { useState, useRef, useCallback } from 'react';

interface DocumentUploaderProps {
  onUpload: (file: File) => Promise<void>;
  loading: boolean;
}

export function DocumentUploader({ onUpload, loading }: DocumentUploaderProps) {
  const [dragActive, setDragActive] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadProgress, setUploadProgress] = useState<{ file: File; progress: number } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const file = e.dataTransfer.files[0];
      if (isValidFile(file)) {
        setSelectedFile(file);
      }
    }
  }, []);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      if (isValidFile(file)) {
        setSelectedFile(file);
      }
    }
  };

  const isValidFile = (file: File): boolean => {
    const validTypes = ['application/pdf', 'text/html', 'application/xhtml+xml', 'application/xml', 'text/xml'];
    const validExtensions = ['.pdf', '.html', '.htm', '.xbrl', '.xml'];
    
    const hasValidType = validTypes.includes(file.type) || 
      validExtensions.some(ext => file.name.toLowerCase().endsWith(ext));
    
    if (!hasValidType) {
      alert('Please select a PDF, HTML, or XBRL file');
      return false;
    }
    
    if (file.size > 50 * 1024 * 1024) {
      alert('File size must be less than 50MB');
      return false;
    }
    
    return true;
  };

  const handleUpload = async () => {
    if (!selectedFile) return;
    
    setUploadProgress({ file: selectedFile, progress: 0 });
    setDragActive(false);
    
    try {
      // Simulate progress
      const progressInterval = setInterval(() => {
        setUploadProgress(prev => {
          if (!prev) return prev;
          if (prev.progress >= 90) {
            clearInterval(progressInterval);
            return { ...prev, progress: 90 };
          }
          return { ...prev, progress: prev.progress + 10 };
        });
      }, 100);

      await onUpload(selectedFile);
      
      clearInterval(progressInterval);
      setUploadProgress({ file: selectedFile, progress: 100 });
      setSelectedFile(null);
      
      // Reset after a moment
      setTimeout(() => setUploadProgress(null), 1000);
    } catch (error) {
      setUploadProgress(null);
      setSelectedFile(null);
    }
  };

  const removeFile = () => {
    setSelectedFile(null);
  };

  return (
    <div className="card">
      <div className="card-header">Upload Financial Document</div>
      <div className="card-body">
        <div 
          className={`file-upload ${dragActive ? 'drag-active' : ''}`}
          onDragEnter={handleDrag}
          onDragLeave={handleDrag}
          onDragOver={handleDrag}
          onDrop={handleDrop}
        >
          <input
            ref={fileInputRef}
            type="file"
            id="file-upload"
            accept=".pdf,.html,.htm,.xbrl,.xml"
            onChange={handleFileSelect}
            disabled={loading || !!selectedFile}
          />
          
          {selectedFile ? (
            <div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                  <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                    <polyline points="14 2 14 8 20 8"/>
                    <line x1="16" y1="13" x2="8" y2="13"/>
                    <line x1="16" y1="17" x2="8" y2="17"/>
                    <polyline points="10 9 9 9 8 9"/>
                  </svg>
                  <div>
                    <div style={{ fontWeight: 500 }}>{selectedFile.name}</div>
                    <div style={{ fontSize: '0.75rem', color: '#6b7280' }}>
                      {(selectedFile.size / 1024 / 1024).toFixed(2)} MB
                    </div>
                  </div>
                </div>
                <button 
                  type="button"
                  onClick={removeFile}
                  style={{
                    background: 'none',
                    border: 'none',
                    color: '#ef4444',
                    cursor: 'pointer',
                    padding: '0.25rem'
                  }}
                >
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <line x1="18" y1="6" x2="6" y2="18"/>
                    <line x1="6" y1="6" x2="18" y2="18"/>
                  </svg>
                </button>
              </div>
              
              <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'center' }}>
                <button 
                  className="btn btn-primary"
                  onClick={handleUpload}
                  disabled={loading}
                >
                  {loading ? 'Processing...' : 'Upload & Analyze'}
                </button>
              </div>
            </div>
          ) : (
            <div>
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ color: '#9ca3af', marginBottom: '1rem' }}>
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                <polyline points="17 8 12 3 7 8"/>
                <line x1="12" y1="3" x2="12" y2="15"/>
              </svg>
              <p style={{ color: '#6b7280', marginBottom: '0.5rem' }}>
                Drag and drop a financial report, or click to browse
              </p>
              <p style={{ fontSize: '0.75rem', color: '#9ca3af' }}>
                Supported formats: PDF, HTML, XBRL (max 50MB)
              </p>
              <button 
                type="button"
                className="btn btn-primary"
                onClick={() => fileInputRef.current?.click()}
                disabled={loading}
                style={{ marginTop: '1rem' }}
              >
                Select File
              </button>
            </div>
          )}
        </div>

        {uploadProgress && (
          <div style={{ marginTop: '1rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.25rem' }}>
              <span style={{ fontSize: '0.875rem', color: '#6b7280' }}>Uploading...</span>
              <span style={{ fontSize: '0.875rem', fontWeight: 500 }}>{uploadProgress.progress}%</span>
            </div>
            <div style={{ height: '6px', background: '#e5e7eb', borderRadius: '3px', overflow: 'hidden' }}>
              <div 
                style={{ 
                  height: '100%', 
                  width: `${uploadProgress.progress}%`, 
                  background: '#2563eb',
                  transition: 'width 0.3s ease'
                }} 
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}