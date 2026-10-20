# Kobi ERP Bot - Taxi & Courier Dispatch Web System

A comprehensive React-based ERP dispatch and management system rewritten from the Python (`aiogram` + `aiosqlite`) Telegram bot `telegram-kobi-bot`.

## 🚖 Preserved Core Features & Business Logic

### 1. Role-Based Access & Permissions (RBAC)
- **Admin / God Mode (`admin`)**:
  - Full authority across all stations.
  - Creation of new stations with custom commission percentages.
  - User role promotion/demotion and station assignment (`admin`, `station_manager`, `dispatcher`, `user`, or `blocked`).
  - Driver debt appeal approval (clearing debt) or rejection.
  - System-wide global broadcast announcement to all users.
- **Station Manager (`station_manager`)**: Station oversight and driver coordination.
- **Dispatcher (`dispatcher`)**:
  - Order publisher with real-time text cleaning (auto-replaces arrows `->`, expands common abbreviations like `פת` -> `פתח תקווה`, `ים` -> `ירושלים`, `ספר` -> `מודיעין עילית`).
  - Automated price detection regex (`\b\d{2,4}\b`).
  - Target selection: Private drivers (filtered by driver active work zones, `free` status, and debt balance <= 500) or external groups.
  - Open orders monitoring and deletion.
  - Driver candidate evaluation (view driver rating, car model, seats, and submitted ETA).
  - One-click approval triggering automated station commission tracking, debt ledger entry, and prompt for driver rating (1–5 stars).
- **Driver / Courier (`user`)**:
  - Profile card with rating, total completed trips, vehicle specs, seats, and current debt balance.
  - Status toggle (`🟢 פנוי לעבודה` / `🔴 תפוס (עצור קריאות)`).
  - **Auto-Freeze Protection**: If driver debt balance exceeds 500 NIS, status switch to "free" is blocked until debt is paid or appealed.
  - **Work Zones (אזורי עבודה)**: Drivers manage their active cities. Orders targeting matching cities are sent to them.
  - **ETA Bidding**: Drivers receive calls and submit estimated arrival time in minutes.
  - **Debts & Appeals (חיובים וערעורים)**: Drivers inspect commission debts and file formal dispute appeals for admin review.
  - **Onboarding Wizard**: 7-step registration flow verifying name, birth year (18+), Israeli phone validation, vehicle brand, model, year, and seat count.

### 2. Live Telegram Bot Simulator
- Pixel-perfect Telegram dark-mode interface.
- Executes the exact `aiogram` FSM flows (`Reg`, `OrderFlow`, `DebtFlow`, `AdminFlow`, `DriverFlow`).
- Inline buttons and persistent reply keyboards.

## 🚀 Running the App
- Dev Server: `npm run dev` (Port 3000, Host 0.0.0.0)
- Production Build: `npm run build`
