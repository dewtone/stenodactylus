# Stenodactylus — Session Recovery Notes

## Git Setup (resolved)

This repo lives in `/home/shared-projects/stenodactylus`, which triggers git's ownership check. Three things must be configured before any git operations work:

1. **Safe directory**: `git config --global --add safe.directory /home/shared-projects/stenodactylus`
2. **Local identity** (already set in `.git/config`):
   - `user.name = dewtone`
   - `user.email = noreply@dewtone.app`
3. **Branch**: `main` (not `master`)

Remote is `https://github.com/dewtone/stenodactylus.git` — PAT not stored, must be provided for push.

## What's gitignored

- `.claude/` — Claude Code settings
- `*.local` — local-only files (e.g., `USER_PROFILE.local` with stripped personal info)

## Architecture

Design-phase, no source code yet. See `DESIGN_NOTES.md` for full design.

Steno chord trainer for the Starboard keyboard (Javelin firmware, HID communication). GTK4/Python/SQLite. Audio from Soundsmith palettes, 432 Hz.
