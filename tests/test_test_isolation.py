"""Regression for the Phase 5 §9 incident.

The incident: a suite ran inside a container exporting
``DJANGO_SETTINGS_MODULE=config.settings.development``. pytest-django ranks the
environment variable above the ``pytest.ini`` value, so the run used development
settings, Celery was not eager, and ``.delay()`` published roughly ten tasks to
the live development Redis broker.

These tests reproduce that environment and prove it is now safe.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.conf import settings

from config.celery import app as celery_app


REPO_ROOT = Path(__file__).resolve().parent.parent
PROBE = "tests/test_isolation_probe.py"
DEVELOPMENT_SETTINGS = "config.settings.development"


def _run_pytest(probe_args, env_overrides):
    env = {**os.environ, **env_overrides}
    return subprocess.run(
        [sys.executable, "-m", "pytest", *probe_args, "-p", "no:cacheprovider", "-q"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )


@pytest.mark.slow
def test_accidental_development_settings_still_run_isolated():
    """The incident scenario, re-executed: development env, test runtime."""

    result = _run_pytest([PROBE], {"DJANGO_SETTINGS_MODULE": DEVELOPMENT_SETTINGS})
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    # pytest-django reports which source won; --ds from addopts must be it.
    assert "settings: config.settings.test (from option)" in output, output
    assert DEVELOPMENT_SETTINGS not in output.replace(
        f"DJANGO_SETTINGS_MODULE={DEVELOPMENT_SETTINGS}", ""
    ), output


@pytest.mark.slow
def test_removing_the_ds_option_fails_closed_instead_of_publishing():
    """Defence in depth: if --ds were ever dropped, the run must abort."""

    result = _run_pytest(
        [PROBE, "-p", "no:randomly", "-o", "addopts="],
        {"DJANGO_SETTINGS_MODULE": DEVELOPMENT_SETTINGS},
    )
    output = result.stdout + result.stderr
    assert result.returncode != 0, output
    assert "Tests must run under config.settings.test" in output, output
    # It aborted during configuration, so no test — and no .delay() — ever ran.
    assert " passed" not in output, output


def test_this_runtime_is_itself_isolated():
    assert settings.SETTINGS_MODULE == "config.settings.test"
    assert settings.CELERY_TASK_ALWAYS_EAGER is True
    assert settings.CELERY_TASK_EAGER_PROPAGATES is True
    assert celery_app.conf.broker_url == "memory://"


def test_the_development_broker_is_not_reachable_from_tests():
    from conftest import ExternalNetworkBlocked

    import kombu

    with pytest.raises(ExternalNetworkBlocked):
        connection = kombu.Connection("redis://redis:6379/0", connect_timeout=1)
        connection.connect()
