---
description: Read an ai-aid request with all its answers.
---

Run:
```bash
bash "$(git rev-parse --show-toplevel)/skills/shared/scripts/aid_check.sh" "$REQUEST_ID" | jq .
```

Returns the full request body and the `answers` array. If `answers` is empty,
no one has responded yet.
