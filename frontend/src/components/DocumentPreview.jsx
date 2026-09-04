import { documentFileUrl } from '../api.js';

export default function DocumentPreview({ referenceId, document }) {
  if (!document) return null;

  const url = documentFileUrl(referenceId, document.id);

  if (document.content_type === 'application/pdf') {
    return (
      <embed
        src={url}
        type="application/pdf"
        width="100%"
        height="500"
        title="Uploaded document preview"
      />
    );
  }

  return (
    <img
      src={url}
      alt="Uploaded identity document preview"
      className="document-preview-image"
      loading="lazy"
    />
  );
}
