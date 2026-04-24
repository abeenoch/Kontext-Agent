# Design Document: Cross-Meeting Search

## Overview

Cross-meeting search adds temporal and topic-based querying across all of a user's past meetings, surfaced exclusively from the Meeting page's "Chat with Transcript" tab. The core idea is a two-step pipeline: first resolve which meetings are relevant (by time window or topic), then run semantic search scoped to those meetings and synthesize a response with source attribution.

The feature introduces:
- A `meeting_title` column on `meeting_summaries` (derived at summary-save time)
- A `MeetingSearchService` that encapsulates the two-step pipeline
- A `POST /meeting/search` endpoint that the Meeting page calls for cross-meeting queries
- An upgrade to `list_meetings()` to return titles
- Frontend changes to `MeetingPage.jsx` to route `any/recent/latest` queries to the new endpoint

---

## Architecture

```mermaid
flowchart TD
    A[MeetingPage.jsx\nChat Tab] -->|meeting_id = any/recent/latest| B[POST /meeting/search]
    A -->|specific meeting_id| C[POST /meeting/{id}/chat\nexisting, unchanged]

    B --> D[MeetingSearchService]
    D --> E[list_meetings\nwith titles]
    D --> F[Meeting_Resolver\nLLM temporal parse]
    F -->|meeting IDs| G[query_meetings\nChromaDB]
    G --> H[LLM response\nwith attribution]
    H --> B
```

The existing `POST /meeting/{meeting_id}/chat` endpoint is **not modified**. The new `POST /meeting/search` endpoint handles all cross-meeting queries. The frontend decides which endpoint to call based on whether `meeting_id` is a special token or a real ID.

---

## Components and Interfaces

### 1. `app/services/meeting_search.py` (new)

The central service. Contains two functions:

```python
async def resolve_meetings(
    user_id: str,
    query: str,
    reference_dt: datetime,
    meetings: list[dict],  # [{meeting_id, started_at, title}, ...]
) -> tuple[list[str] | None, str | None]:
    """
    Use the LLM to extract a time window from the query and return matching meeting IDs.

    Returns:
        (meeting_ids, resolved_range_description)
        - meeting_ids: list of IDs, empty list if temporal match found nothing,
          or None if no temporal reference detected (caller should do unfiltered search)
        - resolved_range_description: human-readable string like "Tuesday Apr 15" or None
    """

async def cross_meeting_search(
    user_id: str,
    query: str,
    date_hint: str | None = None,
) -> CrossMeetingSearchResult:
    """
    Full pipeline: resolve → semantic search → LLM synthesis.
    """
```

**`CrossMeetingSearchResult`** (Pydantic model):
```python
class SourceMeeting(BaseModel):
    meeting_id: str
    title: str
    started_at: str | None

class CrossMeetingSearchResult(BaseModel):
    answer: str
    sources: list[SourceMeeting]
    temporal_range: str | None  # e.g. "Tuesday Apr 15" — None if no temporal ref
```

### 2. `app/routes/meeting.py` — new endpoint

```python
class MeetingSearchRequest(BaseModel):
    query: str
    date_hint: str | None = None  # ISO datetime string, overrides server time

@router.post("/search", response_model=CrossMeetingSearchResult)
async def meeting_search(
    request: MeetingSearchRequest,
    current_user: str = Depends(get_current_user),
) -> CrossMeetingSearchResult:
    ...
```

Note: `/meeting/search` must be registered **before** `/{meeting_id}/...` routes to avoid FastAPI treating `"search"` as a meeting_id path parameter.

### 3. `app/services/chat_memory.py` — changes

- Add `meeting_title` column to `meeting_summaries` table (via `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`).
- Add `save_meeting_title(user_id, meeting_id, title)` helper.
- Update `list_meetings()` to JOIN/query `meeting_summaries.meeting_title` and include it in the returned dict.

### 4. `app/services/summarizer.py` — changes

After saving the final summary, derive and persist the title:

```python
title = _derive_title(summary_text, started_at)
await save_meeting_title(user_id, meeting_id, title)
```

`_derive_title` extracts the first `##` heading or first sentence ≤ 80 chars from the summary. Falls back to `"Meeting on {formatted_started_at}"`.

### 5. `frontend/src/pages/MeetingPage.jsx` — changes

The existing chat tab already sends `POST /meeting/{meeting_id}/chat`. Change the routing logic:

```js
const endpoint =
  ["any", "recent", "latest"].includes(meetingId)
    ? "/meeting/search"
    : `/meeting/${meetingId}/chat`;
```

For `/meeting/search`, the request body is `{ query, date_hint: null }`. The response shape is `CrossMeetingSearchResult` — render `answer` as the assistant message and optionally show `sources` as a collapsible citation list.

---

## Data Models

### `meeting_summaries` table — new column

```sql
ALTER TABLE meeting_summaries
ADD COLUMN IF NOT EXISTS meeting_title VARCHAR(80);
```

No migration file needed — `init_db()` already uses `ADD COLUMN IF NOT EXISTS` for schema evolution (see existing pattern in `chat_memory.py`).

### Updated `list_meetings()` return shape

```python
{
    "meeting_id": str,
    "started_at": str | None,
    "has_summary": bool,
    "title": str,          # new field
}
```

