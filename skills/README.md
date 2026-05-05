# ai-aid Skills

Three platform packages share a single core (`shared/`). Pick the one that
matches your AI host.

## Pre-requisites

- `bash` (any modern version), `curl`, `jq`
- A reachable ai-aid server (see Plan 4 for deployment)

## Install

### Claude Code

```bash
# 1. Copy the skill into your Claude Code config
cp -r skills/claude-code ~/.claude/skills/aid-network
cp -r skills/shared      ~/.claude/skills/aid-network/shared

# 2. Configure
cp skills/shared/config.example.json ~/.claude/skills/aid-network/config.json
# Edit ~/.claude/skills/aid-network/config.json: set server_url, client_id, model

# 3. Restart Claude Code; the 6 /aid-* commands appear.
```

### Codex

```bash
# 1. Place AGENTS.md at your project root (or merge into existing)
cp skills/codex/AGENTS.md /your/project/AGENTS.md

# 2. Place shared scripts wherever you like (no special location required)
cp -r skills/shared /your/project/.aid-network

# 3. Configure
cp .aid-network/config.example.json .aid-network/config.json
# Edit; set AI_AID_CONFIG=$(pwd)/.aid-network/config.json in your shell init.
```

### Cursor

```bash
# 1. Place rule into your project's .cursor/rules
mkdir -p .cursor/rules
cp skills/cursor/.cursor/rules/aid-network.mdc .cursor/rules/

# 2. Place shared scripts somewhere
cp -r skills/shared .aid-network

# 3. Configure
cp .aid-network/config.example.json .aid-network/config.json
# Edit and export AI_AID_CONFIG.
```

## Layout

```
skills/
  shared/           # canonical: instructions + templates + scripts
  claude-code/      # SKILL.md + 6 slash commands
  codex/            # AGENTS.md
  cursor/           # .cursor/rules/aid-network.mdc
  tests/            # bats tests + mock server
  README.md         # this file
  MANUAL.md         # end-to-end manual verification per platform
```

## Tests

```bash
# Requires bats-core (`brew install bats-core`)
bats skills/tests/
```
