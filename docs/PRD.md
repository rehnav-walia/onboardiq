# Product Requirements Document (PRD)
## AI-Powered Banking Onboarding Application

| Field | Value |
|---|---|
| Product Name | AI-Powered Banking Onboarding ("OnboardIQ") |
| Version | 0.2 |
| Owner | [Your Name] |
| Status | Approved for development |
| Type | Portfolio / placement demonstration project |

---

## 1. Problem Statement

Traditional bank account opening is slow and manual. A customer submits a form and identity documents; a back-office operations team then manually reads each document, re-types the details, compares them against the submitted form, and approves or rejects. This creates long turnaround times, high operational cost, inconsistent decisions between reviewers, and weak audit trails where the *reason* for a decision is never captured.

Full automation is not an acceptable answer in a regulated industry. Banks need a system where AI does the heavy lifting but a human remains accountable for the final call.

## 2. Product Vision

**AI extracts, compares, and explains. A human validates and approves.**

The AI never approves an application on its own. It reduces a 15-minute manual review to a 30-second confirmation, while producing a complete, explainable audit trail for every decision.

## 3. Goals & Non-Goals

### Goals
- Demonstrate an end-to-end onboarding flow from application submission to final decision
- Show practical, correct use of LLM document extraction and RAG-grounded question answering
- Make human-in-the-loop a visible product feature, not a hidden implementation detail
- Produce explainable, auditable AI output appropriate to a regulated domain

### Non-Goals (v0.2)
- Production-grade security, encryption, or real PII handling
- Integration with any real bank core system, credit bureau, or government ID API
- Insurance underwriting, claims, lending, or collections modules
- Voice agent / contact centre functionality
- Multi-tenancy or role hierarchies beyond Applicant, Reviewer, and Auditor

## 4. Personas

| Persona | Description | Primary Need |
|---|---|---|
| **Applicant** | Retail customer opening a savings account online | Fast, clear process; know what is needed and where the application stands |
| **Reviewer** (Ops Analyst) | Bank back-office staff approving or rejecting applications | See AI findings fast, understand *why* something was flagged, decide with confidence |
| **Auditor / Compliance** | Reviews decisions after the fact | Complete record of who decided what, when, and on what basis |
| **Administrator** | Maintains the policy knowledge base | Keep assistant answers current and grounded |

---

## 5. The 10 Critical Features

| ID | Feature | Priority | Description |
|---|---|---|---|
| **F1** | Application Intake | P0 | Multi-step account opening form with validation, save-and-resume, and reference ID generation |
| **F2** | KYC Document Upload & Management | P0 | Upload, preview, replace, and lifecycle management of identity documents |
| **F3** | AI Document Extraction | P0 | LLM vision-based extraction of structured identity fields, with confidence scoring |
| **F4** | Automated Cross-Verification | P0 | Field-level comparison of extracted data against submitted data, with intelligent match tolerance |
| **F5** | Risk Scoring & Fraud Signals | P1 | Composite risk indicator from mismatch severity, document quality, confidence, and rule checks |
| **F6** | Reviewer Work Queue | P0 | Prioritised, filterable dashboard of applications awaiting decision, with ageing visibility |
| **F7** | Human-in-the-Loop Review & Decision | P0 | Side-by-side review with mandatory human sign-off; approve, reject, or request information |
| **F8** | Explainability Layer | P0 | Every AI output carries a plain-language justification; no unexplained result reaches a user |
| **F9** | Audit Log & Compliance Reporting | P1 | Append-only record of every AI output and human action, exportable for review |
| **F10** | RAG Policy Assistant | P1 | Grounded chat assistant answering onboarding questions from policy documents with citations |

---

## 6. User Stories

Each story includes **Acceptance Criteria (AC)** — what makes the behaviour correct — and a **Definition of Done (DoD)** — what makes the work shippable.

### Global Definition of Done
Every story must additionally satisfy these before being considered complete:
- Code merged to main with no failing tests
- Unit tests written for new logic
- No hardcoded secrets; configuration via environment variables
- Errors handled explicitly; no unhandled exception surfaces to the user
- Manually verified end-to-end in the running application
- README or PRD updated if behaviour differs from this document

