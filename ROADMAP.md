# Hockey Hub roadmap

## 0. Stable baseline — done / ongoing

- Stable match feed for СКА, СКА-ВМФ, СКА-1946, Академия СКА and Эскулап.
- Standings and qualification zones.
- Automatic Эскулап tournament discovery.
- Arenas in match cards and normalized match model.
- CI smoke/tests for playoff logic and production import.

## 1. Postseason model and league adapters — current priority

Goal: make playoff monitoring work correctly across KHL, VHL, MHL and SPbHL.

- ✅ Common model: `Season -> Stage -> Series -> Games`.
- ✅ League season-calendar adapters for KHL, VHL and MHL; SPbHL uses the active tournament title as its stage signal.
- ✅ KHL schedule keeps official `not_regular` postseason events while regular standings continue to exclude them.
- ✅ Official SKA-family playoff-page probes can override calendar fallback once the current-season bracket is published.
- ✅ Safe series detection only inside the active postseason window, so regular-season rematches cannot become fake playoff series.
- ✅ Round transitions follow the nearest future opponent / latest played opponent, instead of getting stuck on a longer previous series.
- ✅ Machine-readable qualification states: direct playoff / play-in / outside / postseason.
- ✅ Series score/status model, including completed best-of-seven series for KHL/VHL.
- ✅ Team pages get a first-class postseason block with current opponent, series score, target wins when known, next game and completed series games.
- ✅ Team pages become series-first automatically once play-in/playoff is active; regular-season pages stay unchanged.
- ⏳ Extend source-specific round metadata beyond stage detection when league pages expose reliable round names/pairings.
- ⏳ Add full bracket visualization when source data is reliable enough.

## 2. Persistence foundation

Goal: move from process memory to durable normalized storage without breaking the current UI.

- PostgreSQL schema for leagues, teams, seasons, stages, games, arenas and playoff series.
- Mirror current collector output into PostgreSQL.
- Verify counts, scores, timestamps and arenas against the proven in-memory cache.
- Switch read APIs to PostgreSQL only after parity checks.
- Switch UI to those APIs after the database becomes the trusted source.
- Before the free Render PostgreSQL expires in October 2026, choose a permanent free database provider or deliberately upgrade.

## 3. Security gate — mandatory before personal data or AI

This stage must be completed before training notes, personal profile data, wishlists with private notes, assistant memory or OpenAI API access are added.

- Add authentication for the private area (single-user is enough initially).
- Keep public hockey data read-only; require authentication for all personal data and write operations.
- Protect `/refresh` and all future POST/PUT/PATCH/DELETE endpoints.
- Add server-side sessions with Secure/HttpOnly/SameSite cookies.
- Store passwords only as modern salted hashes; never store plaintext credentials.
- Keep `DATABASE_URL`, future `OPENAI_API_KEY` and other credentials only in Render secrets/environment variables; never commit them to GitHub or expose them to browser JS.
- Add CSRF protection for browser write actions and strict input validation.
- Add rate limiting, especially for refresh, search/scraping and future AI endpoints.
- Restrict or disable production `/docs`, `/openapi.json` and diagnostic endpoints where appropriate.
- Parameterize all SQL and keep database permissions minimal.
- Add backup/export strategy for user-owned data before it becomes valuable.
- Consider making the GitHub repository private as the project becomes personal, while still treating source visibility as non-secret.

## 4. UI/design pass

Only after the data model and main navigation stop changing rapidly.

- Unified design system and navigation.
- Mobile-first cleanup.
- Better match cards, postseason/series cards, charts and bracket components.
- Preserve the dark, restrained "personal hockey terminal" feel rather than copying league websites.

## 5. Expansion workshop — parked intentionally

Before adding heterogeneous product areas, run a separate brainstorming/prioritization session. Candidate directions already parked include:

- personal training/progress;
- news/media;
- merch/equipment/watchlists;
- personal hockey archive;
- player tracking and SKA development-path view;
- personalized "today / this week" briefing;
- embedded AI assistant that can use Hockey Hub data and tools.

Do not build these one by one ad hoc. First group ideas into product areas, score usefulness/complexity, then choose the next expansion wave.
