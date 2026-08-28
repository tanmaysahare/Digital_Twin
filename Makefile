# DigitalTwin.ai
#
# Every target delegates to tools/tasks.py so that the same steps run on
# Windows, macOS and Linux. On Windows without make, use make.cmd instead.

PYTHON ?= python

.DEFAULT_GOAL := help
.PHONY: help install lint lint-design format test test-python up down db migrate seed evaluate reference-sheets

help:
	@$(PYTHON) tools/tasks.py

install:
	@$(PYTHON) tools/tasks.py install

lint:
	@$(PYTHON) tools/tasks.py lint

lint-design:
	@$(PYTHON) tools/tasks.py lint-design

format:
	@$(PYTHON) tools/tasks.py format

test:
	@$(PYTHON) tools/tasks.py test

test-python:
	@$(PYTHON) tools/tasks.py test-python

up:
	@$(PYTHON) tools/tasks.py up

down:
	@$(PYTHON) tools/tasks.py down

db:
	@$(PYTHON) tools/tasks.py db

migrate:
	@$(PYTHON) tools/tasks.py migrate

seed:
	@$(PYTHON) tools/tasks.py seed

evaluate:
	@$(PYTHON) tools/tasks.py evaluate

reference-sheets:
	@$(PYTHON) tools/tasks.py reference-sheets
