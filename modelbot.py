"""Pin public Hugging Face model revisions using Hub metadata."""

import argparse
import json
import re
import sys
import tempfile
import tomllib
from pathlib import Path
from urllib.error import URLError
from urllib.parse import quote, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, build_opener

HUB = "https://huggingface.co"
REPO_ID = re.compile(r"[\w.-]+/[\w.-]+", re.ASCII)
COMMIT = re.compile(r"[a-f0-9]{40}")
SHA256 = re.compile(r"[a-f0-9]{64}")


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Hub:
    def __init__(self):
        self.opener = build_opener(NoRedirects())

    def get(self, url):
        parsed = urlsplit(url)
        if (parsed.scheme, parsed.netloc) != ("https", "huggingface.co"):
            raise ValueError("Hugging Face returned an unexpected pagination URL")
        with self.opener.open(url, timeout=30) as response:
            return json.load(response), response.headers.get("Link", "")

    def snapshot(self, repo, ref):
        base = f"{HUB}/api/models/{repo}"
        info, _ = self.get(f"{base}/revision/{quote(ref, safe='')}")
        if info.get("private") is not False or info.get("gated") is not False:
            raise ValueError(f"{repo}: only public, ungated models are supported")
        revision = info.get("sha", "")
        if not COMMIT.fullmatch(revision):
            raise ValueError(f"{repo}: Hugging Face did not return a full commit SHA")
        files = {}
        url = f"{base}/tree/{revision}?recursive=true"
        seen = set()
        while url:
            if url in seen:
                raise ValueError(f"{repo}: repeated file tree page")
            seen.add(url)
            entries, links = self.get(url)
            for entry in entries:
                if entry["type"] != "file":
                    continue
                path = entry["path"]
                lfs = entry.get("lfs")
                digest = lfs["oid"] if lfs else entry["oid"]
                expected = SHA256 if lfs else COMMIT
                if path in files or not expected.fullmatch(digest):
                    raise ValueError(f"{repo}: invalid file metadata for {path!r}")
                kind = "sha256" if lfs else "git-sha1"
                files[path] = {"digest": f"{kind}:{digest}", "size": entry["size"]}
            next_link = re.search(r'<([^>]+)>;\s*rel="next"', links)
            url = urljoin(url, next_link[1]) if next_link else None
        license_id = (info.get("cardData") or {}).get("license")
        return {"ref": ref, "revision": revision, "license": license_id, "files": files}


def read_config(path):
    with path.open("rb") as stream:
        config = tomllib.load(stream)
    models = config.get("models")
    if set(config) != {"models"} or not isinstance(models, dict) or not models:
        raise ValueError("configure at least one model in the [models] table")
    for repo, ref in models.items():
        if (
            not REPO_ID.fullmatch(repo)
            or any(part in {".", ".."} for part in repo.split("/"))
            or not isinstance(ref, str)
            or not ref.strip()
        ):
            raise ValueError(f"invalid model or tracked ref: {repo!r}")
    return models


def encode(data):
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


def read_lock(path):
    lock = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(lock, dict) or lock.get("version") != 1:
        raise ValueError("expected a version 1 Modelbot lockfile")
    models = lock.get("models")
    if not isinstance(models, dict):
        raise ValueError("invalid lockfile models table")
    for repo, snapshot in models.items():
        if (
            not isinstance(snapshot, dict)
            or not isinstance(snapshot.get("revision"), str)
            or not COMMIT.fullmatch(snapshot["revision"])
            or not isinstance(snapshot.get("files"), dict)
            or not isinstance(snapshot.get("ref"), str)
        ):
            raise ValueError(f"invalid lockfile snapshot for {repo!r}")
    return lock


def write_lock(path, lock):
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False
    ) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(encode(lock))
            stream.close()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def sync_lock(path, models, hub):
    previous = read_lock(path)["models"] if path.exists() else {}
    snapshots = {}
    for repo, ref in models.items():
        snapshot = previous.get(repo)
        if snapshot is None or snapshot["ref"] != ref:
            snapshot = hub.snapshot(repo, ref)
        snapshots[repo] = snapshot
    write_lock(path, {"version": 1, "models": snapshots})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("modelbot.toml"))
    parser.add_argument("--lock", type=Path, default=Path("model.lock"))
    parser.add_argument("command", choices=["lock"])
    args = parser.parse_args(argv)
    try:
        sync_lock(args.lock, read_config(args.config), Hub())
    except (OSError, URLError, ValueError, TypeError, KeyError) as exc:
        print(f"modelbot: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
