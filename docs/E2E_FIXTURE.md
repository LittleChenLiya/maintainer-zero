# Offline repository end-to-end fixture

The fixture under tests/fixtures/e2e-repository is a deliberately small, real
Git repository used by tests/test_e2e_fixture.py. The test copies it into a
temporary directory, initializes a local Git history, and runs the CLI path
used by a repository owner:

1. analyze all three built-in drills;
2. write JSON, Markdown, HTML, SARIF, and recovery drafts;
3. rerun against the report as a baseline;
4. introduce a dependency explosion and assert that the score-regression gate
   fails.

The fixture includes CODEOWNERS, CI and release workflows, Python and Node
dependency manifests, and a publishing configuration. It contains no network
credentials and the test never calls GitHub or reads environment tokens. The
repository identity is anonymized by the fixture's continuity.json config.

Run the offline check with:

~~~powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
python -m pytest -q tests/test_e2e_fixture.py
~~~

Generated files are written only below pytest's temporary directory; no fixture
file is modified in place.
