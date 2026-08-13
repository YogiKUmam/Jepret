# Jepret Phase 5 Quality Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Menutup seluruh temuan quality review Phase 5 dengan backend environment fail-closed, jalur payment kreator yang dapat dicapai dari UI, dan payment E2E yang tahan retry/rerun.

**Architecture:** Pertahankan modular monolith dan payment state machine yang ada. Jadikan environment API sebagai startup requirement, tambahkan link route payment pada booking card kreator tanpa memindahkan authorization dari backend, lalu buat E2E memilih tanggal kosong dari endpoint incoming booking sebelum menjalankan product flow melalui UI.

**Tech Stack:** Python 3.13, FastAPI, Pydantic Settings, pytest, TypeScript strict, Next.js 16, React 19, TanStack Query, Vitest/Testing Library, Playwright, Docker Compose.

**Design:** `docs/superpowers/specs/2026-08-13-jepret-phase-5-quality-remediation-design.md`

---

## File map

- `apps/api/app/core/config.py` — kontrak environment API; environment harus eksplisit.
- `apps/api/tests/test_config.py` — unit proof untuk environment required dan accepted values.
- `apps/web/src/app/booking/masuk/page.tsx` — CTA kreator untuk membuka payment page.
- `apps/web/src/app/booking/masuk/page.test.tsx` — component proof status mana yang menampilkan CTA.
- `apps/web/e2e/booking.spec.ts` — setup tanggal kosong, semantic locator, dan release/refund journeys.
- `docker-compose.yml` — build argument frontend yang dapat dioverride dengan default development.
- `.env.example` — contoh environment dan penjelasan Compose.
- `README.md` — alur sandbox serta wording security yang sesuai perilaku aktual.
- `docs/testing.md` — environment wajib untuk test backend langsung dan repeat-run E2E command.
- `docs/implementation-plan.md` — bukti verifikasi aktual setelah semua gate selesai.

Tidak ada perubahan schema database atau Alembic migration.

---

### Task 1: Make API environment fail closed

**Files:**
- Modify: `apps/api/tests/test_config.py`
- Modify: `apps/api/app/core/config.py:14-23`

- [ ] **Step 1: Write the failing configuration test**

Tambahkan helper dan test berikut ke `apps/api/tests/test_config.py`. `_env_file=None` mencegah file lokal menyamarkan requirement; `monkeypatch.delenv` mencegah shell environment menyamarkannya.

```python
def complete_settings_input() -> dict[str, str]:
    return {
        "database_url": "postgresql+asyncpg://jepret:jepret@db:5432/jepret",
        "public_origin": "http://localhost:8080",
        "minio_endpoint": "http://minio:9000",
        "minio_access_key": "minioadmin",
        "minio_secret_key": "minioadmin",
    }


def test_settings_require_explicit_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JEPRET_ENVIRONMENT", raising=False)

    with pytest.raises(ValidationError, match="environment"):
        Settings(_env_file=None, **complete_settings_input())  # type: ignore[arg-type]
```

Ubah existing tests agar memakai helper dan environment eksplisit:

