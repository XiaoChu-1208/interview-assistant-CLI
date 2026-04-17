# Releasing

We publish to PyPI from GitHub Actions using **Trusted Publishing (OIDC)**, so no API token is stored anywhere.

> If anything below confuses you, run the steps top-to-bottom; they're idempotent.

---

## One-time setup (only needed before the FIRST release)

### 1. Reserve the project name on PyPI

The project name `interview-assistant` is published as a fresh project; PyPI will create it on first upload. To enable token-less publishing, we register a **pending publisher** *before* the first upload.

1. Go to <https://pypi.org/account/register/> and create an account if you don't already have one. Enable 2FA (TOTP or hardware key) — PyPI now requires it for publishers.
2. Open <https://pypi.org/manage/account/publishing/> and scroll to **"Add a new pending publisher"**.
3. Fill in **exactly**:
   - **PyPI Project Name**: `interview-assistant`
   - **Owner**: `XiaoChu-1208`
   - **Repository name**: `interview-assistant-CLI`
   - **Workflow name**: `publish.yml`
   - **Environment name**: `pypi`
4. Click **Add**.

### 2. Create the matching environment in GitHub

1. Go to <https://github.com/XiaoChu-1208/interview-assistant-CLI/settings/environments>.
2. Click **New environment**, name it exactly **`pypi`** (must match step 1).
3. (Optional but recommended) Add a **required reviewer** (yourself), so a release can't go out without you clicking approve. This prevents accidental tag-pushes from publishing.

### 3. Flip the publish switch on

The publish workflow's `pypi` job is gated behind a repo variable, so PyPI uploads are opt-in (this prevents the "Failed to deploy to pypi" red X you'd otherwise see on every tag push when Trusted Publisher isn't set up yet).

1. Go to <https://github.com/XiaoChu-1208/interview-assistant-CLI/settings/variables/actions>.
2. Under the **Variables** tab, click **New repository variable**.
3. Name: `PUBLISH_TO_PYPI`. Value: `true`.
4. Save.

That's it. From now on, pushing a `v*` tag will:
1. Build sdist + wheel
2. Verify bundled skills/templates/locales landed in the wheel
3. Upload to PyPI via OIDC
4. Create a GitHub Release with auto-generated notes

---

## Cutting a release

```bash
cd ship

# 1. Bump version in pyproject.toml
#    e.g. 0.1.0 -> 0.1.1
$EDITOR pyproject.toml

# 2. Local sanity check (builds + verifies wheel contents + twine check)
make check

# 3. Commit version bump
git add pyproject.toml
git commit -m "release: v0.1.1"
git push

# 4. Tag and push (kicks off the publish workflow)
make tag VERSION=0.1.1
```

Then watch <https://github.com/XiaoChu-1208/interview-assistant-CLI/actions>. If you set up the `pypi` environment with a required reviewer, you'll need to click **Approve** on the run.

After ~2 minutes:
- `pip install interview-assistant==0.1.1` works
- A new GitHub Release is created with auto-generated notes
- Badges in the README turn green / show the new version

---

## Testing a release without publishing (TestPyPI)

```bash
cd ship
make build      # builds dist/
twine upload --repository testpypi dist/*
pip install --index-url https://test.pypi.org/simple/ \
            --extra-index-url https://pypi.org/simple/ \
            interview-assistant
```

This requires a separate TestPyPI account and an API token in `~/.pypirc`. Useful to dry-run the full pipeline before claiming the real PyPI name.

---

## Rollback

PyPI does **not** allow re-uploading a yanked version with the same number. If you publish a broken release:

```bash
# Mark broken on PyPI (web UI: Manage project → release → "Yank")
# Then publish a fix:
$EDITOR pyproject.toml      # bump to e.g. 0.1.2
make check
git commit -am "release: v0.1.2 (fixes 0.1.1 …)"
git push
make tag VERSION=0.1.2
```

---

## Why Trusted Publishing instead of API tokens?

- No long-lived secret to rotate or leak
- The PyPI side cryptographically verifies that uploads originate from this exact repo + workflow + environment
- If the repo gets transferred / forked, old credentials don't follow

[PyPI Trusted Publishing docs](https://docs.pypi.org/trusted-publishers/) · [PyPA action](https://github.com/pypa/gh-action-pypi-publish)
