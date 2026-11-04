# Modelbot

Modelbot is an open-source project for reviewing Hugging Face model updates in GitHub pull requests. It is currently a scaffold.

## First milestone

A repository lists the public Hugging Face models it wants to track. Modelbot resolves each configured branch or tag to an exact commit and records it in a lockfile. When the upstream reference moves, Modelbot proposes one model update per pull request against the repository's default branch.

The pull request shows the old and new revisions and summarizes changes to weights, configuration, chat templates, licensing, and executable files. A repository can supply its own validation command to test the candidate with its serving runtime and GPU. The report distinguishes passed, failed, and skipped checks.

Candidate model code is untrusted. Keep validation separate from the job that writes pull requests, and use a dedicated, isolated runner without repository write credentials or production secrets for any test that executes candidate code.

## Contributing

Start feature work from `main` and open a pull request back into `main`. Include the reason for the change and how you verified it.

Modelbot is available under the [MIT License](LICENSE).
