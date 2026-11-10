---
name: artifact-link-router
description: Make claude.ai artifact links open in the browser profile that is signed in to the Claude account that published them (macOS; Chrome, Brave, Edge, Vivaldi, Chromium; Safari by hand). Use whenever someone with more than one Claude account or Claude Code profile (CLAUDE_CONFIG_DIR, work and personal sign-ins) and more than one browser profile says an artifact link opened in the wrong Chrome profile or the wrong account, landed on "not found", "you don't have access" or a login page, or asks to choose which browser profile Claude's links open in. Also use to check, repair or remove an existing install (the `claude-artifact-router` command, the "Claude Link Router" app).
---

# Artifact link router

An artifact published from Claude Code is private to the Claude account that published it. A person
with several accounts, each signed in to claude.ai in a different browser profile, clicks the link
and the browser opens it in whichever profile was used last. That is usually the wrong account, so
the page says the artifact does not exist.

This skill installs a small router that sends each artifact link to the right browser profile, and
nothing else anywhere else. macOS only.

## How it works

Three parts. Each covers a case the others cannot.

1. **A recording hook.** A `PostToolUse` hook on the Artifact and Claude Docs tools writes
   `artifact id → Claude account` to a local file the moment an artifact is published. The account
   is read from the session's own config dir, so it is right even when the person runs several
   Claude Code profiles at once.
2. **`BROWSER`.** Claude Code opens links with `$BROWSER <url>` when it opens them itself (a click in
   the fullscreen interface, ctrl+], the `/artifacts` list). `env.BROWSER` points at the router
   script, which looks up the artifact's owner, falls back to the session's current account, and
   passes every other URL straight to `open`.
3. **A default-browser app (optional).** Most terminals open a clicked link themselves through the
   macOS default browser, and so do Slack, Mail and Notes. Those clicks never reach Claude Code.
   "Claude Link Router.app" is a tiny default-browser stand-in: artifact links go to the script,
   every other link is handed unchanged to the browser it replaced. It quits itself after 30 idle
   seconds.

Finding the profile needs no setup. claude.ai keeps the signed-in account's id in the browser
profile's local storage, so the script looks for the account id in each profile's storage and picks
the profile that has it. If none has it, it falls back to a profile whose Google account has the
same email as the Claude account. The person can pin any account by hand.

## Install

Everything is in `scripts/install.py`. It is safe to run again; it changes only what is missing.

1. Look first, and show the person what would change:

   ```bash
   python3 <skill folder>/scripts/install.py --dry-run --app
   ```

2. Install the script, the hook and `BROWSER`, and build the app:

   ```bash
   python3 <skill folder>/scripts/install.py --app
   ```

   `--app` needs the Swift compiler (`xcode-select --install`). Without it, leave `--app` off; parts
   1 and 2 still work. The run ends by reading past transcripts for artifacts published before the
   hook existed (a minute or two on a large history, faster with `rg` installed), then prints the
   status table.

3. Read the status table with the person. Each Claude profile should show its account and the
   browser profile its artifacts will open in. Fix any wrong or missing line now (next section).

4. **Ask before changing the default browser.** It is a system-wide setting and macOS shows its own
   confirmation dialog. Explain the trade: clicks in any terminal and any app are routed, ordinary
   links still open in their current browser, and Chrome will show its "not your default browser"
   banner. If they agree:

   ```bash
   python3 <skill folder>/scripts/install.py --make-default
   ```

   Tell them to choose **Use "Claude Link Router"** in the dialog. If they already use another
   link-router app as their default browser (Finicky, Velja, Choosy), do not replace it; stop after
   step 2 and say that clicks handled by their terminal will keep going through that app.

The installer writes to every Claude Code config dir it finds: `~/.claude`, each `~/.claude-*`
folder that holds a `.claude.json`, and `$CLAUDE_CONFIG_DIR`. Name any other with
`--config-dir <dir>`. It will not replace an `env.BROWSER` that points somewhere else, and it skips
a settings file it cannot parse. For a skipped file, add this by hand:

