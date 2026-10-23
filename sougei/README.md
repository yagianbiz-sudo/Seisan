# Okurimukae-chō (送り迎え帳)

A shared drop-off/pick-up notebook for couples. It shows in numbers who took the kids to and from daycare, and lets either partner request a change with a "trade card".

## What the prototype can do (v0.1)

- **Basic schedule**: register drop-offs and pick-ups for each weekday and each child. The schedule fills in every day automatically.
- **Daily duties**: tap any duty for an upcoming day to see who is in charge. A day can also be marked as "no drop-off/pick-up" (holidays, closures).
- **Trade requests**
  - Only the person currently in charge of a duty can **request** a trade. Nothing changes until the partner taps "Accept".
  - The requester can add a **return favor** ("in exchange, I'll take this duty").
  - Before sending, the screen shows **"If accepted"**: exactly which duty moves to whom.
  - No return favor means the requester **owes one**. Volunteering to take over the partner's duty means they **owe you one**.
- **Totals**: monthly drop-off/pick-up counts per partner, the gap between them, a ratio bar, and a breakdown by child and by drop-off vs. pick-up.

Being able to take on extra work but never push it onto the other person is deliberate. It stops one person from casually saying "I've got this one" and leaving their spouse with the rest.

## How data is stored

- Opened as a Claude artifact: both partners share the same data (the `db` capability).
- Opened directly as `index.html`: data is saved only in that phone's browser.
- Each phone asks once who is using it.

## Toward the public app (draft)

1. **Try it as a couple for 2–4 weeks** with this prototype and find what's hard to use or missing.
2. Turn it into an app: React Native (Expo) or a PWA, with Firebase/Supabase for login, data, and **push notifications** (so "You have a trade request" reaches the phone).
3. A pairing flow that links two accounts with an invite code.
4. Candidates: rain-day rules, linking business trips to the calendar, a monthly report, setups with three or more caregivers (e.g. grandparents).