```python
def test_settings_accept_complete_development_environment() -> None:
    settings = Settings(
        _env_file=None,
        environment=Environment.DEVELOPMENT,
        **complete_settings_input(),
    )  # type: ignore[arg-type]
    assert settings.environment is Environment.DEVELOPMENT
    assert settings.redis_url is None


def test_settings_reject_wildcard_public_origin() -> None:
    with pytest.raises(ValidationError, match="public_origin"):
        Settings(
            _env_file=None,
            environment=Environment.TEST,
            **{**complete_settings_input(), "public_origin": "*"},
        )  # type: ignore[arg-type]
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```powershell
$env:JEPRET_ENVIRONMENT='development'
uv run --project apps/api pytest apps/api/tests/test_config.py::test_settings_require_explicit_environment -q
```

Expected: FAIL because `Settings` still supplies `Environment.DEVELOPMENT` when environment is omitted.

- [ ] **Step 3: Remove the fail-open default**

In `apps/api/app/core/config.py`, replace:

```python
environment: Environment = Environment.DEVELOPMENT
```

with:

```python
environment: Environment
```

Keep `get_settings()` and its narrow Pydantic mypy suppression unchanged:

```python
@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
```

- [ ] **Step 4: Run configuration tests and static checks**

Run:

```powershell
$env:JEPRET_ENVIRONMENT='development'
uv run --project apps/api pytest apps/api/tests/test_config.py -q
uv run --project apps/api mypy apps/api/app
uv run --project apps/api ruff check apps/api/app/core/config.py apps/api/tests/test_config.py
```

Expected: all configuration tests PASS; mypy and Ruff PASS.

- [ ] **Step 5: Prove startup configuration is fail closed**

Run:

```powershell
$saved=$env:JEPRET_ENVIRONMENT
Remove-Item Env:JEPRET_ENVIRONMENT -ErrorAction SilentlyContinue
uv run --project apps/api python -c "from app.core.config import get_settings; get_settings()"
$env:JEPRET_ENVIRONMENT=$saved
```

Expected: command exits non-zero with a Pydantic validation error naming `environment`. Restore the shell variable even when manually interrupted.

- [ ] **Step 6: Commit the backend security change**

```powershell
git add apps/api/app/core/config.py apps/api/tests/test_config.py
git commit -m "fix(api): require explicit environment"
```

---

### Task 2: Add a creator-reachable payment route

**Files:**
- Modify: `apps/web/src/app/booking/masuk/page.test.tsx`
- Modify: `apps/web/src/app/booking/masuk/page.tsx`

- [ ] **Step 1: Write failing UI tests for confirmed and completed bookings**

Add these tests to `BookingMasukPage`:

```tsx
it("links confirmed bookings to their payment page", async () => {
  stubFetch(incoming("confirmed"));
  renderPage();

  expect(
    await screen.findByRole("button", { name: "Tandai selesai" }),
  ).toBeVisible();
  expect(
    screen.getByRole("link", { name: "Lihat pembayaran" }),
  ).toHaveAttribute("href", "/booking/b9/pembayaran");
});

it("keeps the payment link after completion", async () => {
  stubFetch(incoming("completed"));
  renderPage();

  expect(
    await screen.findByRole("link", { name: "Lihat pembayaran" }),
  ).toHaveAttribute("href", "/booking/b9/pembayaran");
  expect(
    screen.queryByRole("button", { name: "Tandai selesai" }),
  ).not.toBeInTheDocument();
});

it("does not expose a payment link before confirmation", async () => {
  stubFetch(incoming("awaiting_payment"));
  renderPage();

  expect(await screen.findByText("Menunggu pembayaran")).toBeVisible();
  expect(
    screen.queryByRole("link", { name: "Lihat pembayaran" }),
  ).not.toBeInTheDocument();
});
```

Replace the old confirmed/awaiting-payment assertions where they duplicate these cases; keep the requested acceptance test.

- [ ] **Step 2: Run page tests and verify RED**

Run:

```powershell
npm --workspace @jepret/web test -- "src/app/booking/masuk/page.test.tsx"
```

Expected: confirmed/completed tests FAIL because `Lihat pembayaran` does not exist.

- [ ] **Step 3: Implement the minimal accessible links**

Add the import:

```tsx
import Link from "next/link";
```

Inside `BookingCard`, replace the single confirmed branch with explicit confirmed and completed branches:

```tsx
) : booking.status === "confirmed" ? (
  <>
    <button
      type="button"
      onClick={() => complete.mutate(booking.id)}
      disabled={busy}
      className={`${actionClass} border border-[var(--border)]`}
    >
      Tandai selesai
    </button>
    <Link
      href={`/booking/${booking.id}/pembayaran`}
      className={`${actionClass} inline-flex items-center border border-[var(--border)]`}
    >
      Lihat pembayaran
    </Link>
  </>
) : booking.status === "completed" ? (
  <Link
    href={`/booking/${booking.id}/pembayaran`}
    className={`${actionClass} inline-flex items-center border border-[var(--border)]`}
  >
    Lihat pembayaran
  </Link>
) : null}
```

Do not fetch payment data from the booking list. The existing protected payment page remains the only data-loading boundary.

- [ ] **Step 4: Run focused and full web tests**

Run:

```powershell
npm --workspace @jepret/web test -- "src/app/booking/masuk/page.test.tsx"
npm --workspace @jepret/web test
npm --workspace @jepret/web run typecheck
```

Expected: focused tests PASS; full Vitest and TypeScript PASS.

- [ ] **Step 5: Commit the creator navigation change**

```powershell
git add apps/web/src/app/booking/masuk/page.tsx apps/web/src/app/booking/masuk/page.test.tsx
git commit -m "fix(web): expose creator payment route"
```

---

### Task 3: Make booking/payment E2E deterministic and user reachable

**Files:**
- Modify: `apps/web/e2e/booking.spec.ts`

- [ ] **Step 1: Add serial execution and typed booking setup helpers**

Immediately after account constants, add:

```typescript
test.describe.configure({ mode: "serial" });

