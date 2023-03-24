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


### Maintainability

Code maintainability is evaluated using [Radon](https://radon.readthedocs.io/en/latest/). Two metrics are considered:

 - Cyclomatic complexity
 - Maintainability index

To run Radon from the command line:

    $ radon cc
    $ radon mi

Two wrapper scripts are provided in the `scripts/` directory that are also used in the CI environment.


Unit tests
----------

Unit tests are executed in the CI environment against different Python versions: 3.8, 3.9 and 3.10. Code coverage of
the tests is computed using [Coverage.py](https://coverage.readthedocs.io/en/coverage-5.3.1/). To run the tests
locally, use the scripts provided in `scripts/`:

    $ run_unit_tests.sh
    $ run_unit_tests_with_coverage.sh

When unit tests are run locally, the Python version you have installed will be used.


CI configuration
----------------

Code quality analysis, maintainability analysis and unit tests are executed on all branches when changes are pushed
to the repository.

The pipelines are configured in `.github\workflows` and consists of four files:

  1. github-ci.yml
  2. pull_request.yml
  3. schedule-full-ci-test-main.yml
  4. python_publish.yml

In the first three workflows, the following tests are performed:
- The code quality and maintainability analyses and unit-test coverage are performed, as these metrics are considered as quality indicators for the code base (which includes
tests).
- Unit-tests are performed.
  - However, since this implies that unit tests are executed twice (coverage AND unit-testing), we might consider dropping the latter step.
- On push to a branch, tests are executing only with Python 3.11. When changes are pushed to a pull request, the tests are rerun parallel also with Python 3.8, 3.9 and 3.10. With the 3.10 version, the quality badges are created.
- The fourth workflow packages the source code into an installable Python package.


### Acceptance criteria

The following limits are defined for code quality and maintainability metrics:

 - Pylint score: at least 8.0
 - Mypy: 0 errors
 - Cyclomatic complexity: at most 30
 - Maintainability index: at least 20
 - Code coverage: at least 80%

If any of the metrics does not comply to the set thresholds, the corresponding job fails.