---

## Epic A — Application Intake (F1)

### US-01 · Submit account application
> As an **applicant**, I want to complete an online account opening form so that I can apply without visiting a branch.

**Acceptance Criteria**
- Form captures: full name, date of birth, ID number, address, email, phone, account type
- Required fields validated on both client and server
- Invalid email, invalid phone, and future-dated date of birth are rejected with specific messages
- On successful submit, an `Application` record is created with status `SUBMITTED`
- A unique, human-readable reference ID is generated and shown (e.g. `ONB-2026-00042`)

**Definition of Done**
- Server-side validation cannot be bypassed by crafting a direct API request
- Reference ID uniqueness enforced at the database level
- Form state persists across validation failures — the user does not lose entered data

---

### US-02 · Multi-step form with progress
> As an **applicant**, I want the form broken into clear steps so that it does not feel overwhelming.

**Acceptance Criteria**
- Form split into at least three steps: Personal Details, Address & Contact, Account Type
- A progress indicator shows current step and total steps
- Back navigation preserves previously entered values
- Each step validates before allowing advance

**Definition of Done**
- Step state managed in a single source of truth
- Direct navigation to a later step without completing earlier ones is prevented

---

### US-03 · Save and resume application
> As an **applicant**, I want to save an incomplete application so that I can finish it later.

**Acceptance Criteria**
- A partially completed application can be saved with status `DRAFT`
- Applicant can resume using the reference ID
- Draft applications are not visible in the reviewer queue
- Resuming restores all previously entered field values

**Definition of Done**
- Draft and submitted states clearly distinguished in the data model
- Resume flow tested with a partially completed multi-step form

---

### US-04 · Applicant-facing validation feedback
> As an **applicant**, I want clear error messages so that I know exactly what to fix.

**Acceptance Criteria**
- Errors appear inline next to the offending field, not only as a summary
- Messages state what is wrong and what is expected
- Errors clear as soon as the field becomes valid
- Submit is blocked while any error is unresolved

**Definition of Done**
- No raw validation library output or stack trace shown to the user
- Error copy reviewed for plain language

---

## Epic B — Document Upload (F2)

### US-05 · Upload KYC document
> As an **applicant**, I want to upload my identity document so that my identity can be verified.

**Acceptance Criteria**
- Accepts JPG, PNG, and PDF
- Enforces a maximum file size with a clear message when exceeded
- File stored and linked to the application record
- Upload confirmation shown with the filename
- Unsupported file types rejected before upload begins

**Definition of Done**
- File type validated by content, not only by file extension
- Storage path is not user-controllable — no path traversal possible
- Orphaned uploads with no linked application cannot occur

---

### US-06 · Preview uploaded document
> As an **applicant**, I want to see the document I uploaded so that I can confirm it is the correct, legible file.

**Acceptance Criteria**
- Uploaded image or PDF renders in the browser after upload
- Preview available before final submission
- Preview loads without forcing a file download

**Definition of Done**
- Both PDF and image preview verified
- Large files do not block the UI while loading

---

### US-07 · Replace an uploaded document
> As an **applicant**, I want to replace a document so that I can correct a blurry or wrong upload.

**Acceptance Criteria**
- Replace action available while status is `DRAFT` or `INFO_REQUESTED`
- Replacing invalidates any prior extraction result for that document
- Replacement blocked once the application is under review
- The previous document version is retained for audit, not deleted

**Definition of Done**
- Stale extraction results cannot appear against a replaced document
- Version retention verified in the data model

---

### US-08 · Document type selection
> As an **applicant**, I want to declare what document I am uploading so that the system knows what to expect.

**Acceptance Criteria**
- Applicant selects document type from a defined list (Passport, National ID, Driving Licence)
- Selected type passed to the extraction step as context
- Mismatch between declared and detected type is flagged during verification

**Definition of Done**
- Document type stored as a controlled enum, not free text
- Declared-versus-detected mismatch path tested

