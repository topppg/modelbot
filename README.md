# Modelbot

Modelbot is an open-source project for reviewing Hugging Face model updates in GitHub pull requests.

## Pin a model

With Python 3.11 or later, create a `modelbot.toml` in your project:

```toml
[models]
"sshleifer/tiny-gpt2" = "main"
```

Run `python /path/to/modelbot/modelbot.py lock` from your project directory and commit the resulting `model.lock`. The lock records the exact revision, the model card's declared license, and the file identifiers reported by Hugging Face. This only fetches metadata. Run `lock` again after adding or changing tracked references. Existing pins with unchanged tracked references are preserved.

Run `python /path/to/modelbot/modelbot.py plan` to check for updates locally. It prints a JSON list of candidates and writes a proposed lockfile and Markdown report per model under `.modelbot-plan/`. Your committed lockfile stays at its current revision until you accept an update.

## Use the pin in your application

Your application should read the revision from the lockfile when loading the model:

```python
import json
from pathlib import Path

from transformers import AutoModelForCausalLM

repo = "sshleifer/tiny-gpt2"
revision = json.loads(Path("model.lock").read_text())["models"][repo]["revision"]
model = AutoModelForCausalLM.from_pretrained(repo, revision=revision)
```

## Enable update pull requests

In your public repository, enable **Allow GitHub Actions to create and approve pull requests** under **Settings → Actions → General**. Then add `.github/workflows/model-updates.yml`. Replace `MODEL_BOT_COMMIT_SHA` with the full commit SHA of the Modelbot version you want to run.

```yaml
name: Model updates
on:
  workflow_dispatch:
  schedule:
    - cron: '17 8 * * 1'
jobs:
  updates:
    permissions:
      contents: write
      pull-requests: write
    uses: topppg/modelbot/.github/workflows/modelbot.yml@MODEL_BOT_COMMIT_SHA
    with:
      validate: true
```

Run the workflow manually from the default branch to try it. Modelbot opens one pull request per changed model against that branch. It skips revisions already proposed, including closed pull requests. If a model already has an open update, close or merge it before the next update can be proposed.

With `validate: true`, add a Bash script at `.github/modelbot-validate`. It runs with the proposed `model.lock` in place and receives `MODELBOT_MODEL` and `MODELBOT_REVISION`. Use it to run a model load or your own evaluations against the exact candidate. A failed job creates a draft pull request with a link to the run. Set `validate: false` or omit it to generate metadata-only reports.

Validation defaults to a GitHub-hosted runner and can use a custom label via `validation-runner`. Use an isolated, disposable runner if you need a GPU. Give it no production secrets. GitHub can require maintainer approval for ordinary PR-triggered checks on pull requests opened by `GITHUB_TOKEN`; Modelbot's validation runs before the PR opens.

## Contributing

Start feature work from `main` and open a pull request back into `main`. Include the reason for the change and how you verified it.

Modelbot is available under the [MIT License](LICENSE).
