#!/usr/bin/env python3
"""Install, repair or remove the artifact link router (macOS).

  install.py                  script + recording hook + BROWSER, in every Claude Code profile
  install.py --app            also build "Claude Link Router.app" (needs swiftc)
  install.py --make-default   also make that app the default browser (macOS asks the person)
  install.py --dry-run ...    say what would change and change nothing
  install.py --uninstall      undo all of it; --purge also deletes the recorded artifact owners

Safe to run again: it changes only what is missing or out of date.

What it touches:
  ~/.local/bin/claude-artifact-router                 the router script
  <each Claude config dir>/settings.json              one PostToolUse hook and env.BROWSER
  ~/Applications/Claude Link Router.app               only with --app
  the default http/https handler                      only with --make-default
"""
import argparse
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HOME = Path.home()
SKILL = Path(__file__).resolve().parent.parent
SCRIPT_SRC = SKILL / "scripts/claude-artifact-router"
APP_SRC = SKILL / "app"
BIN = HOME / ".local/bin/claude-artifact-router"  # LinkRouter.swift looks for it here
APP = HOME / "Applications/Claude Link Router.app"
APP_BIN = APP / "Contents/MacOS/ClaudeLinkRouter"
BUNDLE_ID = "local.claude-link-router"
STATE = Path(os.environ.get("CAR_STATE_DIR") or HOME / ".local/state/claude-artifact-router")
CONFIG = Path(os.environ.get("CAR_CONFIG_DIR") or HOME / ".config/claude-artifact-router")
APP_STAMP = STATE / "app-source.sha256"
LSREGISTER = ("/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework"
              "/Support/lsregister")
MATCHER = "Artifact|mcp__claude_ai_Claude_Docs__.*"
MARK = "claude-artifact-router"

DRY = False


def say(msg=""):
    print(msg, flush=True)


def did(msg):
    say(("would: " if DRY else "") + msg)


# ---- the router script -----------------------------------------------------

def python_for_script():
    """An absolute interpreter path: the app starts the script without the shell's PATH."""
    clt = subprocess.run(["/usr/bin/xcode-select", "-p"], capture_output=True).returncode == 0
    if clt and Path("/usr/bin/python3").exists():
        return "/usr/bin/python3"  # present on every Mac with the Command Line Tools
    return sys.executable


def install_script():
    lines = SCRIPT_SRC.read_text().split("\n")
    lines[0] = "#!" + python_for_script()
    wanted = "\n".join(lines)
    try:
        current = BIN.read_text()
    except OSError:
        current = None
    if current == wanted and os.access(BIN, os.X_OK):
        say(f"script: up to date ({BIN})")
        return
    did(f"install {BIN} (runs with {lines[0][2:]})")
    if DRY:
        return
    BIN.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(BIN, wanted, 0o755)


def write_atomic(path, text, mode=None):
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        if mode is None:
            try:
                mode = path.stat().st_mode & 0o777
            except OSError:
                mode = 0o644
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ---- Claude Code settings --------------------------------------------------

def settings_files(extra):
    """Each profile's settings.json once, even when profiles share one through a symlink."""
    dirs = [HOME / ".claude"]
    # A Claude Code config dir holds .claude.json; other tools' ~/.claude-* folders do not.
    dirs += sorted(p for p in HOME.glob(".claude-*") if p.is_dir() and (p / ".claude.json").is_file())
    if os.environ.get("CLAUDE_CONFIG_DIR"):
        dirs.append(Path(os.environ["CLAUDE_CONFIG_DIR"]))
    dirs += [Path(d).expanduser() for d in extra]
    seen, out = set(), []
    for d in dirs:
        if not d.is_dir():
            continue
        real = Path(os.path.realpath(d / "settings.json"))
        if real not in seen:
            seen.add(real)
            out.append((d / "settings.json", real))
    return out


def indent_of(text):
    for line in text.splitlines()[1:]:
        body = line.lstrip(" \t")
        if body and body != line:
            lead = line[: len(line) - len(body)]
            return "\t" if lead[0] == "\t" else len(lead)
    return 2


