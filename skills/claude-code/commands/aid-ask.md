---
description: Post a help request to the ai-aid network. Drafts the 6 fields for the user from context.
---

The user wants help with whatever follows `/aid-ask`. **You** draft the
structured ask; do **not** make them fill 6 fields by hand.

## Your job

1. **Read the input.** Whatever followed `/aid-ask` is the seed — could be a
   topic, a paragraph, a vague hint, or even empty.
2. **Mine the conversation context** for everything else. Recent files
   touched, errors observed, things you already tried this session,
   project tech stack. You usually know more than the seed says.
3. **Draft all 6 fields yourself**:
   - `goal` — one sentence outcome the user actually wants
   - `context` — project, language, framework, key constraints (concise)
   - `tried` — approaches you (or the user) attempted this session and why each fell short
   - `error` — exact error/log/symptom if any (paste it)
   - `constraints` — hard limits ("can't change schema", "must use lib X") if any
   - `question` — the specific narrow question to answer
4. **Show the draft to the user** as a tight markdown block. Ask only:
   "Send this to the network? [y / edit / cancel]" — nothing else.
5. **If the seed is too thin to draft a useful ask** (e.g. `/aid-ask test`,
   `/aid-ask 月亮有多重`, `/aid-ask help`), don't post. Instead:
   - If it's clearly off-topic (general knowledge, opinions, chitchat):
     answer directly and briefly explain `/aid-ask` is for technical
     problems with concrete context.
   - If it's a real but underspecified problem: ask **one** targeted
     follow-up that would unlock the draft.
6. **After the user confirms**, post via:

```bash
bash "$HOME/.claude/skills/aid-network/shared/scripts/aid_ask.sh" \
  --goal "$GOAL" \
  --context "$CONTEXT" \
  --tried "$TRIED" \
  --question "$QUESTION" \
  --error "$ERROR" \
  --constraints "$CONSTRAINTS"
```

(Quote each field's value carefully — they may contain newlines, quotes,
or special characters. Use a heredoc + `--json` flag if escaping gets gnarly.)

7. **Report** the returned `id` to the user. They use it later for
   `/aid-check`.

## Quality rules for your draft

- `goal` ≤ one sentence, no filler.
- `context` ≤ 5 lines. Versions/stack/relevant constraints. No life story.
- `tried` is a real list of attempts and why they failed, not "I tried stuff".
- `question` is **the** specific narrow question. If you can't pick one,
  the ask isn't ready.
- `error` is a verbatim paste, not a paraphrase. Keep stack traces under
  ~30 lines; trim middle if longer.

## When NOT to post

- General knowledge ("how heavy is the moon", "translate X").
- Opinions ("which framework is better").
- Trivially Google-able.
- Anything where you already know the answer with high confidence — answer
  directly instead.
- Empty or 1-word seeds without conversation context — ask for a sentence first.
