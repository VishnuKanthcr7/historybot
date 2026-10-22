# Student accounts without email (roll numbers)

Added 22 Oct 2026 (migration `007_student_roll`).

## How students sign up and log in
- **Sign up:** full name, roll number, password, confirm password. No email and no phone number.
- **Roll number:** exactly two digits, `01` to `99`. It is stored as text, so `07` stays `07`.
  `7`, `00`, `100` and letters are rejected with a simple message.
- **Password:** at least 8 characters, hashed with the existing scrypt helper (`backend/src/services/passwords.js`).
- **Log in:** roll number + password.
- Students who signed up **with an email before this change** can still log in: on the login page choose
  "Signed up earlier with an email? Use email instead". Their accounts, chats and scores are unchanged.
- Teachers log in with email + password exactly as before (Teacher login). There is still no public teacher sign-up.

## Cohorts (which class/group a roll number belongs to)
Before this change the database had **no class, section or school field** (users only had email, name, role).
Roll numbers repeat across classes, so each account now also has a `cohort_code`:

- New sign-ups get the cohort set on the server in `.env`: `STUDENT_COHORT=class9-default` (the default if unset).
- Roll numbers are unique **within a cohort** (database unique key `uq_users_cohort_roll (cohort_code, roll_number)`).
  A second student trying to register roll `07` in the same cohort is told the roll number is already registered.
- When a new class or research group starts (for example a second school), set a new value such as
  `STUDENT_COHORT=class9-2026-schoolB` and restart the backend. Students of the earlier cohort then cannot log in by
  roll number on that server until it is switched back, so **one server = one active cohort**. If two groups must use
  the site at the same time, a cohort chooser on the login page is needed (not built; ask if required).
- Older email accounts have no roll number and no cohort (`NULL`); they never clash with roll numbers.

## Database change (additive only)
`backend/scripts/migrate-007.mjs` (backs up with mysqldump first, idempotent):
- `users.email` becomes NULL-able (existing emails kept; unique key on email unchanged).
- adds `users.roll_number VARCHAR(2) NULL`, `users.cohort_code VARCHAR(40) NULL`,
  unique key `(cohort_code, roll_number)` and check `roll_number` is two digits and not `00`.
- No table is dropped, no row is changed or deleted.

Status: applied and tested on a **test copy** (`historybot_test13`). **Not yet applied to the live database**: that
needs approval, and must be done before the live backend is restarted with the new code.

Apply (after approval):
```
cd C:\Users\vkant\Projects\historybot
node backend\scripts\migrate-007.mjs
```

## Rate limiting
Sign-up/log-in is limited per IP address. Because a whole class may sign up from one school network, only **failed**
attempts are counted now (15 per 15 minutes per IP by default; `AUTH_RATE_MAX` overrides).

## Test-only switch
`STUDENT_EMAIL_SIGNUP=1` re-enables the old email sign-up so the older automated test suites can run. Set it only on
test instances (port 3100). Never in production.
