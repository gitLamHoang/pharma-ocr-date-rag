import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { STATIC_MODE, api, type DocumentSummary } from "../api";
import { DocumentTable } from "../components/DocumentTable";
import { UploadDropzone, type UploadDropzoneHandle } from "../components/UploadDropzone";

/** While any run is still moving (queued included: it will move next), the list refreshes this often. */
const POLL_MS = 2000;

function inProgress(doc: DocumentSummary): boolean {
  return doc.status !== "done" && doc.status !== "failed";
}

function messageOf(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

/** Upload documents and see which ones still have dates waiting for review. */
export function Documents() {
  const queryClient = useQueryClient();
  const dropzone = useRef<UploadDropzoneHandle>(null);
  const [uploading, setUploading] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const health = useQuery({ queryKey: ["health"], queryFn: () => api.getHealth(), staleTime: 60_000 });
  const documents = useQuery({
    queryKey: ["documents"],
    queryFn: () => api.listDocuments(),
    refetchInterval: (query) => (query.state.data?.some(inProgress) ? POLL_MS : false),
  });

  async function upload(files: File[]) {
    setUploadError(null);
    const failures: string[] = [];
    for (const [i, file] of files.entries()) {
      setUploading(files.length > 1 ? `${file.name} (${i + 1} of ${files.length})` : file.name);
      try {
        await api.uploadDocument(file);
      } catch (error) {
        failures.push(`${file.name}: ${messageOf(error, "The upload failed. Try again.")}`);
      }
      await queryClient.invalidateQueries({ queryKey: ["documents"] });
    }
    setUploading(null);
    setUploadError(failures.length > 0 ? failures.join("\n") : null);
  }

  return (
    <div className="screen">
      <header className="title-row">
        <h1>Documents</h1>
        <div className="title-row__actions">
          <button
            type="button"
            className="button button--primary"
            disabled={uploading !== null}
            onClick={() => dropzone.current?.open()}
          >
            Upload documents
          </button>
        </div>
      </header>

      {/* The static build's banner already says rules only. */}
      {health.data && !health.data.ai_enabled && !STATIC_MODE ? (
        <p className="notice">AI classification off — rules only</p>
      ) : null}

      <UploadDropzone ref={dropzone} onAccept={upload} uploading={uploading} error={uploadError} />

      <DocumentTable
        documents={documents.data}
        notice={
          documents.isError && !documents.data ? (
            <span className="doc-table__failure" role="alert">
              Could not load the documents. {messageOf(documents.error, "")}{" "}
              <button type="button" className="text-button" onClick={() => void documents.refetch()}>
                Retry
              </button>
            </span>
          ) : null
        }
      />
    </div>
  );
}