---

## Epic C — AI Document Extraction (F3)

### US-09 · Extract identity fields from document
> As the **system**, I want to extract identity fields from the uploaded document so that data does not need to be re-typed manually.

**Acceptance Criteria**
- Returns structured JSON: `name`, `date_of_birth`, `id_number`, `document_type`
- Each field carries a confidence indicator
- Result persisted against the application and document
- Extraction runs automatically on submission, without manual triggering

**Definition of Done**
- LLM response parsed defensively; malformed JSON does not crash the flow
- Extraction is idempotent — re-running does not duplicate results
- Prompt stored in version control as a named template, not inline as a magic string

---

### US-10 · Handle unreadable documents
> As the **system**, I want to fail clearly on unreadable documents so that I never guess at identity data.

**Acceptance Criteria**
- If the document is illegible, the system returns an explicit failure state
- No partial or invented field values are persisted on failure
- Application routed to human review with a "document unreadable" flag
- Applicant informed that a clearer document is needed

**Definition of Done**
- Tested with a deliberately blurred and a blank document
- Failure state distinguishable from low-confidence success in the data model

---

### US-11 · Confidence scoring per field
> As a **reviewer**, I want per-field confidence so that I know which values to scrutinise.

**Acceptance Criteria**
- Every extracted field has a confidence value
- Fields below a configurable threshold are visually marked as low confidence
- Threshold configurable without a code change
- Low confidence alone does not reject an application — it escalates attention

**Definition of Done**
- Threshold read from configuration
- Low-confidence rendering verified in the review UI

---

### US-12 · Graceful degradation on AI failure
> As the **system**, I want to keep working when the AI service is unavailable so that onboarding does not halt.

**Acceptance Criteria**
- LLM timeout or error does not return a server error to the applicant
- Application moves to `PENDING_REVIEW` flagged "AI unavailable — manual extraction required"
- Failure recorded in the audit log
- Retry possible from the reviewer screen

**Definition of Done**
- Tested by simulating an API failure and a timeout
- Timeout value configurable
- No silent failures — every failure produces a log entry

---

## Epic D — Cross-Verification (F4)

### US-13 · Compare extracted data against submitted data
> As the **system**, I want to compare document data against form entries so that discrepancies surface before human review.

**Acceptance Criteria**
- Each comparable field marked `MATCH`, `PARTIAL_MATCH`, or `MISMATCH`
- Comparison covers at minimum: name, date of birth, ID number
- A summary flag count stored on the application
- Application status moves to `PENDING_REVIEW` on completion

**Definition of Done**
- Comparison logic unit tested with a table of edge cases
- Results persisted per field, not as an aggregate blob

---

### US-14 · Intelligent match tolerance
> As a **reviewer**, I want trivial formatting differences ignored so that I am not flooded with false flags.

**Acceptance Criteria**
- Case differences treated as a match ("JOHN SMITH" vs "John Smith")
- Extra or missing whitespace treated as a match
- Differing date formats representing the same date treated as a match (`01/02/1998` vs `1998-02-01`)
- Middle name present in one source but absent in the other is `PARTIAL_MATCH`, not `MISMATCH`
- Genuinely different values remain `MISMATCH`

**Definition of Done**
- Normalisation rules documented in code
- At least ten edge cases covered by unit tests
- Ambiguous date formats resolved deterministically by an explicit rule, not by guesswork

---

### US-15 · Declared vs detected document type check
> As the **system**, I want to verify the document is the type the applicant claimed so that mismatched submissions are caught.

**Acceptance Criteria**
- Detected document type compared against the declared type
- Mismatch raises a flag visible in the review screen
- Mismatch does not auto-reject the application

**Definition of Done**
- Flag rendered distinctly from field-level mismatches
- Tested with a deliberately mis-declared document

---

## Epic E — Risk Scoring (F5)

### US-16 · Compute composite risk indicator
> As a **reviewer**, I want a risk indicator so that I can prioritise which applications need close attention.

