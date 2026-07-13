# AGENTS.md

## Mission
Build and maintain Jepret, a mobile-first marketplace for clients and visual creators.

## Working rules
- Inspect existing code before editing.
- Keep the architecture a modular monolith.
- Prefer simple, maintainable solutions over clever abstractions.
- Do not leave core paths as mocks or TODOs.
- Payment may use a mock/sandbox adapter, but the business state machine must be complete.
- Never commit secrets.
- Use stable, non-deprecated APIs.
- Preserve backward compatibility unless a migration is included.
- Every database change requires an Alembic migration.
- Every authorization-sensitive feature requires backend permission tests.
- Every booking/payment change requires transaction and idempotency review.

## Language
- Code, identifiers, schema, and technical comments: English.
- User-facing UI: Indonesian.
- Documentation: Indonesian, with English technical terms where clearer.

## Frontend
- TypeScript strict mode.
- Accessible components.
- Mobile-first.
- Handle loading, empty, error, and success states.
- Do not fetch protected data directly from client code without the approved API/auth flow.
- Keep feature code grouped by domain.

## Backend
- Keep route handlers thin.
- Put domain rules in testable services.
- Validate inputs and authorize every action.
- Use consistent API errors.
- Avoid N+1 queries.
- Use transactions for booking, payment, review, and availability-sensitive operations.

## Quality gates
Before declaring a task complete:
1. Run formatter.
2. Run lint.
3. Run type-check.
4. Run relevant unit/integration tests.
5. Run build.
6. Review the diff for security and accidental secrets.
7. Update docs when behavior or setup changes.
8. Run `npm run verify` from the repository root before declaring Phase 1 work complete.

## Reporting
At the end of each task, report:
- summary
- files changed
- migrations
- tests run and results
- known limitations
- next recommended task
