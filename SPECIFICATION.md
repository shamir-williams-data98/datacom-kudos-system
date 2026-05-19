# Kudos System Specification

## Overview

The Kudos System is an internal feature for the Datacom employee portal that enables team members to publicly recognize and appreciate their colleagues. It fosters a positive work culture by making appreciation visible across the organization.

**Repository:** [https://github.com/shamir-williams-data98/datacom-kudos-system](https://github.com/shamir-williams-data98/datacom-kudos-system)

---

## Functional Requirements

### User Stories

1. **US-01**: As a user, I can log in by selecting my name from a list of employees so I can access the dashboard.
2. **US-02**: As a user, I can select another user from a dropdown list to send kudos to.
3. **US-03**: As a user, I can write a short message of appreciation (5–500 characters) and submit it.
4. **US-04**: As a user, I can view a live feed of all recent kudos on the main dashboard.
5. **US-05**: As a user, I cannot send kudos to myself.
6. **US-06**: As a user, I cannot send duplicate kudos to the same person within 5 minutes.
7. **US-07**: As an administrator, I can hide inappropriate kudos messages (soft-delete).
8. **US-08**: As an administrator, I can restore previously hidden kudos messages.
9. **US-09**: As an administrator, I can permanently delete a kudos message.
10. **US-10**: As an administrator, I can view a list of all hidden/moderated kudos.

### Acceptance Criteria

#### US-01: User Login
- A login screen displays a list of all registered employees
- Selecting a name and clicking "Login" establishes a session
- The user's name and role are stored for the duration of the session
- Admin users see additional moderation controls after login

#### US-02: Recipient Selection
- A searchable dropdown displays all employees except the logged-in user
- Each option shows the employee's full name
- Selection is required before submission

#### US-03: Kudos Message Submission
- A textarea accepts messages between 5 and 500 characters
- A live character counter shows remaining characters
- Submission is blocked if validation fails, with inline error messages
- On successful submission, the form resets and the feed updates immediately

#### US-04: Public Kudos Feed
- The dashboard displays the most recent kudos in reverse-chronological order
- Each kudos card shows: sender name, receiver name, message, and timestamp
- The feed auto-refreshes every 15 seconds
- Pagination or "load more" supports viewing older kudos

#### US-05: Self-Kudos Prevention
- The sender is excluded from the recipient dropdown
- Server-side validation rejects kudos where sender_id == receiver_id

#### US-06: Duplicate Prevention
- Server-side check: if same sender → same receiver within last 5 minutes, reject
- User receives a clear error message explaining the cooldown

#### US-07: Hide Kudos (Admin)
- Admin users see a "Hide" button on each kudos card in the feed
- Clicking "Hide" prompts for an optional reason
- Hidden kudos are removed from the public feed immediately
- The `is_visible` flag is set to `false`, with moderation metadata recorded

#### US-08: Restore Kudos (Admin)
- The admin panel shows all hidden kudos
- A "Restore" button sets `is_visible` back to `true`
- The kudos reappears in the public feed

#### US-09: Delete Kudos (Admin)
- A "Delete" button permanently removes a kudos record
- A confirmation dialog prevents accidental deletion

#### US-10: Moderation Dashboard
- Admin users can toggle to a "Moderated" tab
- Shows all hidden kudos with moderation reason, moderator name, and timestamp

---

## Technical Design

### Technology Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Frontend | HTML + CSS + JavaScript | No build tooling needed; single-page app |
| Backend | Python / Flask | Consistent with existing Datacom Python codebase |
| Database | SQLite | Zero-config, file-based, ideal for internal tools |
| Auth | Session-based (simplified) | Internal tool scope |

### Database Schema

#### `users` Table

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | Unique user identifier |
| `name` | TEXT | NOT NULL | Full display name |
| `email` | TEXT | UNIQUE NOT NULL | Email address |
| `role` | TEXT | NOT NULL DEFAULT 'user' | `user` or `admin` |
| `avatar_color` | TEXT | NOT NULL | Hex color code for UI avatar |

#### `kudos` Table

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | Unique kudos identifier |
| `sender_id` | INTEGER | FOREIGN KEY → users.id, NOT NULL | Who sent the kudos |
| `receiver_id` | INTEGER | FOREIGN KEY → users.id, NOT NULL | Who received the kudos |
| `message` | TEXT | NOT NULL | 5–500 characters |
| `created_at` | DATETIME | NOT NULL DEFAULT CURRENT_TIMESTAMP | When it was sent |
| `is_visible` | BOOLEAN | NOT NULL DEFAULT 1 | Moderation flag |
| `moderated_by` | INTEGER | FOREIGN KEY → users.id, NULLABLE | Admin who moderated |
| `moderated_at` | DATETIME | NULLABLE | When moderation occurred |
| `moderation_reason` | TEXT | NULLABLE | Why it was hidden |

### API Endpoints

#### `GET /api/users`
- **Description**: Retrieve all users
- **Response**: `200 OK` — JSON array of user objects
- **Auth**: Any logged-in user

#### `GET /api/kudos`
- **Description**: Retrieve visible kudos feed
- **Query Params**: `page` (default: 1), `per_page` (default: 20)
- **Response**: `200 OK` — JSON object with `kudos` array and `pagination` metadata
- **Auth**: Any logged-in user

#### `POST /api/kudos`
- **Description**: Submit a new kudos
- **Body**: `{ "sender_id": int, "receiver_id": int, "message": string }`
- **Validation**: Message 5–500 chars, sender ≠ receiver, no duplicate within 5 min
- **Response**: `201 Created` — The created kudos object
- **Error Responses**: `400 Bad Request` with error details

#### `PATCH /api/kudos/<id>/hide`
- **Description**: Hide a kudos from the public feed
- **Body**: `{ "moderated_by": int, "reason": string (optional) }`
- **Response**: `200 OK`
- **Auth**: Admin only

#### `PATCH /api/kudos/<id>/restore`
- **Description**: Restore a hidden kudos
- **Body**: `{ "moderated_by": int }`
- **Response**: `200 OK`
- **Auth**: Admin only

#### `DELETE /api/kudos/<id>`
- **Description**: Permanently delete a kudos
- **Response**: `200 OK`
- **Auth**: Admin only

#### `GET /api/kudos/hidden`
- **Description**: List all hidden kudos
- **Response**: `200 OK` — JSON array of hidden kudos with moderation metadata
- **Auth**: Admin only

### Frontend Components

```
App
├── LoginScreen
│   └── UserSelector (dropdown of all employees)
├── Dashboard
│   ├── Header (user info, logout, admin toggle)
│   ├── KudosForm
│   │   ├── RecipientSelector (filtered dropdown)
│   │   ├── MessageTextarea (with char counter)
│   │   └── SubmitButton
│   ├── KudosFeed
│   │   └── KudosCard[] (sender, receiver, message, timestamp, admin actions)
│   └── AdminPanel (toggle-visible for admins)
│       ├── HiddenKudosList
│       └── ModerationActions (restore, delete)
└── ToastNotifications
```

### Security Considerations

- **Input Sanitization**: All user input is HTML-escaped server-side before storage
- **SQL Injection**: Parameterized queries used exclusively
- **XSS Prevention**: Output encoding on the frontend; no `innerHTML` with raw user data
- **CSRF**: Not applicable for API-only architecture with JSON payloads
- **Rate Limiting**: Duplicate submission detection (same sender→receiver within 5 min)

### Performance Considerations

- **Pagination**: Feed is paginated (20 items per page) to limit payload size
- **Auto-refresh**: 15-second polling interval balances freshness vs. server load
- **Indexing**: Database indexes on `kudos.created_at`, `kudos.sender_id`, `kudos.receiver_id`
- **Lightweight**: SQLite + Flask has minimal overhead for internal tool scale

### Error Handling & Logging

- All API errors return structured JSON: `{ "error": string, "details": string }`
- Python `logging` module used for server-side logging
- Frontend displays user-friendly toast notifications for all error/success states

---

## Implementation Plan

### Task Breakdown

1. **Database Layer** (`database.py`)
   - Define schema creation SQL
   - Write seed data insertion (8 employees + 1 admin)
   - Build query helper functions

2. **API Server** (`app.py`)
   - Initialize Flask app with SQLite connection
   - Implement all 7 API endpoints
   - Add input validation and error handling
   - Add duplicate detection logic

3. **Frontend Design System** (`static/styles.css`)
   - Define CSS custom properties (colors, spacing, typography)
   - Build component styles (cards, forms, buttons, modals)
   - Add animations and responsive breakpoints

4. **Frontend Structure** (`static/index.html`)
   - Login screen layout
   - Dashboard with form + feed columns
   - Admin panel section

5. **Frontend Logic** (`static/app.js`)
   - Session management
   - API integration layer
   - Dynamic DOM rendering
   - Form validation
   - Auto-refresh mechanism
   - Admin moderation actions

6. **Dependencies** (`requirements.txt`)
   - List Python packages

### Dependencies Between Tasks

```
database.py → app.py → static/styles.css → static/index.html → static/app.js
```

### Testing Strategy

- Manual API testing via browser
- Browser-based UI walkthrough covering all user stories
- Edge case testing: self-kudos, duplicates, empty messages, XSS attempts