**Acceptance Criteria**
- Risk presented as `LOW`, `MEDIUM`, or `HIGH`
- Inputs include mismatch count and severity, extraction confidence, document readability, declared-type mismatch
- Scoring is deterministic and reproducible for the same inputs
- Risk level never causes automatic approval or rejection

**Definition of Done**
- Scoring rules documented in the codebase
- Same input produces same output across runs, verified by test
- Code comments state explicitly that risk is advisory only

---

### US-17 · Rule-based validity checks
> As the **system**, I want basic rule checks so that obvious problems are caught without an LLM call.

**Acceptance Criteria**
- Applicant under minimum age is flagged
- Expired document, where expiry is extractable, is flagged
- Future-dated date of birth is flagged
- Rule checks run independently of the LLM and still function if AI is unavailable

**Definition of Done**
- Rules unit tested independently of AI code paths
- Minimum age configurable

---

### US-18 · Risk breakdown visibility
> As a **reviewer**, I want to see what drove the risk level so that I can judge whether I agree with it.

**Acceptance Criteria**
- Review screen shows contributing factors, not just the final level
- Each factor states its individual contribution in plain language
- Reviewer can proceed regardless of risk level

**Definition of Done**
- No opaque numeric score shown without accompanying explanation
- Verified that a `HIGH` risk application can still be approved by a human

---

## Epic F — Reviewer Work Queue (F6)

### US-19 · View pending application queue
> As a **reviewer**, I want a list of applications awaiting decision so that I can work through them efficiently.

**Acceptance Criteria**
- Queue shows reference ID, applicant name, submission time, flag count, risk level, status
- Only applications in `PENDING_REVIEW` or `INFO_REQUESTED` appear
- Draft applications never appear
- Clicking a row opens the review screen

**Definition of Done**
- Queue query paginated and does not degrade with volume
- Tested with a seeded dataset of at least 50 applications

---

### US-20 · Sort and filter the queue
> As a **reviewer**, I want to sort and filter so that I can handle the most urgent work first.

**Acceptance Criteria**
- Sortable by submission time and risk level
- Filterable by status and risk level
- Filter state persists while navigating within the session
- Empty results show a clear message, not a blank screen

**Definition of Done**
- Sorting and filtering performed server-side
- Combined filter and sort verified together

---

### US-21 · Ageing visibility
> As a **reviewer**, I want to see how long an application has been waiting so that nothing is silently forgotten.

**Acceptance Criteria**
- Each queue row shows time elapsed since entering `PENDING_REVIEW`
- Applications past a configurable threshold are visually marked as overdue
- Overdue items can be filtered

**Definition of Done**
- Elapsed time computed at query time, not stored stale
- Threshold configurable
- Timezone handling verified

---

## Epic G — Human-in-the-Loop Decision (F7)

### US-22 · Side-by-side comparison view
> As a **reviewer**, I want submitted and extracted data side by side so that I can assess discrepancies quickly.

**Acceptance Criteria**
- Both data sets displayed in aligned columns
- Mismatched fields highlighted; partial matches visually distinguished from full mismatches
- Uploaded document viewable in the same screen without navigating away
- Low-confidence fields marked

**Definition of Done**
- Layout usable without horizontal scrolling at standard screen widths
- Highlighting distinguishable without relying on colour alone

---

### US-23 · Approve, reject, or request information
> As a **reviewer**, I want to record my decision so that the application progresses.

**Acceptance Criteria**
- Three actions available: Approve, Reject, Request More Information
- Reasoning note is **mandatory** for Reject and Request More Information
- Decision updates application status and writes to the audit log
- Reviewer identity recorded against the decision
- A decision cannot be submitted twice for the same application

**Definition of Done**
- Double submission prevented server-side, not only by disabling the button
- Decision and audit write occur atomically — no partial state possible
- Tested that a decision missing required reasoning is rejected by the API

---

### US-24 · No automatic approval path
> As an **auditor**, I want certainty that no application can be approved without a human so that accountability is preserved.

