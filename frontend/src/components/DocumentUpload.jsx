import { useRef, useState } from 'react';

import { uploadDocument } from '../api.js';
import DocumentPreview from './DocumentPreview.jsx';
import FieldError from './FieldError.jsx';

const ACCEPTED_MIME_TYPES = ['image/jpeg', 'image/png', 'application/pdf'];
const ACCEPTED_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.pdf'];
// Kept in sync with the backend's MAX_UPLOAD_SIZE_MB default (backend/.env.example).
// This is a client-side convenience check only — the server enforces its own limit.
const MAX_SIZE_BYTES = 10 * 1024 * 1024;

function getExtension(filename) {
  const index = filename.lastIndexOf('.');
  return index === -1 ? '' : filename.slice(index).toLowerCase();
}

function validateFile(file) {
  const looksLikeAcceptedType =
    ACCEPTED_MIME_TYPES.includes(file.type) || ACCEPTED_EXTENSIONS.includes(getExtension(file.name));
  if (!looksLikeAcceptedType) {
    return 'Unsupported file type. Please upload a JPG, PNG, or PDF file.';
  }
  if (file.size > MAX_SIZE_BYTES) {
    return `File is too large. Maximum size is ${Math.round(MAX_SIZE_BYTES / (1024 * 1024))}MB.`;
  }
  return '';
}

export default function DocumentUpload({ referenceId, onUploaded }) {
  const [error, setError] = useState('');
  const [uploading, setUploading] = useState(false);
  const [document, setDocument] = useState(null);
  const inputRef = useRef(null);

  async function handleFileChange(event) {
    const file = event.target.files?.[0];
    if (!file) return;

    // Rejected before any network request is made (US-05 AC).
    const validationError = validateFile(file);
    if (validationError) {
      setError(validationError);
      setDocument(null);
      if (inputRef.current) inputRef.current.value = '';
      return;
    }

    setError('');
    setUploading(true);
    try {
      const uploaded = await uploadDocument(referenceId, file);
      setDocument(uploaded);
      onUploaded?.(uploaded);
    } catch (err) {
      setError(err.message || 'Upload failed. Please try again.');
      if (inputRef.current) inputRef.current.value = '';
    } finally {
      setUploading(false);
    }
  }

  return (
    <section className="document-upload">
      <h2>Upload identity document</h2>
      <p>Accepted formats: JPG, PNG, or PDF.</p>

      <div className="form-field">
        <label htmlFor="kyc-file">Identity document</label>
        <input
          id="kyc-file"
          ref={inputRef}
          type="file"
          accept={[...ACCEPTED_EXTENSIONS, ...ACCEPTED_MIME_TYPES].join(',')}
          onChange={handleFileChange}
          disabled={uploading}
        />
        <FieldError message={error} />
      </div>

      {uploading && <p role="status">Uploading…</p>}

      {document && (
        <div className="upload-confirmation" role="status">
          <p>
            Uploaded: <strong>{document.original_filename}</strong>
          </p>
          <DocumentPreview referenceId={referenceId} document={document} />
        </div>
      )}
    </section>
  );
}
