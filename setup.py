#!/usr/bin/env python

import io
from os.path import dirname
from os.path import join

from setuptools import find_packages
from setuptools import setup


def read(*names, **kwargs):
    with io.open(
            join(dirname(__file__), *names),
            encoding=kwargs.get('encoding', 'utf8')
    ) as fh:
        return fh.read()


setup(
    name='qmi',
    version='0.40.0-beta.0',
    description='The Quantum Measurement Infrastructure framework',
    long_description="{}\n{}".format(
        read('README.md'),
        read('CHANGELOG.md')),
    author='QuTech',
    author_email='',
    url='https://github.com/QuTech-Delft/QMI',
    packages=find_packages(include=["qmi*"]),
    package_data={"qmi": ["py.typed"], "qmi.instruments.zurich_instruments": ["hdawg_command_table.schema"]},
    include_package_data=True,
    zip_safe=False,
    classifiers=[
        # complete classifier list: http://pypi.python.org/pypi?%3Aaction=list_classifiers
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Science/Research',
        'Operating System :: Unix',
        'Operating System :: POSIX',
        'Operating System :: Microsoft :: Windows',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: Implementation :: CPython',
        'Programming Language :: Python :: Implementation :: PyPy',
        'Topic:: Scientific / Engineering:: Physics',
    ],
    project_urls={
        'Changelog': 'https://github.com/QuTech-Delft/QMI/CHANGELOG.md',
        'Issue Tracker': 'https://github.com/QuTech-Delft/QMI/issues',
    },
    keywords=[
        # eg: 'keyword1', 'keyword2', 'keyword3',
    ],
    python_requires='>=3.8, <4',
    install_requires=[
        # For generating an installable package and deploying
        'setuptools',
        'wheel',
        'twine',
        # For scientific data processing and visualisation
        'numpy',
        'scipy',
        'h5py>=3.7.0',
        # For hardware interfacing
        'pyserial',
        'pyusb',
        'python-vxi11',
        # For miscellaneous functionality
        'pytz',
        'psutil',
        'colorama',
        'jsonschema',
        # Instrument AD2
        'pydwf',
    ],
    extras_require={
        'dev': [
            # For generating an installable package and deploying
            'setuptools',
            'wheel',
            'twine',
            # For static code checks
            "astroid==2.12.2",
            "coverage",
            'pylint',
            'mypy',
            "radon",
            # version bump
            'bump2version'
        ],
        'rtd': [
            # For generating documentation
            'sphinx', 'sphinx_rtd_theme'
        ]
    },
    entry_points={
        'console_scripts': [
            'qmi_proc = qmi.tools.proc:main',
            'qmi_adbasic_parser = qmi.utils.adbasic_parser:main',
            'qmi_adbasic_compiler = qmi.utils.adbasic_compiler:main'
        ]
    },
    scripts=[
        'bin/qmi_tool',
        'bin/qmi_run_contexts',
        'bin/qmi_hdf5_to_mat',
        'bin/instruments/qmi_anapico_apsin',
        'bin/instruments/qmi_mcc_usb1808x',
        'bin/instruments/qmi_newport_ag_uc8',
        'bin/instruments/qmi_quantum_composer_9530',
        'bin/instruments/qmi_siglent_ssa3000x',
        'bin/instruments/qmi_srs_dc205',
        'bin/instruments/qmi_thorlabs_k10cr1',
        'bin/instruments/qmi_timebase_dim3000',
        'bin/instruments/qmi_wavelength_tclab',
        'bin/instruments/qmi_wieserlabs_flexdds'
    ]
)
