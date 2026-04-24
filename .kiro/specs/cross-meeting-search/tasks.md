# Implementation Plan: Cross-Meeting Search

## Phase 1 — Meeting Title Foundation

- [ ] 1.1 Add `meeting_title` column to `meeting_summaries` table
  - In `init_db()` in `app/services/chat_memory.py`, add `ALTER TABLE meeting_summaries ADD COLUMN IF NOT EXISTS meeting_title VARCHAR(80)` following the existing pattern
  - _Requirements: 1.1, 1.3_

- [ ] 1.2 Implement `_derive_title()` helper in `app/services/chat_memory.py`
  - Extract first `##` heading from summary; if none, take first sentence truncated to 80 chars
  - Fall back to `"Meeting on {formatted_started_at}"` when summary is empty
  - Fall back to `"Untitled Meeting"` when both are absent
  - _Requirements: 1.1, 1.2, 1.4, 1.5_

- [ ] 1.3 Add `save_meeting_title()` async function to `app/services/chat_memory.py`
  - `save_meeting_title(user_id: str, meeting_id: str, title: str) -> None`
  - UPSERTs the `meeting_title` column for the given user/meeting row
  - _Requirements: 1.1_

- [ ] 1.4 Update `list_meetings()` to return a `title` field
  - LEFT JOIN `meeting_summaries` to fetch `meeting_title`; fall back to `_derive_title(None, started_at)` if NULL
  - Add `title` key to each dict in the returned list
  - _Requirements: 1.3_

- [ ] 1.5 Update `MeetingListItem` Pydantic model in `app/routes/meeting.py`
  - Add `title: str` field with default `""` so existing callers don't break
  - _Requirements: 1.3_

---

## Phase 2 — Wire Title Generation into Summary Saving

- [ ] 2.1 Call `save_meeting_title()` after final summary is saved in `app/routes/meeting.py`
  - After `await save_meeting_summary(...)`, derive title with `_derive_title(final_summary, datetime.now())` and persist it
  - _Requirements: 1.1_

- [ ] 2.2 Write unit tests for `_derive_title()`
  - Test: summary with `## Heading` → heading is the title
  - Test: summary with no heading → first sentence (≤80 chars) is the title
  - Test: empty summary + started_at → `"Meeting on ..."` fallback
  - Test: empty summary + no started_at → `"Untitled Meeting"` fallback
  - _Requirements: 1.1, 1.2, 1.4, 1.5_

- [ ] 2.3 Write unit test for `save_meeting_title()` and `list_meetings()` title field
  - Test that after saving a summary + title, `list_meetings()` returns the correct `title`
  - Test that a meeting with no summary row returns a non-empty fallback title
  - _Requirements: 1.3_

- [ ] 2.4 Run Phase 1 + 2 tests and confirm they pass before proceeding

---

## Phase 3 — MeetingSearchService: Models + Temporal Resolution

- [ ] 3.1 Create `app/services/meeting_search.py` with Pydantic models
  - `SourceMeeting(BaseModel)`: `meeting_id: str`, `title: str`, `started_at: str | None`
  - `CrossMeetingSearchResult(BaseModel)`: `answer: str`, `sources: list[SourceMeeting]`, `temporal_range: str | None`
  - _Requirements: 5.2_

- [ ] 3.2 Implement `resolve_meetings()` in `app/services/meeting_search.py`
  - Build prompt with today's UTC datetime + meeting list (truncated to 50 most recent)
  - Ask LLM for JSON: `{"has_temporal": bool, "start_iso": str|null, "end_iso": str|null, "description": str|null}`
  - If `has_temporal` is false → return `(None, None)`
  - Filter meeting list to IDs whose `started_at` falls in `[start_iso, end_iso]` → return `(matching_ids, description)`
  - On any failure → return `(None, None)` (unfiltered fallback)
  - Use `temperature=0` for determinism
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