```json
{
  "env": { "BROWSER": "/Users/<name>/.local/bin/claude-artifact-router" },
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Artifact|mcp__claude_ai_Claude_Docs__.*",
        "hooks": [
          { "type": "command", "command": "/Users/<name>/.local/bin/claude-artifact-router record", "timeout": 5 }
        ]
      }
    ]
  }
}
```

## Check it works

```bash
claude-artifact-router status                # every Claude profile → account → browser profile
claude-artifact-router where <artifact url>  # where one link would go, and why
tail ~/.local/state/claude-artifact-router/router.log
```

Then prove it with a real click: publish or pick an artifact, have the person click its link, and
read the last log line. `route <id> <email> -> <browser>/<profile>` means the app handled a click;
`open ...` means Claude Code opened it through `BROWSER`. Do not report it working from the status
table alone.

`CAR_DRY_RUN=1 claude-artifact-router route <url>` prints the command instead of opening a tab.

## When a link goes to the wrong place

Read the log line for that click first. The reason is in brackets.

| Log says | Meaning | Fix |
| --- | --- | --- |
| `no record of which account published it` | The artifact was published before the hook, in a session with no hook, or by someone else. | `claude-artifact-router backfill`, then try again. A link nobody published from this Mac cannot be placed; it opens in the normal browser. |
| `no browser profile has this account's claude.ai session` | That account is not signed in to claude.ai in any Chromium profile. | Sign in to claude.ai in the right profile and run `claude-artifact-router detect`, or pin it (below). |
| A profile, but the wrong one | Two profiles are signed in to the same account, or the fallback matched on email. | Pin it. |
| Nothing logged at all | The click never reached the router. | Check `status` shows the app installed and that it is the default browser: `"$HOME/Applications/Claude Link Router.app/Contents/MacOS/ClaudeLinkRouter" --default-status` should print `local.claude-link-router`. |

Pin an account to a profile:

```bash
claude-artifact-router profiles                           # what can be a target
claude-artifact-router set me@work.com "Profile 6"        # a Chrome profile folder or its display name
claude-artifact-router set me@other.com "Brave Browser/Default"
claude-artifact-router set me@home.com safari
claude-artifact-router set me@work.com none               # back to automatic
```

Detection is cached for a day. `claude-artifact-router detect` re-reads the browsers now; run it
after the person signs in to claude.ai somewhere new.

## Limits to tell the person

- macOS only. Chrome is the tested browser. Brave, Edge, Vivaldi and Chromium use the same profile
  layout and flags and are detected the same way, but are less proven. Firefox and Arc are not
  supported. Safari works only as a pinned target and only for its default profile.
- The owner of an artifact is known only if a Claude Code session on this Mac published it (the
  hook) or its transcript is still on disk (backfill). A link someone else sent stays unrouted.
- An account switch with `/login` is handled: the hook records the account that was signed in at
  publish time, not the profile's current one.
- A skill folder is per Claude Code profile. Copy or symlink this folder into each profile's
  `skills/` if the person wants the skill itself available everywhere; the router works in all
  profiles either way.
- Without the app, a click that the terminal handles on its own still goes to the default browser.
  Some terminals can be told to run a command for a clicked URL (kitty `open_url_with`, WezTerm's
  `open-uri` event); pointing that at `claude-artifact-router open` should work without changing the
  default browser, but it is untested here.

## Remove it

```bash
python3 <skill folder>/scripts/install.py --uninstall          # add --purge to delete the records too
```

This gives the default browser back to the one it replaced (macOS asks again), removes the hook and
`BROWSER` from every settings file, and deletes the app and the script. It stops, and removes
nothing, if the default browser cannot be handed back.

## Files

- `scripts/claude-artifact-router`: the router. Python 3.9+, standard library only. Run it with no
  arguments for its commands.
- `scripts/install.py`: install, repair, uninstall.
- `app/`: Swift source, `Info.plist` and `build.sh` for the default-browser app.
- On the person's machine: records and log in `~/.local/state/claude-artifact-router/`, pins in
  `~/.config/claude-artifact-router/profiles.json`.

The records hold artifact ids, account ids and account emails. Treat them as private: do not paste
the status table, the log or the records into anything that leaves the machine.