interface IncomingBooking {
  event_date: string;
}

interface IncomingEnvelope {
  data: IncomingBooking[];
}

function isoDate(date: Date) {
  return date.toISOString().slice(0, 10);
}

function addUtcDays(date: Date, days: number) {
  const result = new Date(date);
  result.setUTCDate(result.getUTCDate() + days);
  return result;
}
```

Use semantic list items in `bookingCard`:

```typescript
return page
  .getByRole("listitem")
  .filter({ hasText: bookingNote })
  .filter({ hasText: status });
```

- [ ] **Step 2: Add deterministic available-date discovery**

Add this helper after `logout`:

```typescript
async function findAvailableEventDate(
  page: import("@playwright/test").Page,
  initialOffset: number,
) {
  await login(page, CREATOR);
  const response = await page.request.get("/api/v1/bookings/incoming");
  expect(response.ok()).toBe(true);
  const payload = (await response.json()) as IncomingEnvelope;
  const usedDates = new Set(payload.data.map((booking) => booking.event_date));
  const start = new Date();
  start.setUTCHours(0, 0, 0, 0);
  start.setUTCFullYear(start.getUTCFullYear() + 1);

  for (let offset = initialOffset; offset < initialOffset + 730; offset += 1) {
    const candidate = isoDate(addUtcDays(start, offset));
    if (!usedDates.has(candidate)) {
      await logout(page);
      return candidate;
    }
  }

  throw new Error("Tidak ada tanggal booking kosong dalam jendela E2E dua tahun.");
}
```

This reads an existing authorized endpoint through the same browser context; it does not add a test-only API.

- [ ] **Step 3: Keep URL capture scoped to the client refund assertion**

Keep `payBooking` returning the payment URL for the refund test:

```typescript
return page.url();
```

The release test must ignore this return value; no creator flow may retain or
consume a URL learned from the client session. The refund test may reuse it
because it remains within the same authorized client journey.

- [ ] **Step 4: Rewrite release and refund setup**

Release test setup:

```typescript
const eventDate = await findAvailableEventDate(page, 0);
const bookingNote = `E2E release ${crypto.randomUUID()}`;

await requestBooking(page, eventDate, bookingNote);
await acceptBooking(page, bookingNote);
await payBooking(page, bookingNote);
```

After creator completes the booking, navigate through the visible link:

```typescript
const completed = bookingCard(page, bookingNote, "Selesai");
await expect(completed).toBeVisible();
await completed.getByRole("link", { name: "Lihat pembayaran" }).click();
await expect(page).toHaveURL(/\/booking\/[^/]+\/pembayaran$/);
await page.getByRole("button", { name: "Simulasikan pencairan" }).click();
await expect(page.getByText("Pembayaran telah dilepas")).toBeVisible();
```

Refund test setup:

```typescript
const eventDate = await findAvailableEventDate(page, 365);
const bookingNote = `E2E refund ${crypto.randomUUID()}`;

