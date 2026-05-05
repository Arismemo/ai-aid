---
description: Read an ai-aid request with all its answers.
---

Run:
```bash
bash "$HOME/.claude/skills/aid-network/shared/scripts/aid_check.sh" "$REQUEST_ID" | jq .
```

Returns the full request body and the `answers` array. If `answers` is empty,
no one has responded yet.
