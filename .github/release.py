#!/usr/bin/env python3
"""Make GitHub releases from the AniBox zips pushed to this repository (see workflows/release.yml).

Every AniBox-<version>-windows.zip ever added to the checked-out history gets a release v<version>
(skipped when it exists), with the zip, "<zip>.sha256" and the notes latest.json had when that zip was
added. Then main gets latest.json pointing at the newest release's download, the README, and no zips
in its folder; an upload/* branch is deleted afterwards. Standard library + the gh command line.
"""

import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

ZIP_RE = re.compile(r"^AniBox-(\d+(?:\.\d+){1,3})-windows\.zip$")
REPO = os.environ.get("GITHUB_REPOSITORY", "patschgoo/AniBox-release")
BRANCH = os.environ.get("GITHUB_REF_NAME", "main")


def run(*args, check=True, capture=True):
    r = subprocess.run(list(args), capture_output=capture, text=True)
    if check and r.returncode != 0:
        raise SystemExit(f"{' '.join(args[:3])} … failed: {(r.stderr or r.stdout or '').strip()[-500:]}")
    return r


def git(*args, check=True):
    return run("git", *args, check=check).stdout.strip()


def vkey(version):
    return tuple(int(x) for x in version.split("."))


def zips_in_history():
    """{version: (commit that added the zip, file name)} for every zip added in HEAD's history."""
    out = {}
    log = git("log", "--no-renames", "--diff-filter=A", "--name-only", "--format=@%H", "HEAD")  # a replaced zip looks like a rename otherwise
    commit = None
    for line in log.splitlines():
        if line.startswith("@"):
            commit = line[1:]
        elif line and "/" not in line:
            m = ZIP_RE.match(line)
            if m and m.group(1) not in out:  # newest first: the latest time it was added wins
                out[m.group(1)] = (commit, line)
    return out


def manifest_at(commit):
    try:
        return json.loads(git("show", f"{commit}:latest.json"))
    except (SystemExit, ValueError):
        return {}


def release_exists(tag):
    return run("gh", "release", "view", tag, "--repo", REPO, check=False).returncode == 0


def make_release(version, commit, name, target, latest, workdir):
    tag = "v" + version
    if release_exists(tag):
        print(f"{tag}: release already there")
        return
    zip_path = Path(workdir) / name
    with open(zip_path, "wb") as fh:  # bytes as they are (git show to a file, not through text)
        subprocess.run(["git", "show", f"{commit}:{name}"], stdout=fh, check=True)
    data = zip_path.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    man = manifest_at(commit)
    if man.get("file") == name and man.get("sha256") and man["sha256"].lower() != sha:
        raise SystemExit(f"{name}: SHA-256 {sha} doesn't match latest.json ({man['sha256']}); no release made")
    side = Path(workdir) / (name + ".sha256")
    side.write_text(f"{sha}  {name}\n", encoding="utf-8")
    notes = (man.get("notes") if man.get("file") == name else "") or f"AniBox {version}."
    body = Path(workdir) / f"notes-{version}.md"
    body.write_text(f"{notes}\n\n**First install:** download the zip below, right-click it → Properties → tick "
                    f"**Unblock**, unpack it anywhere and double-click `AniBox.bat`.\n"
                    f"**Update:** AniBox offers it by itself (Download, then Update now).\n\n"
                    f"SHA-256 of `{name}`: `{sha}` ({len(data):,} bytes)\n", encoding="utf-8")
    run("gh", "release", "create", tag, str(zip_path), str(side), "--repo", REPO, "--title", f"AniBox {version}",
        "--notes-file", str(body), "--target", target, "--latest" if latest else "--latest=false")
    print(f"{tag}: release made ({len(data):,} bytes)")


def realign_tags(ref="origin/main"):
    """A release tag whose commit isn't on main any more (main's history was rewritten) moves to the
    commit on main with the same files and the same subject; the release stays with its tag name."""
    commits = []
    for line in git("log", "--format=%H %T %s", ref).splitlines():
        sha, tree, subject = line.split(" ", 2) if line.count(" ") >= 2 else (line.split(" ") + ["", ""])[:3]
        commits.append((sha, tree, subject))
    for tag in git("tag", "--list", "v*").split():
        sha = git("rev-parse", tag + "^{commit}")
        if run("git", "merge-base", "--is-ancestor", sha, ref, check=False).returncode == 0:
            continue
        tree, subject = git("rev-parse", tag + "^{tree}"), git("log", "-1", "--format=%s", sha)
        match = next((c for c, tr, s in commits if tr == tree and s == subject), None)
        if not match:
            print(f"{tag}: its commit isn't on main and has no twin there; left as it is")
            continue
        git("push", "--force", "origin", f"{match}:refs/tags/{tag}")
        print(f"{tag}: moved to {match[:7]} on main")


def main():
    found = zips_in_history()
    head = git("rev-parse", "HEAD")
    git("fetch", "origin", "main")
    main_sha = git("rev-parse", "origin/main")
    realign_tags()
    if not found:
        print("No AniBox zips in the history: nothing to release.")
    head_manifest = manifest_at(head)
    newest = max(found, key=vkey) if found else None
    with tempfile.TemporaryDirectory() as work:
        for version in sorted(found, key=vkey):  # oldest first, so the newest ends up as "Latest"
            commit, name = found[version]
            make_release(version, commit, name, main_sha, version == newest, work)

    # main: latest.json pointing at the release, the README, and no zips in the folder
    uploading = BRANCH.startswith("upload/")
    git("checkout", "-q", "-B", "main", "origin/main")
    if uploading:  # the new version's latest.json and README go to main; its zip doesn't
        for f in ("latest.json", "README.md"):
            if f == "latest.json" or head_manifest:
                git("checkout", head, "--", f)
    man = json.loads(Path("latest.json").read_text(encoding="utf-8")) if Path("latest.json").exists() else {}
    if man.get("file") and ZIP_RE.match(man["file"]):
        ver = ZIP_RE.match(man["file"]).group(1)
        man["url"] = f"https://github.com/{REPO}/releases/download/v{ver}/{man['file']}"
        Path("latest.json").write_text(json.dumps(man, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for p in Path(".").iterdir():
        if ZIP_RE.match(p.name):
            git("rm", "-q", "--", p.name)
    git("add", "--", *[f for f in ("latest.json", "README.md") if Path(f).exists()])
    if git("diff", "--cached", "--name-only"):  # only what this script staged
        git("commit", "-q", "-m", f"AniBox {man.get('version', '')}: download from the GitHub release")
        git("push", "origin", "main")
        print("main updated: latest.json points at the release; no zips in the folder")
    else:
        print("main already up to date")
    if uploading:
        git("push", "origin", "--delete", BRANCH)
        print(f"{BRANCH} deleted")


if __name__ == "__main__":
    main()