await requestBooking(page, eventDate, bookingNote);
await acceptBooking(page, bookingNote);
await payBooking(page, bookingNote);
```

Capture the URL only in the refund test and reopen it after cancellation:

```typescript
const paymentUrl = await payBooking(page, bookingNote);

await page.goto("/booking");
const card = bookingCard(page, bookingNote, "Terkonfirmasi");
await card.getByRole("button", { name: "Batalkan" }).click();
await expect(bookingCard(page, bookingNote, "Dibatalkan")).toBeVisible();

await page.goto(paymentUrl);
await expect(page.getByText("Pembayaran dikembalikan")).toBeVisible();
```

This is an authorized same-client state assertion. Do not add a cancelled
booking CTA because that behavior is outside the approved remediation scope.

- [ ] **Step 5: Run formatter and focused E2E twice**

Ensure stack reflects current code:

```powershell
npm run format
docker compose up -d --build
docker compose run --rm migrate
docker compose run --rm seed
npm --workspace @jepret/web run e2e -- booking.spec.ts
npm --workspace @jepret/web run e2e -- booking.spec.ts
```

Expected: each run reports 2 passed. The second run selects different free dates and does not hit `DATE_UNAVAILABLE`.

- [ ] **Step 6: Commit the retry-safe product journeys**

```powershell
git add apps/web/e2e/booking.spec.ts
git commit -m "test(e2e): make payment journeys retry safe"
```

---

### Task 4: Align Compose and documentation with actual security behavior

**Files:**
- Modify: `docker-compose.yml:12-17`
- Modify: `.env.example:1-4`
- Modify: `README.md:44-46,93-109,119-130`
- Modify: `docs/testing.md`

- [ ] **Step 1: Make the frontend Compose build argument overridable but explicit**

In `docker-compose.yml`, replace the hard-coded argument with:

```yaml
args:
  NEXT_PUBLIC_JEPRET_ENVIRONMENT: ${NEXT_PUBLIC_JEPRET_ENVIRONMENT:-development}
```

Keep API/migrate/seed on the explicit shared `JEPRET_ENVIRONMENT: development` mapping.

- [ ] **Step 2: Clarify the root environment example**

Use these leading comments in `.env.example`:

```dotenv
# Required by the API. Mock payment and /api/v1/dev/payments/* are unavailable in production.
JEPRET_ENVIRONMENT=development
# Compose forwards this build-time value; its local default is development.
NEXT_PUBLIC_JEPRET_ENVIRONMENT=development
```

- [ ] **Step 3: Correct README environment and sandbox instructions**

In **Environment variables**, explicitly state:

```markdown
`JEPRET_ENVIRONMENT` wajib diisi; API menolak startup bila variable ini hilang
atau invalid. Compose menetapkan API ke `development` secara eksplisit dan
meneruskan `NEXT_PUBLIC_JEPRET_ENVIRONMENT` ke build web dengan default lokal
`development`.
```

Replace sandbox step 4 with the user-reachable flow:

```markdown
4. Untuk alur pencairan, masuk sebagai kreator, buka **Booking masuk**, tandai
   booking selesai, pilih **Lihat pembayaran**, lalu **Simulasikan pencairan**.
