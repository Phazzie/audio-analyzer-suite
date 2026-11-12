# Origin CI

GitHub Actions is not the CI for this repository. The GitHub account is billing-locked, and the owner is moving CI to Cursor Origin. Origin runs the workflows through the Depot app: GitHub Actions-syntax YAML in `.depot/workflows/`, on `depot-ubuntu-24.04`, after the repository is detached from GitHub.

This repository has no `.github/workflows` directory. Nothing was deleted. Depot CI below is the workflow that will run.

## Workflow map

| GitHub Actions workflow | Depot workflow | What runs |
| --- | --- | --- |
| None. `.github/workflows/` is not in the repo. | `.depot/workflows/ci.yml` | `verify` on pull requests and pushes to `main`. `ai-review` on pull requests only. |

`verify` uses the same install shape as the README and `server/Dockerfile` (`pip install` from the requirements files), locked to `requirements/ci.lock`:

1. Install `libsndfile1` with `sudo apt-get` when passwordless sudo exists, otherwise with `apt-get` (needed by `soundfile`)
2. `python -m pip install --upgrade pip`
3. `pip install --require-hashes -r requirements/ci.lock`
4. `python -m compileall -q client server`
5. `python -m unittest discover -s tests -v`
6. `node --test scripts/ai-review.test.mjs`
7. `node scripts/ai-review.mjs` with an empty `XAI_API_KEY`, which must print a skip line and exit 0

`ai-review` checks out the full history and runs `node scripts/ai-review.mjs` with `XAI_API_KEY`, `PR_NUMBER`, and `GITHUB_BASE_REF`. The script calls Grok (`grok-4.5` on `https://api.x.ai/v1/chat/completions`). When a pull request number is present it posts with:

```bash
origin pr comment "$PR_NUMBER" --body-file "$FILE" --edit-last --create-if-none
```

If `XAI_API_KEY` is unset, or the `origin` CLI is not on `PATH`, the script prints the reason (and the review text, once it has one) to the log and exits 0. A GitHub token is not required. When `GITHUB_TOKEN` and `GITHUB_REPOSITORY` are both set, the script tries a GitHub issue comment first and falls back to the Origin command if GitHub rejects it.

There is no lint config and there were no tests. `tests/test_smoke.py` compiles `client/` and `server/`, imports both clients, and runs the handler on an empty payload, a payload with no audio, and a one-second WAV generated in the test.

## Locked install

`requirements/ci.in` repeats the direct dependencies from `client/requirements.txt` and `server/requirements.txt`. `torch` and `torchaudio` are left out of the CI lock:

- `server/handler.py` does not import them. Analysis uses numpy, scipy, soundfile, and librosa.
- Deploys use `runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04`, which already provides CUDA PyTorch, then `pip install -r server/requirements.txt` inside that image.
- A CPU torch wheel would dominate CI time and would not match the GPU image.

Regenerate the lock when those requirement files change:

```bash
uv pip compile --python-version 3.12 --generate-hashes -o requirements/ci.lock requirements/ci.in
```

The lock is resolved for CPython 3.12, which is the interpreter `verify` installs. The RunPod image stays on the CUDA image's Python 3.11; this job does not build that image.

CI installs that lock with `--require-hashes`, which is the locked equivalent of `pip install -r client/requirements.txt` and `pip install -r server/requirements.txt`.

## GitHub-only pieces

Nothing in `.github/workflows` will be dropped, because that directory is absent. Do not add GitHub Actions workflows while billing is locked.

These paths stay outside CI:

| Piece | Why it is not a Depot job |
| --- | --- |
| `server/Dockerfile` image build and RunPod Serverless deploy | Manual, documented in the README. The worker image is the CUDA base above, not `depot-ubuntu-24.04`. |
| `RUNPOD_API_KEY` and `RUNPOD_ENDPOINT_ID` | Runtime secrets for `client/analyze.py` and `client/web_app.py`. The workflows do not read them. |
| Plugin and model work in `PRD.md` | Proposed. It is not implemented and has no workflow. |

## Secrets to enter in Depot

| Secret | Needed for CI | What happens without it |
| --- | --- | --- |
| `XAI_API_KEY` | Only for the Grok review comment on pull requests. | `ai-review` logs `AI review skipped: XAI_API_KEY is not set` and exits 0. |
| `RUNPOD_API_KEY` | No. | Client commands keep reading it from the environment at runtime. |
| `RUNPOD_ENDPOINT_ID` | No. | Same as the API key. |

Enter `XAI_API_KEY` in the Depot app's secret store for this repository. No other CI secret has to be copied off GitHub, because GitHub Actions was never configured here.
