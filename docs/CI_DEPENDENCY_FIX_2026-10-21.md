# CI dependency repair, 2026-10-21

The first public GitHub Actions run exposed an unavailable Windows Python patch and outdated locked dependencies. The repair keeps Python 3.12, hash-checked installation, and both dependency-audit steps.

## Changes

- `.github/workflows/ci.yml`: change the three `setup-python` inputs from `3.12.14` to `3.12`. The action resolves an available patch for each runner. The official manifest checked on this date provides Windows x64 builds through 3.12.10, but no Windows 3.12.14 build. The existing Linux Docker image and its digest remain unchanged.
- `requirements.txt`: update the direct Pillow pin from 12.2.0 to 13.0.0. The upstream 13.0.0 security release fixes vulnerabilities that are not all fixed by 12.3.0. Python 3.12 is supported.
- `requirements-lock.txt`: regenerate universal distribution hashes; Pillow is the only changed package among 27 pins.
- `requirements-dev-lock.txt`: regenerate hashes; Pillow and certifi are the only changed packages among 63 pins. certifi moves from 2026.7.22 to 2026.10.19, addressing PYSEC-2026-4320. certifi is a development transitive dependency and is absent from the production lock.
- No audit suppression, dependency removal, application-source change, global package installation, Docker operation, database operation, or project-license change forms part of this repair.

## Generation

The existing generator is uv 0.12.0. Original lockfiles were copied to the local ignored `work/ci-dependency-check/before/` directory. A temporary constraints file preserved every existing development pin and platform marker except Pillow and certifi, and pinned certifi to 2026.10.19. This prevents unrelated upgrades. `requirements-dev.txt` also retains its production-lock constraint.

The following commands were executed from the repository root:

```text
uv pip compile requirements.txt --constraint work/ci-dependency-check/preserved-constraints.txt --python work/ci-dependency-check/runtime-venv/Scripts/python.exe --python-version 3.12 --universal --generate-hashes --no-annotate --output-file requirements-lock.txt --no-python-downloads --quiet
uv pip compile requirements-dev.txt --constraint work/ci-dependency-check/preserved-constraints.txt --python work/ci-dependency-check/runtime-venv/Scripts/python.exe --python-version 3.12 --universal --generate-hashes --no-annotate --output-file requirements-dev-lock.txt --no-python-downloads --quiet
```

The temporary constraints file is a local migration input, not an application runtime requirement. Subsequent normal lock regeneration uses the commands in `docs/OPERATIONS.md`; uv prefers the existing output pins unless an upgrade is requested.

## Verification

Two new project-local virtual environments used the existing bundled CPython 3.12.14 interpreter on Windows x64. No global Python installation was changed. In the commands below, `runtime-python` and `dev-python` denote the respective `work/ci-dependency-check/runtime-venv/Scripts/python.exe` and `work/ci-dependency-check/dev-venv/Scripts/python.exe` executables.

| Executed command | Result |
| --- | --- |
| `runtime-python -m pip install --require-hashes -r requirements-lock.txt --disable-pip-version-check` | Exit 0, fresh production installation |
| `dev-python -m pip install --require-hashes -r requirements-dev-lock.txt --disable-pip-version-check` | Exit 0, fresh development installation |
| `runtime-python -m pip check` | Exit 0, no broken requirements |
| `dev-python -m pip check` | Exit 0, no broken requirements |
| `dev-python -m pip_audit -r requirements-lock.txt --no-deps --disable-pip --format json` | Exit 0, 27 dependencies, zero known vulnerabilities |
| `dev-python -m pip_audit -r requirements-dev-lock.txt --no-deps --disable-pip --format json` | Exit 0, 62 applicable dependencies, zero known vulnerabilities |
| `dev-python -m ruff check .` | Exit 0 |
| `dev-python -m unittest discover -s scripts -p "test_*.py"` | Exit 0, 7 tests passed |
| `dev-python -m pytest -q -m "not postgresql"` | Exit 0, 385 passed, 35 PostgreSQL tests deselected, 23 warnings (383.85 seconds) |