def is_ours(hook):
    cmd = str(hook.get("command") or "").strip()
    return MARK in cmd and cmd.endswith(" record")


def add_settings(s, hook_cmd, browser):
    """Change `s` in place; return what changed and what to tell the person."""
    changes, warnings = [], []
    hooks = s.setdefault("hooks", {})
    post = hooks.setdefault("PostToolUse", []) if isinstance(hooks, dict) else None
    if not isinstance(post, list):
        raise ValueError('"hooks" is not in the shape Claude Code documents')
    ours = [h for e in post if isinstance(e, dict) for h in e.get("hooks") or [] if isinstance(h, dict) and is_ours(h)]
    if not ours:
        post.append({"matcher": MATCHER, "hooks": [{"type": "command", "command": hook_cmd, "timeout": 5}]})
        changes.append("add the recording hook")
    for h in ours:
        if h.get("command") != hook_cmd:
            h["command"] = hook_cmd
            changes.append("point the recording hook at the installed script")
    env = s.setdefault("env", {})
    if not isinstance(env, dict):
        raise ValueError('"env" is not an object')
    have = env.get("BROWSER")
    if have == browser:
        pass
    elif not have or MARK in str(have):
        env["BROWSER"] = browser
        changes.append("set env.BROWSER")
    else:
        warnings.append(f"env.BROWSER is already {have!r}; left alone, so links Claude Code opens itself "
                        "keep going there")
    if not env:
        del s["env"]
    return changes, warnings


def remove_settings(s):
    changes = []
    hooks = s.get("hooks")
    post = hooks.get("PostToolUse") if isinstance(hooks, dict) else None
    if isinstance(post, list):
        kept = []
        for e in post:
            if isinstance(e, dict) and isinstance(e.get("hooks"), list):
                rest = [h for h in e["hooks"] if not (isinstance(h, dict) and is_ours(h))]
                if len(rest) != len(e["hooks"]):
                    changes.append("remove the recording hook")
                    if not rest:
                        continue
                    e["hooks"] = rest
            kept.append(e)
        if kept:
            hooks["PostToolUse"] = kept
        else:
            del hooks["PostToolUse"]
        if not hooks:
            del s["hooks"]
    env = s.get("env")
    if isinstance(env, dict) and MARK in str(env.get("BROWSER") or ""):
        del env["BROWSER"]
        changes.append("remove env.BROWSER")
        if not env:
            del s["env"]
    return changes


def update_settings(extra, uninstall):
    hook_cmd = shlex.quote(str(BIN)) + " record"
    ok = True
    for shown, real in settings_files(extra):
        try:
            text = real.read_text()
        except FileNotFoundError:
            text = None
        except OSError as e:
            say(f"settings: cannot read {shown}: {e}")
            ok = False
            continue
        try:
            s = json.loads(text) if text and text.strip() else {}
            if not isinstance(s, dict):
                raise ValueError("top level is not an object")
            if uninstall:
                changes, warnings = remove_settings(s), []
            else:
                changes, warnings = add_settings(s, hook_cmd, str(BIN))
        except ValueError as e:
            by_hand = "Remove the hook and env.BROWSER" if uninstall else "Add the hook and env.BROWSER"
            say(f"settings: skipped {shown}: {e}. {by_hand} there by hand (see SKILL.md).")
            ok = False
            continue
        for w in warnings:
            say(f"settings: {shown}: {w}")
        if not changes:
            say(f"settings: nothing to change in {shown}")
            continue
        did(f"{shown}: " + ", ".join(changes))
        if not DRY:
            write_atomic(real, json.dumps(s, indent=indent_of(text or ""), ensure_ascii=False) + "\n")
    return ok


# ---- the default-browser app -----------------------------------------------

def app_source_hash():
    h = hashlib.sha256()
    for name in ("LinkRouter.swift", "Info.plist", "build.sh"):
        h.update((APP_SRC / name).read_bytes())
    return h.hexdigest()


def default_browser():
    if not APP_BIN.exists():
        return None
    r = subprocess.run([str(APP_BIN), "--default-status"], capture_output=True, text=True, timeout=30)
    return r.stdout.strip() or None