### `MeetingListItem` Pydantic model — new field

```python
class MeetingListItem(BaseModel):
    meeting_id: str
    started_at: str | None
    has_summary: bool
    title: str             # new field
```

---

## Correctness Properties

A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.

Property 1: Title length invariant
*For any* meeting summary text, the derived title SHALL be at most 80 characters long.
**Validates: Requirements 1.4**

Property 2: Title fallback completeness
*For any* meeting record, `list_meetings()` SHALL return a non-empty `title` string — never `None` or `""`.
**Validates: Requirements 1.2, 1.3, 1.5**

Property 3: Temporal resolution scoping
*For any* user with N meetings and a query containing a temporal reference that resolves to a non-empty window, the meeting IDs returned by `resolve_meetings()` SHALL be a subset of the user's full meeting list.
**Validates: Requirements 2.2**

Property 4: No-temporal-reference pass-through
*For any* query that contains no temporal reference, `resolve_meetings()` SHALL return `None` (not an empty list), signalling the caller to perform an unfiltered search.
**Validates: Requirements 2.4**

Property 5: Meeting list truncation
*For any* user with more than 50 meetings, the meeting list passed to the LLM by `resolve_meetings()` SHALL contain exactly 50 entries, ordered by `started_at` descending.
**Validates: Requirements 2.5**

Property 6: Source attribution completeness
*For any* `CrossMeetingSearchResult` where `sources` is non-empty, every `SourceMeeting` in `sources` SHALL have a non-empty `title` and a non-None `meeting_id`.
**Validates: Requirements 3.4, 4.4**

Property 7: Search result chunk count bounds
*For any* cross-meeting search that returns results, the number of semantic chunks passed to the LLM context SHALL be between 5 and 10 inclusive.
**Validates: Requirements 3.5**

---

## Error Handling

| Scenario | Behavior |
|---|---|
| LLM unavailable during temporal resolution | Catch exception, skip temporal filtering, set `temporal_range=None`, proceed with unfiltered semantic search, prepend notice to answer |
| LLM unavailable during response synthesis | Return raw chunk excerpts joined with `\n\n---\n\n`, prepend "LLM temporarily unavailable" notice |
| User has no meetings | Return `CrossMeetingSearchResult(answer="You have no meeting history yet.", sources=[], temporal_range=None)` |
| Temporal reference resolves to empty window | Return answer stating the resolved date range and that no meetings were found; `sources=[]` |
| ChromaDB query fails | Log warning, return graceful "no relevant content found" answer |
| `date_hint` is malformed ISO string | Return HTTP 422 with validation error from Pydantic |

---

## Testing Strategy

### Unit tests

- `_derive_title()`: test with summary containing `##` heading, plain prose, empty string, very long first sentence.
- `resolve_meetings()`: mock `query_llm` to return structured JSON; test temporal match, no-match, no-temporal-ref, and LLM failure paths.
- `cross_meeting_search()`: mock `list_meetings`, `resolve_meetings`, `query_meetings`, `query_llm`; test full pipeline happy path and each fallback branch.
- `list_meetings()`: test that `title` field is present and non-empty for meetings with and without summaries.

### Property-based tests (pytest + Hypothesis)

Each property test runs a minimum of 100 iterations.

- **Property 1** — `test_title_length_invariant`
  Generate random summary strings (including empty, whitespace-only, very long). Assert `len(_derive_title(s, dt)) <= 80`.
  Tag: `Feature: cross-meeting-search, Property 1: title length invariant`

- **Property 2** — `test_title_fallback_completeness`
  Generate random meeting records (with/without summary, with/without started_at). Assert `title` in result is truthy.
  Tag: `Feature: cross-meeting-search, Property 2: title fallback completeness`

- **Property 3** — `test_temporal_resolution_scoping`
  Generate random meeting lists and temporal queries. Mock LLM to return a subset of IDs. Assert returned IDs ⊆ input meeting IDs.
  Tag: `Feature: cross-meeting-search, Property 3: temporal resolution scoping`

- **Property 4** — `test_no_temporal_reference_returns_none`
  Generate queries with no time words. Assert `resolve_meetings()` returns `(None, None)`.
  Tag: `Feature: cross-meeting-search, Property 4: no-temporal-reference pass-through`

- **Property 5** — `test_meeting_list_truncation`
  Generate meeting lists with more than 50 entries. Assert the list passed to the LLM has exactly 50 entries and they are the 50 most recent by `started_at`.
  Tag: `Feature: cross-meeting-search, Property 5: meeting list truncation`

- **Property 6** — `test_source_attribution_completeness`
  Generate random `CrossMeetingSearchResult` instances with non-empty sources. Assert every source has non-empty `title` and `meeting_id`.
  Tag: `Feature: cross-meeting-search, Property 6: source attribution completeness`

- **Property 7** — `test_chunk_count_bounds`
  Generate random semantic search results with varying chunk counts. Assert the number of chunks passed to the LLM is clamped between 5 and 10.
  Tag: `Feature: cross-meeting-search, Property 7: search result chunk count bounds`

### Integration tests

- `POST /meeting/search` with a mocked `cross_meeting_search` — verify auth, request validation, response shape.
- End-to-end: seed meetings in test DB + ChromaDB, call `/meeting/search`, assert answer references correct meeting titles.
