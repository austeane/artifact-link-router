# artifact-link-router

A Claude Code skill for people who use several Claude accounts and several browser profiles on one
Mac. It makes a claude.ai artifact link open in the browser profile that is signed in to the Claude
account that published it.

## The problem

An artifact published from Claude Code is private to the account that published it. If your work
account is signed in to claude.ai in one Chrome profile and your personal account in another, a
clicked artifact link opens in whichever profile you used last. Half the time that is the wrong
account, and the page says the artifact does not exist.

## What it does

- **Records the owner.** A Claude Code hook notes which account published each artifact.
- **Finds the profile.** It reads each browser profile's claude.ai sign-in to learn which profile
  belongs to which account. There is nothing to configure, and you can pin an account by hand.
- **Routes the click.** Links Claude Code opens itself go through `BROWSER`. For clicks handled by
  your terminal or another app, an optional small default-browser app routes artifact links and
  passes every other link to your normal browser unchanged.
- **Catches up on old artifacts.** `claude-artifact-router backfill` reads past transcripts for
  artifacts published before you installed it.

## Requirements

- macOS.
- Chrome, Brave, Edge, Vivaldi or Chromium. Chrome is the tested one. Safari can be chosen by hand
  for an account. Firefox and Arc are not supported.
- Python 3.9 or later (the one that comes with the Xcode Command Line Tools is enough).
- The Swift compiler, only for the optional default-browser app (`xcode-select --install`).

## Install

Clone it into your Claude Code skills folder:

```bash
git clone https://github.com/austeane/artifact-link-router ~/.claude/skills/artifact-link-router
```

Then ask Claude Code: "set up the artifact link router". It will show you what it would change and
ask before touching your default browser.

Or run the installer yourself:

```bash
cd ~/.claude/skills/artifact-link-router
python3 scripts/install.py --dry-run --app   # see what would change
python3 scripts/install.py --app             # script, hook, BROWSER, and the app
python3 scripts/install.py --make-default    # optional: make the app your default browser
```

The installer adds one hook and one environment variable to the `settings.json` of every Claude
Code profile it finds (`~/.claude`, `~/.claude-*`, `$CLAUDE_CONFIG_DIR`). It is safe to run again.

## Use

```bash
claude-artifact-router status                       # each Claude profile, its account, its browser profile
claude-artifact-router where <artifact url>         # where a link would open, and why
claude-artifact-router set me@work.com "Profile 6"  # pin an account to a profile
claude-artifact-router set me@home.com safari
```

[SKILL.md](SKILL.md) has the full guide: how it works, troubleshooting, and limits.

## Remove

```bash
python3 scripts/install.py --uninstall   # add --purge to delete the recorded owners too
```

## Privacy

Everything stays on your Mac. The router reads each browser's profile list and looks in each
profile's claude.ai storage for your own account id, and it sends nothing anywhere. Its records (artifact ids,
account ids, account emails) are in `~/.local/state/claude-artifact-router/`.

## Limits

- It knows an artifact's owner only if a Claude Code session on this Mac published it. A link
  someone else sent you opens in your normal browser.
- Browsers other than Chrome use the same profile layout and should work, but are untested.
- This is a personal tool, not an Anthropic product.

## License

MIT. See [LICENSE](LICENSE).