def build_app(force):
    want = app_source_hash()
    try:
        have = APP_STAMP.read_text().strip()
    except OSError:
        have = ""
    if APP_BIN.exists() and have == want and not force:
        say(f"app: up to date ({APP})")
        return True
    if not shutil.which("swiftc"):
        say("app: not built. It needs the Swift compiler: run `xcode-select --install`, then run this again.")
        return False
    did(f"build {APP}")
    if DRY:
        return True
    r = subprocess.run(["/bin/bash", str(APP_SRC / "build.sh")], capture_output=True, text=True)
    if r.returncode != 0:
        say("app: build failed:\n" + (r.stderr or r.stdout).strip())
        return False
    STATE.mkdir(parents=True, exist_ok=True)
    APP_STAMP.write_text(want + "\n")
    return True


def make_default():
    if default_browser() == BUNDLE_ID:
        say("default browser: already Claude Link Router")
        return True
    did("make Claude Link Router the default browser (macOS shows a dialog; choose 'Use \"Claude Link Router\"')")
    if DRY:
        return True
    r = subprocess.run([str(APP_BIN), "--make-default"], capture_output=True, text=True, timeout=300)
    say(r.stdout.strip())
    if r.returncode != 0:
        say("default browser: not changed (the dialog was declined or timed out). Nothing else depends on it.")
    return r.returncode == 0


# ---- uninstall -------------------------------------------------------------

def uninstall(extra, purge):
    if default_browser() == BUNDLE_ID:
        did("give the default browser back to the one it replaced (macOS shows a dialog)")
        if not DRY:
            r = subprocess.run([str(APP_BIN), "--restore"], capture_output=True, text=True, timeout=300)
            say(r.stdout.strip())
            if r.returncode != 0:
                say("Stopped: Claude Link Router is still the default browser, and removing it now would leave "
                    "links with nowhere to go. Pick another default browser in System Settings > Desktop & Dock, "
                    "then run this again.")
                return 1
    update_settings(extra, uninstall=True)
    if APP.exists():
        did(f"remove {APP}")
        if not DRY:
            subprocess.run([LSREGISTER, "-u", str(APP)], capture_output=True)
            shutil.rmtree(APP)
            subprocess.run(["/usr/bin/defaults", "delete", BUNDLE_ID], capture_output=True)
            try:
                APP_STAMP.unlink()
            except OSError:
                pass
    if BIN.exists():
        did(f"remove {BIN}")
        if not DRY:
            BIN.unlink()
    for d in (STATE, CONFIG):
        if d.exists():
            if purge:
                did(f"remove {d}")
                if not DRY:
                    shutil.rmtree(d)
            else:
                say(f"kept {d} (--purge removes it)")
    return 0


def main():
    global DRY
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--app", action="store_true", help="build the default-browser app")
    ap.add_argument("--rebuild", action="store_true", help="build the app even if it is up to date")
    ap.add_argument("--make-default", action="store_true", help="make the app the default browser (implies --app)")
    ap.add_argument("--no-backfill", action="store_true", help="skip reading past transcripts")
    ap.add_argument("--config-dir", action="append", default=[], metavar="DIR",
                    help="another Claude Code config dir to set up (repeatable)")
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--purge", action="store_true", help="with --uninstall: also delete records and overrides")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    DRY = a.dry_run
    if sys.platform != "darwin":
        say("This router is macOS-only: it opens profiles with `open -na <browser> --args --profile-directory=...` "
            "and reads browser profiles under ~/Library/Application Support.")
        return 2
    if a.uninstall:
        return uninstall(a.config_dir, a.purge)

    install_script()
    ok = update_settings(a.config_dir, uninstall=False)
    if a.app or a.rebuild or a.make_default:
        built = build_app(a.rebuild)
        ok = ok and built
        if a.make_default and built:
            make_default()
    if DRY:
        return 0
    if not a.no_backfill:
        say("\nReading past transcripts for artifacts published before the hook existed "
            "(a minute or two on a large history)...")
        subprocess.run([str(BIN), "backfill"])
    say()
    subprocess.run([str(BIN), "status"])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
