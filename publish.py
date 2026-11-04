"""Publish a trusted Modelbot plan from a GitHub Actions job."""

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from modelbot import REPO_ID


def run(*args):
    return subprocess.check_output(args, text=True).strip()


def pulls(repository, *fields):
    pages = run(
        "gh", "api", "--method", "GET", "--paginate", "--slurp",
        f"repos/{repository}/pulls", "-f", "per_page=100", *fields,
    )
    return [pr for page in json.loads(pages) for pr in page]


def push(branch):
    run(
        "git", "-c", "credential.helper=", "-c", "credential.helper=!gh auth git-credential",
        "push", f"--force-with-lease=refs/heads/{branch}:", "origin", f"HEAD:refs/heads/{branch}",
    )


def publish(repository, base, branch, repo, directory, validation):
    owner = repository.split("/", 1)[0]
    if pulls(repository, "-f", "state=all", "-f", f"head={owner}:{branch}", "-f", f"base={base}"):
        print(f"Already proposed {branch}")
        return
    prefix = branch.rsplit("/", 1)[0] + "/"
    for pr in pulls(repository, "-f", "state=open", "-f", f"base={base}"):
        head = pr["head"]
        if (head.get("repo") or {}).get("full_name") == repository and head["ref"].startswith(prefix):
            print(f"An update is already open for {repo}: {pr['html_url']}")
            return

    planned = directory / "model.lock"
    base_sha = run("git", "rev-parse", "HEAD")
    remote_base = run("git", "ls-remote", "--heads", "origin", f"refs/heads/{base}")
    if not remote_base or remote_base.split()[0] != base_sha:
        raise ValueError("The default branch moved; rerun Modelbot to refresh the plan")
    remote_branch = run("git", "ls-remote", "--heads", "origin", f"refs/heads/{branch}")
    if remote_branch:
        run("git", "fetch", "--depth=2", "origin", f"refs/heads/{branch}")
        tip = run("git", "rev-parse", "FETCH_HEAD")
        changed = run("git", "diff", "--name-only", f"{tip}^", tip)
        previous_lock = run("git", "show", f"{tip}^:model.lock")
        updated_lock = run("git", "show", f"{tip}:model.lock")
        if (
            changed != "model.lock"
            or previous_lock != Path("model.lock").read_text(encoding="utf-8").strip()
            or updated_lock != planned.read_text(encoding="utf-8").strip()
        ):
            raise ValueError(f"Existing branch {branch} does not match the planned change")
    else:
        shutil.copyfile(planned, "model.lock")
        run("git", "add", "--", "model.lock")
        run(
            "git", "-c", "user.name=github-actions[bot]",
            "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
            "commit", "-m", f"Update model pin for {repo}",
        )
        push(branch)

    run_url = f"https://github.com/{repository}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    outcome = {"success": "Passed", "failure": "Failed", "skipped": "Skipped"}[validation]
    body = (directory / "report.md").read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory() as temporary:
        body_path = Path(temporary) / "pull-request.md"
        body_path.write_text(
            body + f"\n### Validation\n\n{outcome}. [Workflow run]({run_url}).\n",
            encoding="utf-8",
        )
        args = ["--draft"] if validation == "failure" else []
        print(run(
            "gh", "pr", "create", "--repo", repository, "--base", base, "--head", branch,
            "--title", f"Update model pin for {repo}", "--body-file", str(body_path), *args,
        ))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--validation", choices=["success", "failure", "skipped"], required=True)
    args = parser.parse_args()
    if not REPO_ID.fullmatch(args.model) or not re.fullmatch(
        r"modelbot/[0-9a-f]{20}/[0-9a-f]{20}", args.branch
    ):
        parser.error("invalid model or update branch")
    publish(
        os.environ["GITHUB_REPOSITORY"], args.base, args.branch,
        args.model, args.plan, args.validation,
    )


if __name__ == "__main__":
    main()
