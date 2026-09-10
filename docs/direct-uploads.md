# Direct uploads

Files of at least 8 MB use direct browser-to-blob upload when
`DIRECT_UPLOADS_ENABLED=1` is set on the web app. Smaller files retain streamed
multipart upload and instant row/profile previews.

The authenticated ticket endpoint grants create/write access to exactly one
random staging blob for ten minutes, with HTTPS required and no read/list/delete
permission. Staging is outside the Event Grid inventory prefix. Finalization
rechecks the engagement and user, expiry, size, magic bytes/text classification
and source ETag. Azure copies the validated version into the engagement using a
source If-Match condition; concurrent replacement fails instead of bypassing
validation. Only then can ingestion observe the file. Completed staging/ticket
objects are removed; expired abandoned objects need a one-day lifecycle rule.

Enable only after configuring the storage account's CORS rule for the exact web
origin (`PUT`, `OPTIONS`, `x-ms-blob-type`, `content-type`). Preserve other existing
CORS rules. CSP permits connections only to this configured storage account in
addition to the app origin. Never use wildcard origins or account keys.

Direct upload preserves file validation but does not perform the small-file
questionnaire answer extraction or immediate row preview; normal ingestion and
DQ reporting provide the inventory details after upload. Use the existing small
upload path for completed discovery questionnaires. Large files are not put into
an HTTP request body on the web tier; the final copy is performed by Azure Storage.

Tests cover user/engagement isolation, size limits, disguised binary input and
copying only the validated source ETag. Real storage/CORS/browser validation is a
separate release check and must not be inferred from mocks.