The development lock also includes `httpx2-jsfetch` for Emscripten; its environment marker does not apply to the Windows/Linux server targets and it is not included in this Windows audit count. `--no-deps --disable-pip` retains the existing CI audit approach for fully pinned lockfiles; separate fresh `--require-hashes` installations verified dependency resolution and artifact integrity. No findings were ignored.

The 23 pytest warnings comprise one expected oversized-image decompression-bomb warning from the rejection test and 22 Windows temporary-directory cleanup warnings (`WinError 145`). The test assertions passed; this task did not remove unrelated temporary directories.

The test subprocess disabled dotenv loading with `PYTHON_DOTENV_DISABLED=1` and used repository-local imports. Existing backend tests allocate isolated SQLite databases and temporary media directories. Local production configuration and data were not used. Logs, machine-readable checks, original lockfiles, and the version-only diff are retained locally under `work/ci-dependency-check/`.

## Sources and remaining verification

- Failed public run: https://github.com/susmogus228/pitomo/actions/runs/39603711419
- Official setup-python version selection: https://github.com/actions/setup-python/blob/main/docs/advanced-usage.md#specifying-a-python-version
- Official runner-version manifest: https://github.com/actions/python-versions/blob/main/versions-manifest.json
- Official uv compilation and constraints documentation, also checked through Context7: https://docs.astral.sh/uv/pip/compile/
- Pillow 13.0.0 security release: https://pillow.readthedocs.io/en/stable/releasenotes/13.0.0.html
- certifi advisory: https://github.com/pypa/advisory-database/blob/main/vulns/certifi/PYSEC-2026-4320.yaml
- certifi fixed release: https://pypi.org/project/certifi/2026.10.19/

Local audit results reflect the advisory data available on this date and do not certify the whole application. At completion of the first local dependency repair, hosted checks remained pending. The follow-up below records the next run and its separate runner-isolation fix. Local verification did not start PostgreSQL, rebuild Docker images, or modify volumes.

## Hosted-run follow-up: isolate runner packages

Run [39606658324](https://github.com/susmogus228/pitomo/actions/runs/39606658324) passed frontend, container, PostgreSQL, and audit jobs. Windows SQLite failed at `pip check`: the runner's preinstalled pipx 1.18.4 required filelock >=4.2 and platformdirs >=4.12.2, whereas the application's development lock pinned 4.0.6 and 4.12.1. The clean local virtual environments had passed because they did not contain the runner's pipx installation. Ubuntu SQLite stopped after 72 tests when matrix fail-fast cancelled it; its log did not report an assertion failure.

The workflow now creates a project-local `.venv` after `setup-python` in the SQLite, PostgreSQL, and audit jobs. A `shell: python` step calls `venv.create(..., with_pip=True, system_site_packages=False)`. It appends the absolute `.venv/Scripts` directory on Windows, or `.venv/bin` on POSIX, to the UTF-8 `GITHUB_PATH` file. GitHub prepends this directory for subsequent steps in the job. A separate Python step checks `sys.prefix != sys.base_prefix` before installation. This fails early if PATH resolution selects the base interpreter.

The package pins remain unchanged. Hash-checked installation, `pip check`, both dependency audits, and the existing application tests remain enabled. The runner's global pipx installation remains in place.

Local checks for this workflow-only follow-up:

- Parse the workflow with the already installed PyYAML 6.0.3: passed.
- Parse the Python creation and guard blocks in all three jobs: passed.
- Execute each creation block with mocked venv creation and file output for both `os.name == "nt"` and POSIX: the absolute Scripts/bin path and newline matched, six checks passed.
- Check step order: environment creation and interpreter guard precede hash-checked installation in each job.
- Execute the interpreter guard in the existing clean local development venv: passed.
- Confirm that SQLite `pip check` and both audit commands remain present: passed.

These checks verify workflow syntax and path selection. The earlier 385-test backend result remains the application regression evidence; the workflow-only change did not repeat that suite. The next hosted run must confirm both runner platforms and the new isolation steps.

Official references:

- [GitHub built-in Python shell](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsshell), supported across runner platforms.
- [GITHUB_PATH](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-commands#adding-a-system-path), applied to subsequent steps.
- [Python 3.12 venv](https://docs.python.org/3.12/library/venv.html), isolated site-packages and platform-specific script directories.
