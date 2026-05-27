---
name: brain-compliance
description: Use to inspect whether sessions are capturing enough, or to audit recent under-captured / thin sessions. Compliance is observability — the brain can't compel capture, but it can make non-capture visible.
---

# brain-compliance

## When to use

- Reviewing why the brain doesn't seem to "remember" — check whether prior sessions were actually capturing.
- Onboarding a new agent or project — confirm capture cadence is healthy.
- Debugging a "thin" resume bundle — find sessions where the bundle generator had nothing substantive to save.

## How

```bash
# One session's stats by id.
bash skills/brain-compliance/scripts/compliance.sh check --session-id <N>

# Recent under-captured sessions (≥5 user turns + <3 substantive captures).
bash skills/brain-compliance/scripts/compliance.sh list [--limit N]

# Recent sessions that produced thin (no-substantive-content) resume bundles.
bash skills/brain-compliance/scripts/compliance.sh list-thin [--limit N]
```

## Strict mode (opt-in)

Brain runs in a Docker container exposed at `127.0.0.1:5433` — there's no host-side Postgres socket. Use one of these:

```bash
# Via TCP from the host
PGPASSWORD=brain_dev_password psql -h 127.0.0.1 -p 5433 -U brain -d brain -c \
  "INSERT INTO brain_config(key, value, updated_at) VALUES ('strict_mode', 'true', NOW()) \
   ON CONFLICT (key) DO UPDATE SET value = 'true';"

# Or directly in the container
docker exec -i brain-postgres psql -U brain -d brain -c \
  "INSERT INTO brain_config(key, value, updated_at) VALUES ('strict_mode', 'true', NOW()) \
   ON CONFLICT (key) DO UPDATE SET value = 'true';"
```

With strict mode on, the SessionEnd hook exits non-zero (code 2) when the session is under-captured. The next session's SessionStart hook surfaces this as a visible system reminder. To turn it back off:

```bash
PGPASSWORD=brain_dev_password psql -h 127.0.0.1 -p 5433 -U brain -d brain -c \
  "UPDATE brain_config SET value = 'false', updated_at = NOW() WHERE key = 'strict_mode';"
```

## Output budget

≤200 tokens per call. Reference sessions by id; do not paste full counts in your prose.
