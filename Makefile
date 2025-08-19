# Otto BGP Development Makefile

.PHONY: help venv lint test run clean

# Default target
help:
	@echo "Otto BGP Development Commands"
	@echo "============================"
	@echo ""
	@echo "Setup Commands:"
	@echo "  venv            Create virtual environment and install dependencies"
	@echo ""
	@echo "Development Commands:"
	@echo "  lint            Run code linting"
	@echo "  test            Run all tests"
	@echo "  run             Run Otto BGP (example usage)"
	@echo "  clean           Clean up temporary files"

# Setup targets
venv:
	@echo "🔧 Creating virtual environment..."
	python3 -m venv venv
	venv/bin/pip install --upgrade pip
	venv/bin/pip install -r requirements.txt
	@echo "✓ Virtual environment created"
	@echo "  Activate with: source venv/bin/activate"

# Development targets  
lint:
	@echo "🔍 Running code linting..."
	venv/bin/python -m flake8 otto_bgp/ --count --select=E9,F63,F7,F82 --show-source --statistics

test:
	@echo "🧪 Running tests..."
	venv/bin/python -m pytest tests/ -v

run:
	@echo "🚀 Example Otto BGP usage:"
	@echo "  venv/bin/python -m otto_bgp.main --help"
	@echo "  venv/bin/python -m otto_bgp.main policy sample_input.txt -o output.txt"

# Cleanup targets
clean:
	@echo "🧹 Cleaning up temporary files..."
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	rm -rf .pytest_cache/
	rm -rf htmlcov/
	rm -rf .coverage
	rm -rf coverage.xml
	@echo "✅ Cleanup completed"