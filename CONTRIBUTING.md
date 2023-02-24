# Contributing

Contributions are welcome, and they are greatly appreciated!

## Bug reports

When [reporting a bug](https://github.com/QuTech-Delft/QMI/issues) please include:

* Your operating system name and version of qmi.
* Any details about your local setup that might be helpful in troubleshooting.
* Detailed steps to reproduce the bug.

## Feature requests and feedback

The best way to send feedback is to file an issue at https://github.com/QuTech-Delft/QMI/issues.

If you are proposing a feature:

* Explain in detail how it would work.
* Keep the scope as narrow as possible, to make it easier to implement.

## Development

To set up `QMI` for local development:

1. Clone QMI <https://github.com/QuTech-Delft/QMI.git>:
    ```sh
    git clone git@github.com/QuTech-Delft/QMI.git
    ```
2. Important: setup and activate virtual environment <https://docs.python.org/3/tutorial/venv.html>. This ensures that
during the following step, the editable installation of the pip package is not affecting the rest your system.
3. Install developer dependencies using pip:
   ```shell script
   pip install -e .[dev]
   ```
4. Create a branch for your feature
   ```
   git checkout -b name-of-your-bugfix-or-feature 
   ```
5. When you're done making your changes run the mypy and unit-tests:
   ```
   mypy qmi/
   python3 -m unittest discover -s=tests -p "test_*.py"
   ```
6. Submit a pull request using the GitHub website.
