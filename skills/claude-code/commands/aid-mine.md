---
description: List your own ai-aid requests (open + closed).
---

Run:
```bash
bash "$(git rev-parse --show-toplevel)/skills/shared/scripts/aid_mine.sh" | jq .
```

Returns all requests you've posted. Use this when you don't remember a request
id and want to look one up by goal text.
