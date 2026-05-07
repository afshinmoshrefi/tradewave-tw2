# TW2 web-tier — convenience wrappers for the test suite.
# See /home/flask/tests/README.md for full setup notes.

PY := /home/flask/venv/bin/python
SUDO_FLASK := sudo -u flask

.PHONY: test test-unit test-db test-tier test-webhook test-session test-user

test:
	$(SUDO_FLASK) $(PY) -m pytest -ra --tb=short

test-unit:
	$(SUDO_FLASK) $(PY) -m pytest -ra --tb=short -m unit

test-db:
	$(SUDO_FLASK) $(PY) -m pytest -ra --tb=short -m db

test-tier:
	$(SUDO_FLASK) $(PY) -m pytest -ra --tb=short tests/test_tier_compat.py

test-webhook:
	$(SUDO_FLASK) $(PY) -m pytest -ra --tb=short tests/test_webhook_idempotency.py

test-session:
	$(SUDO_FLASK) $(PY) -m pytest -ra --tb=short tests/test_sealed_session.py

test-user:
	$(SUDO_FLASK) $(PY) -m pytest -ra --tb=short tests/test_lazy_create_user.py