```

Replace the inaccurate production bundle sentence with:

```markdown
Mock webhook dan `/api/v1/dev/payments/*` ditolak saat
`JEPRET_ENVIRONMENT=production`. Konfigurasi frontend production menyembunyikan
kontrol simulasi, tetapi backend tetap menjadi security boundary; client code
tidak dianggap sebagai pengaman endpoint.
```

- [ ] **Step 4: Update direct-test environment instructions**

In `docs/testing.md`, add this variable to the documented PowerShell integration setup before database URL:

```powershell
$env:JEPRET_ENVIRONMENT='test'
```

Under focused booking E2E, document the repeat proof:

```bash
npm --workspace @jepret/web run e2e -- booking.spec.ts
npm --workspace @jepret/web run e2e -- booking.spec.ts
```

Explain that two consecutive runs prove interrupted-run date isolation.

- [ ] **Step 5: Validate rendered Compose configuration and formatting**

Run:

```powershell
npm run format
docker compose config
$env:NEXT_PUBLIC_JEPRET_ENVIRONMENT='production'
docker compose config
Remove-Item Env:NEXT_PUBLIC_JEPRET_ENVIRONMENT
```

Expected: default config renders frontend build argument `development`; override renders `production`; API remains explicitly `development` in local Compose.

- [ ] **Step 6: Commit configuration and docs**

```powershell
git add .env.example docker-compose.yml README.md docs/testing.md
git commit -m "docs: clarify payment environment safeguards"
```

---

### Task 5: Run final gates, record evidence, and close review findings

**Files:**
- Modify: `docs/implementation-plan.md`

- [ ] **Step 1: Run focused backend and frontend suites**

Run:

```powershell
$env:JEPRET_ENVIRONMENT='test'
uv run --project apps/api pytest apps/api/tests/test_config.py apps/api/tests/test_payment_provider.py -q
uv run --project apps/api pytest apps/api/tests/test_bookings_api.py apps/api/tests/test_payments_api.py -m integration -q
npm --workspace @jepret/web test
```

Expected: all suites PASS. Record exact counts and warnings from this run; do not copy stale numbers.

- [ ] **Step 2: Run full E2E**

Run:

```powershell
docker compose up -d --build
docker compose run --rm migrate
docker compose run --rm seed
npm --workspace @jepret/web run e2e
```

Expected: foundation, auth, marketplace, booking, release, and refund scenarios PASS.

- [ ] **Step 3: Run the repository quality gate**

Run:

```powershell
$env:JEPRET_ENVIRONMENT='test'
npm run verify
```

Expected: format check, lint, mypy, TypeScript, pytest, Vitest, contracts, Next build, and Compose config all PASS.

- [ ] **Step 4: Perform diff, security, and domain invariants review**

Run:

```powershell
git diff --check 52b82bf..HEAD
git diff --stat 52b82bf..HEAD
git grep -n -I -E "(api[_-]?key|secret|password|token)" -- . ":!package-lock.json" ":!apps/api/uv.lock"
git status --short
```

Confirm from the diff:

- no real secret or provider metadata was added;
- no dev endpoint can activate from an omitted environment;
- creator link does not bypass backend authorization;
- booking/payment services, transactions, and idempotency code are unchanged;
- no migration or generated contract drift exists;
- E2E uses UI navigation and deterministic free dates.

- [ ] **Step 5: Record actual remediation evidence**

Append one bullet to the Phase 5 evidence section. It must state the verification
date `2026-08-13`, that the API environment is required, that the creator route
is available for confirmed/completed bookings, and that focused booking E2E
passed twice without collision. In the same bullet, transcribe the exact focused
pytest count, full Playwright count, Vitest file/test counts, and final
`npm run verify` counts produced by Steps 1–3. Do not round counts or copy the
2026-08-02 evidence.

- [ ] **Step 6: Commit the evidence**

```powershell
git add docs/implementation-plan.md
git commit -m "docs: record phase 5 remediation evidence"
```

- [ ] **Step 7: Request two-stage review**

Dispatch a fresh spec reviewer against:

- design spec `docs/superpowers/specs/2026-08-13-jepret-phase-5-quality-remediation-design.md`;
- this implementation plan;
- base `52b82bf` through current HEAD.

Only after spec approval, dispatch a fresh quality reviewer. Any Critical or Important issue returns to the responsible implementer, followed by re-review.

- [ ] **Step 8: Push the approved checkpoint**

After both reviews approve and the worktree is clean:

```powershell
git push origin codex/phase-5-payment
git status -sb
git log -8 --oneline
```

Expected: local branch tracks and matches `origin/codex/phase-5-payment`; Phase 5 quality review has no open Critical or Important issue.