- [ ] 3.3 Write unit tests for `resolve_meetings()`
  - Test: query with temporal ref → returns subset of input meeting IDs
  - Test: query with no temporal ref → returns `(None, None)`
  - Test: meeting list > 50 entries → only 50 most recent passed to LLM
  - Test: LLM failure → returns `(None, None)` gracefully
  - _Requirements: 2.2, 2.4, 2.5, 2.6_

- [ ] 3.4 Run Phase 3 tests and confirm they pass before proceeding

---

## Phase 4 — MeetingSearchService: Full Pipeline

- [ ] 4.1 Implement `cross_meeting_search()` in `app/services/meeting_search.py`
  - Call `list_meetings(user_id)` → if empty, return early with "no meeting history" answer
  - Call `resolve_meetings()` → get `(meeting_ids, temporal_range)`
  - If `meeting_ids == []` → return "no meetings found in {temporal_range}" answer, `sources=[]`
  - If `meeting_ids is None` → `query_meetings(user_id, query, n_results=10)` unfiltered
  - Otherwise → `query_meetings()` per resolved ID, merge results, cap at 10 chunks
  - Build LLM prompt with chunks annotated by meeting title + date
  - Build `sources` list from meetings whose chunks appeared; return `CrossMeetingSearchResult`
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 6.1, 6.2, 6.3_

- [ ] 4.2 Write unit tests for `cross_meeting_search()`
  - Test: user with no meetings → graceful "no history" response
  - Test: temporal ref resolves to empty window → "no meetings found" response
  - Test: unfiltered search → sources list populated from results
  - Test: LLM unavailable during synthesis → raw excerpts returned with notice
  - _Requirements: 3.2, 3.3, 3.6, 6.2, 6.3_

- [ ] 4.3 Run Phase 4 tests and confirm they pass before proceeding

---

## Phase 5 — API Endpoint

- [ ] 5.1 Add `MeetingSearchRequest` model and `POST /meeting/search` endpoint to `app/routes/meeting.py`
  - `MeetingSearchRequest`: `query: str`, `date_hint: str | None = None`
  - Register route **before** any `/{meeting_id}/...` routes to avoid path param collision
  - Call `cross_meeting_search(user_id, query, date_hint)` and return result
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [ ] 5.2 Write unit tests for `POST /meeting/search`
  - Test: unauthenticated → 401
  - Test: empty query → 422
  - Test: valid request → returns `CrossMeetingSearchResult` shape
  - Test: `date_hint` is forwarded to the service
  - _Requirements: 5.1, 5.2, 5.3, 5.5_

- [ ] 5.3 Run Phase 5 tests and confirm they pass before proceeding

---

## Phase 6 — Frontend

- [ ] 6.1 Update `MeetingContext` to route cross-meeting queries to `POST /meeting/search`
  - When `meetingId` is `"any"`, `"recent"`, or `"latest"`, call `POST /meeting/search` with `{ query, date_hint: null }`
  - Otherwise keep existing `POST /meeting/{meetingId}/chat` call unchanged
  - Map `CrossMeetingSearchResult.answer` to the assistant message
  - _Requirements: 4.1, 4.2_

- [ ] 6.2 Render source citations in the Meeting page chat tab
  - When response contains non-empty `sources`, render a collapsible "Sources" section below the answer
  - Each source shows `title` and formatted `started_at`
  - _Requirements: 4.4_

- [ ] 6.3 Manual smoke test: ask "what was discussed in the last meeting?" and verify a sourced answer appears

---

## Notes

- `/meeting/search` must be declared before `/{meeting_id}/...` routes — FastAPI matches top-down
- `resolve_meetings()` uses `temperature=0` — deterministic JSON parsing is critical
- `ADD COLUMN IF NOT EXISTS` pattern is already established in `init_db()` — follow it exactly
- Phase checkpoints (2.4, 3.4, 4.3, 5.3) are gates — don't proceed if tests are red
