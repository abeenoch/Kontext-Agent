# Requirements Document

## Introduction

The cross-meeting search feature enables users to query across all of their past meetings using natural language, including temporal references like "last Tuesday" or "this week". It adds a human-readable title to each meeting and provides a two-step retrieval pipeline that first resolves which meetings match a time or topic reference, then performs semantic search scoped to those meetings. The feature surfaces exclusively from the Meeting page's "Chat with Transcript" tab — the general Chat page is out of scope and retains its existing document-only behavior.

## Glossary

- **Meeting_Resolver**: The component responsible for mapping a natural language temporal or topic reference to one or more meeting IDs from the user's meeting list.
- **Cross_Meeting_Search**: The end-to-end pipeline that accepts a natural language query, resolves relevant meetings, and returns semantically matched content from those meetings.
- **Meeting_Title**: A short, human-readable label derived from the meeting summary or transcript, stored alongside the meeting record.
- **Temporal_Reference**: A natural language phrase that refers to a point or range in time (e.g., "yesterday", "last Tuesday", "this week").
- **Meeting_Context**: The structured list of a user's meetings including meeting_id, started_at timestamp, and title, passed to the LLM to enable temporal resolution.
- **Meeting_Page**: The per-meeting UI that contains the "Chat with Transcript" tab.
- **Semantic_Search**: Vector similarity search over meeting embeddings in ChromaDB via `query_meetings()`.
- **LLM**: The large language model (Groq) used for natural language understanding and response generation.

---

## Requirements

### Requirement 1: Meeting Title Generation

**User Story:** As a user, I want each meeting to have a short human-readable title, so that I can identify and reference meetings naturally without memorizing hex IDs.

#### Acceptance Criteria

1. WHEN a meeting's final summary is saved, THE Meeting_Title SHALL be derived from the first meaningful sentence or heading of the summary and stored alongside the meeting record.
2. WHEN no summary exists for a meeting, THE Meeting_Title SHALL fall back to a formatted version of the meeting's `started_at` timestamp (e.g., "Meeting on Apr 14, 2026 at 2:30 PM").
3. THE `list_meetings()` function SHALL return a `title` field for every meeting in its response.
4. WHEN a meeting title is generated, THE Meeting_Title SHALL be no longer than 80 characters.
5. IF a meeting has no transcript and no summary, THEN THE Meeting_Title SHALL default to "Untitled Meeting" followed by the formatted `started_at` timestamp.

---

### Requirement 2: Temporal Meeting Resolution

**User Story:** As a user, I want to ask questions using natural language time references like "yesterday" or "last Tuesday", so that the system can identify which meetings I am referring to without me needing to know meeting IDs.

#### Acceptance Criteria

1. WHEN a query contains a temporal reference, THE Meeting_Resolver SHALL receive the current server-side date and time in UTC alongside the full meeting list (meeting_id, started_at, title) to resolve the reference.
2. WHEN the LLM resolves a temporal reference, THE Meeting_Resolver SHALL return a list of meeting IDs whose `started_at` falls within the resolved time window.
3. WHEN a temporal reference resolves to zero meetings, THE Meeting_Resolver SHALL return an empty list and signal that no meetings were found for that time window.
4. WHEN a query contains no temporal reference, THE Meeting_Resolver SHALL treat the query as a topic-only search and skip temporal filtering.
5. WHEN the meeting list passed to the LLM exceeds 50 entries, THE Meeting_Resolver SHALL truncate to the 50 most recent meetings ordered by `started_at` descending.
6. IF the LLM fails to parse the temporal reference, THEN THE Meeting_Resolver SHALL fall back to an unfiltered semantic search across all meetings.

---

### Requirement 3: Cross-Meeting Semantic Search

**User Story:** As a user, I want to ask questions that span multiple past meetings, so that I can find decisions, action items, or topics without knowing which specific meeting they came from.

#### Acceptance Criteria

1. WHEN a cross-meeting query is received, THE Cross_Meeting_Search SHALL perform Semantic_Search scoped to the meeting IDs returned by the Meeting_Resolver.
2. WHEN the Meeting_Resolver returns an empty list due to no temporal match, THE Cross_Meeting_Search SHALL return a response indicating no meetings were found for the specified time period rather than searching all meetings.
3. WHEN the Meeting_Resolver returns an empty list because no temporal reference was present, THE Cross_Meeting_Search SHALL perform an unfiltered Semantic_Search across all of the user's meetings.
4. WHEN semantic search results are returned, THE Cross_Meeting_Search SHALL include the meeting title and formatted date in the LLM context so the response can cite which meeting the information came from.
5. THE Cross_Meeting_Search SHALL return a minimum of 5 and a maximum of 10 semantically relevant chunks per query.
6. WHEN no semantically relevant content is found across any meeting, THE Cross_Meeting_Search SHALL return a response stating that no relevant content was found.

---

### Requirement 4: Cross-Meeting Search from the Meeting Page

**User Story:** As a user on the Meeting page, I want to ask questions that reference other past meetings, so that I can compare or connect information across meetings without leaving the page.

#### Acceptance Criteria

1. WHEN a user submits a query on the Meeting page chat tab with `meeting_id` set to `"any"`, `"recent"`, or `"latest"`, THE Meeting_Page SHALL route the query through Cross_Meeting_Search.
2. WHEN a user submits a query on the Meeting page chat tab with a specific `meeting_id`, THE Meeting_Page SHALL continue to scope the search to that single meeting (existing behavior preserved).
3. WHEN a cross-meeting query is submitted from the Meeting page, THE Meeting_Page SHALL support temporal references using the same Meeting_Resolver pipeline.
4. WHEN a cross-meeting response is returned to the Meeting page, THE Meeting_Page SHALL include the source meeting title and date in the response so the user knows which meeting the answer came from.

---

### Requirement 5: Meeting Search API Endpoint

**User Story:** As a developer, I want a dedicated API endpoint for cross-meeting search, so that the Meeting page can call a single, well-defined endpoint for all cross-meeting queries.

#### Acceptance Criteria

1. THE system SHALL expose a `POST /meeting/search` endpoint that accepts a `query` string and an optional `date_hint` string.
2. WHEN `POST /meeting/search` is called, THE system SHALL execute the full Cross_Meeting_Search pipeline and return a structured response containing the answer and a list of source meetings (meeting_id, title, started_at).
3. WHEN the `date_hint` parameter is provided, THE Meeting_Resolver SHALL use it as the reference date instead of the current server time.
4. IF the authenticated user has no meetings, THEN THE system SHALL return a response indicating no meeting history is available.
5. THE `POST /meeting/search` endpoint SHALL require authentication and SHALL only search meetings belonging to the authenticated user.

---

### Requirement 6: Graceful Fallback and Error Handling

**User Story:** As a user, I want clear and helpful responses when my query doesn't match any meetings, so that I understand what happened and can refine my question.

#### Acceptance Criteria

1. WHEN a temporal reference resolves to a date range with no meetings, THE system SHALL respond with a message that includes the resolved date range and states no meetings were found in that period.
2. WHEN the LLM is unavailable during temporal resolution, THE system SHALL fall back to unfiltered semantic search and include a notice that temporal filtering was skipped.
3. WHEN the LLM is unavailable during response generation, THE system SHALL return the raw semantic search excerpts with a notice that the LLM is temporarily unavailable.
4. WHEN a cross-meeting search returns results from multiple meetings, THE system SHALL clearly attribute each piece of information to its source meeting in the response.
