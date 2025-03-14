QMI Code Quality Assurance
==========================

We perform unit test and code quality analysis to maintain software quality.


Code analysis
-------------

### Code quality

Code quality is evaluated using [Pylint](https://www.pylint.org) and [Mypy](http://mypy-lang.org). Pylint primarily
checks coding style (in the broadest sense), but is also able to catch some errors (like referencing variables out of
scope). Mypy is a static type checker. It requires the code to be annotated.

It is strongly recommended to integrate Pylint and Mypy with your development environment, to catch any problems as
you work on the code base. The Pylint configuration is provided in `pylintrc`. The Mypy configuration is provided in
`mypy.ini`.

In any case, both tools can be run from the command line:

    $ pylint qmi/
    $ mypy qmi/


Unit tests
----------

Unit tests are executed in the CI environment against different Python versions: 3.11, 3.12 and 3.13. Code coverage of
the tests is computed using [Coverage.py](https://coverage.readthedocs.io/en/coverage-5.3.1/). To run the tests
locally, use:
```zsh
coverage run --branch -m unittest discover --start-directory=tests --pattern="test_*.py";
```

When unit tests are run locally, the Python version you have installed will be used.


CI configuration
----------------

Code quality analysis, maintainability analysis and unit tests are executed on all branches when changes are pushed
to the repository.

The pipelines are configured in `.github\workflows` and consists of four files:

  1. `push-ci.yml`
  2. `pull_request-ci.yml`
  3. `scheduled-full-ci.yml`
  4. `pypi_publish.yml`

with a support file `reusable-ci-workflows.yml`.

In the first three workflows, the following tests are performed:
- The code quality and maintainability analyses and unit-test coverage are performed, as these metrics are considered as quality indicators for the code base (which includes
tests).
- Unit-tests are performed and the coverage is calculated.
- On push to a branch, tests are executing only with Python 3.11. When changes are pushed to a pull request, the tests are rerun parallel also with Python 3.12 and 3.13. With the 3.11 version, the quality badges are created.

The fourth workflow packages the source code into an installable Python package.


### Acceptance criteria

The following limits are defined for code quality and maintainability metrics:

 - Pylint score: at least 9.0
 - Mypy: 0 errors
 - Code coverage: at least 90%

If any of the metrics does not comply to the set thresholds, the corresponding job fails.