**Acceptance Criteria**
- No code path sets status to `APPROVED` without a recorded reviewer decision
- AI output cannot trigger a status change beyond `PENDING_REVIEW`
- Attempting to approve via API without reviewer identity fails

**Definition of Done**
- An explicit automated test asserts no auto-approval is possible
- Constraint documented in the README as a stated design principle

---

### US-25 · Request-more-information loop
> As an **applicant**, I want to be told what additional information is needed so that I can complete my application.

**Acceptance Criteria**
- Reviewer's request note visible to the applicant
- Application moves to `INFO_REQUESTED`
- Applicant can upload a replacement document and resubmit
- Resubmission re-triggers extraction and verification, returning to `PENDING_REVIEW`

**Definition of Done**
- Full loop tested: submit → request info → resubmit → review → approve
- Prior review context retained and visible on the second review

---

## Epic H — Explainability & Audit (F8, F9)

### US-26 · Justification on every AI output
> As a **reviewer**, I want a short reason with each AI result so that I can trust and challenge it.

**Acceptance Criteria**
- Every extraction and comparison result carries a one-to-two sentence natural-language justification
- Justifications reference the specific field and the observed difference
- No AI output renders in the UI without an accompanying reason

**Definition of Done**
- The UI cannot display an AI value with an empty justification — enforced, not merely conventional
- Justification text stored, not regenerated on each view

---

### US-27 · Append-only audit log
> As an **auditor**, I want a complete record of AI outputs and human actions so that any application can be reconstructed.

**Acceptance Criteria**
- Entries capture timestamp, actor (system or reviewer ID), action, AI justification, human reasoning
- Entries are append-only — no update or delete path exists
- Log viewable per application in chronological order
- Every status transition produces an entry

**Definition of Done**
- No update or delete endpoint exists for audit entries
- Test asserts a full application lifecycle produces a complete, correctly ordered trail

---

### US-28 · Export audit trail
> As an **auditor**, I want to export an application's decision history so that I can review it outside the system.

**Acceptance Criteria**
- Export available per application in a structured format (CSV or JSON)
- Export includes all audit entries plus final decision and reviewer identity
- Export is read-only and does not alter application state

**Definition of Done**
- Exported file opens correctly in a spreadsheet tool
- Commas, quotes, and newlines in reasoning text handled correctly

---

## Epic I — RAG Policy Assistant (F10)

### US-29 · Ingest policy documents
> As an **administrator**, I want to load bank policy documents into the knowledge base so that the assistant can answer from them.

**Acceptance Criteria**
- Documents chunked, embedded, and stored in a vector store
- Re-running ingestion does not create duplicate entries
- Ingestion reports how many chunks were created
- Retrieval returns the top-k relevant chunks for a query

**Definition of Done**
- Chunk size and overlap configurable and documented
- Sample policy documents committed to the repository so the demo is reproducible
- Idempotency verified by running ingestion twice

---

### US-30 · Ask grounded onboarding questions
> As an **applicant**, I want to ask questions about required documents and timelines so that I can proceed without contacting support.

**Acceptance Criteria**
- Chat interface available during the application flow
- Answers generated only from ingested policy content
- Each answer cites the source document or section
- When no relevant content is found, the assistant says so explicitly rather than inventing an answer
- The assistant does not comment on the status or likely outcome of the applicant's own application

**Definition of Done**
- Tested with an out-of-scope question; assistant declines rather than hallucinating
- Retrieved context logged for debugging
- Every citation maps to a real, retrievable source chunk

---

## 7. Story Coverage Map

| Feature | Stories |
|---|---|
| F1 Application Intake | US-01, US-02, US-03, US-04 |
| F2 Document Upload | US-05, US-06, US-07, US-08 |
| F3 AI Extraction | US-09, US-10, US-11, US-12 |
| F4 Cross-Verification | US-13, US-14, US-15 |
| F5 Risk Scoring | US-16, US-17, US-18 |
| F6 Reviewer Queue | US-19, US-20, US-21 |
| F7 Human-in-the-Loop | US-22, US-23, US-24, US-25 |
| F8 Explainability | US-26 |
| F9 Audit & Reporting | US-27, US-28 |
| F10 RAG Assistant | US-29, US-30 |

