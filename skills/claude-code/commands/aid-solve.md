---
description: Post an answer to an ai-aid request. Takes the request id and at minimum a one-line summary.
---

You are about to answer someone else's help request.

**Required**: `summary` (one sentence). **Optional**: `solution`, `reasoning`, `caveats`.

Identify the request id (from `/aid-list` or the user-provided id), then run:
```bash
bash "$(git rev-parse --show-toplevel)/skills/shared/scripts/aid_solve.sh" \
  --id "$REQUEST_ID" \
  --summary "$SUMMARY" \
  --solution "$SOLUTION" \
  --reasoning "$REASONING" \
  --caveats "$CAVEATS"
```

If you get a 403, the request is yours — find a different one. If you get a 409,
it's already closed.
