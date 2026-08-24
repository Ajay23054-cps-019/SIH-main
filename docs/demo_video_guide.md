# Demo Video Recording Guide

A pre-recorded video is the backup of the backup — record it once the live
demo rehearses cleanly, so it always matches reality.

## Preparation

1. `./venv/bin/python scripts/load_demo_data.py && make run`
2. Fresh browser profile (no extensions/notifications), zoom 125%,
   window 1920×1080.
3. Disconnect the network and reload `/dashboard/` once to prove offline
   rendering works; reconnect only if you need nothing else.
4. Have `docs/demo_script.md` open on a second screen as the teleprompter.

## Recording

- Tool: OBS Studio (or any recorder), 1080p @ 30 fps, capture display audio
  or a quiet-room voice track.
- One continuous take walking the storyboard in `docs/demo_script.md`;
  restart from the top rather than editing mid-flow cuts.
- Cursor discipline: move deliberately; park the cursor bottom-right while
  narrating numbers.
- Target: **1:55** (leave 5 s of headroom under the 2:00 limit).

## Shot list

| # | Screen | Duration |
|---|--------|----------|
| 1 | `/dashboard/` portfolio table | ~20 s |
| 2 | Click CSE-042 → entity view | ~20 s |
| 3 | Finding view `CSE-042:quality_degradation`, expand one record | ~20 s |
| 4 | `/dashboard/entity/CSE-089` negative-space beat | ~15 s |
| 5 | Peer chart panel on CSE-042's entity view | ~20 s |
| 6 | Back to portfolio, closing frame | ~15 s |

## After recording

- Verify the file plays on a machine with no Python installed at all.
- Export alongside screenshots (see `docs/demo_screenshots/README.md`).
- Store one copy outside the demo laptop.