## 8. Application Status Model

```
DRAFT → SUBMITTED → PROCESSING → PENDING_REVIEW → APPROVED
                                                → REJECTED
                                                → INFO_REQUESTED → PROCESSING
```

| Status | Meaning |
|---|---|
| `DRAFT` | Started, not yet submitted; not visible to reviewers |
| `SUBMITTED` | Form received, document not yet processed |
| `PROCESSING` | AI extraction and verification running |
| `PENDING_REVIEW` | Awaiting human reviewer decision |
| `INFO_REQUESTED` | Reviewer needs additional information from the applicant |
| `APPROVED` | Human reviewer approved |
| `REJECTED` | Human reviewer rejected |

## 9. Core Data Entities

| Entity | Key Fields |
|---|---|
| `Application` | id, reference_id, status, submitted_at, applicant fields, account_type, risk_level, flag_count |
| `Document` | id, application_id, file_path, declared_type, detected_type, version, uploaded_at |
| `ExtractionResult` | id, document_id, extracted_fields (JSON), field_confidences (JSON), justification, status, created_at |
| `VerificationResult` | id, application_id, field_name, submitted_value, extracted_value, match_status, justification |
| `RiskAssessment` | id, application_id, risk_level, contributing_factors (JSON), computed_at |
| `Decision` | id, application_id, reviewer_id, action, reasoning, decided_at |
| `AuditLogEntry` | id, application_id, timestamp, actor, action, details |
| `PolicyChunk` | id, source_document, chunk_text, embedding, section_reference |

## 10. Non-Functional Requirements

| Category | Requirement |
|---|---|
| **Explainability** | No AI output surfaces to a user without a human-readable justification |
| **Auditability** | Every state change logged with actor and timestamp; log is append-only |
| **Human oversight** | Approval requires explicit human action; no automatic approval path exists |
| **Graceful degradation** | LLM failure routes to manual review rather than erroring out |
| **Determinism** | Risk scoring and match logic produce identical output for identical input |
| **Performance** | Document extraction target: under 15 seconds per document |
| **Portability** | Runs locally via a single documented setup command |
| **Configuration** | Thresholds, timeouts, and model names configurable without code changes |

## 11. Success Criteria

- A reviewer can take an application from submission to decision in under one minute
- Every decision in the demo has a complete, readable audit trail
- The RAG assistant answers correctly from source documents and declines when it cannot
- The repository is clonable and runnable by a stranger following the README
- An automated test proves no auto-approval path exists
- The project can be explained in a two-minute interview walkthrough

## 12. Build Sequence

Each phase should be fully working before the next begins.

| Phase | Stories | Outcome |
|---|---|---|
| 1 | US-01, US-02, US-04, US-05, US-06 | Applicant can submit an application with a document |
| 2 | US-09, US-10, US-11, US-12, US-13, US-14 | AI extracts and verifies; results persisted |
| 3 | US-19, US-22, US-23, US-24, US-26, US-27 | Reviewer can decide with explanation and audit trail |
| 4 | US-16, US-17, US-18, US-20, US-21 | Risk scoring and queue management |
| 5 | US-29, US-30 | RAG policy assistant |
| 6 | US-03, US-07, US-08, US-15, US-25, US-28 | Completeness: drafts, resubmission loop, export |

Phases 1–3 constitute a demonstrable product. Everything after strengthens it.

## 13. Future Scope

- Insurance underwriting and claims onboarding modules
- Lending, credit assessment, and collections workflows
- Voice-based onboarding assistant
- Real ID verification API integration
- Reviewer decision-consistency analytics

## 14. Open Questions

1. Where does liability sit if an AI extraction error contributes to a wrong approval? *(Design answer: mandatory human sign-off — document in README.)*
2. Should low-confidence extractions be weighted differently from confirmed mismatches in risk scoring?
3. Should risk scoring remain purely rules-based, or incorporate LLM judgement?
