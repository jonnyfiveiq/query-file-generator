.PHONY: help install build test clean examples lint

help:
	@echo "Query File Generator Collection - Development Commands"
	@echo ""
	@echo "Available targets:"
	@echo "  install     - Install collection and dependencies"
	@echo "  build       - Build collection tarball"
	@echo "  test        - Run test playbook"
	@echo "  examples    - Generate example query files"
	@echo "  lint        - Run linters on collection"
	@echo "  clean       - Remove build artifacts"
	@echo ""
	@echo "Requirements:"
	@echo "  - Python 3.8+"
	@echo "  - Ansible 2.9+"
	@echo "  - ANTHROPIC_API_KEY environment variable"

install:
	@echo "Installing Python dependencies..."
	pip install -r requirements.txt
	@echo "Installing collection..."
	ansible-galaxy collection install . --force

build:
	@echo "Building collection tarball..."
	ansible-galaxy collection build --force
	@ls -lh ansible_bu-query_file_generator-*.tar.gz

test:
	@echo "Running test playbook..."
	@if [ -z "$$ANTHROPIC_API_KEY" ]; then \
		echo "ERROR: ANTHROPIC_API_KEY environment variable not set"; \
		exit 1; \
	fi
	ansible-playbook playbooks/test_generator.yml

examples:
	@echo "Generating example query files..."
	@mkdir -p ./generated_examples
	@echo "Generating Azure example..."
	ansible-playbook playbooks/generate_azure_queries.yml
	@echo "Generating VMware example..."
	ansible-playbook playbooks/generate_vmware_queries.yml
	@echo "Generated files:"
	@ls -lh ./*_event_query.yml 2>/dev/null || echo "  (run with ANTHROPIC_API_KEY set)"

lint:
	@echo "Running yamllint..."
	yamllint galaxy.yml examples/*.yml playbooks/*.yml || true
	@echo "Running ansible-lint..."
	ansible-lint playbooks/*.yml || true
	@echo "Running Python linters..."
	pylint plugins/modules/*.py || true

clean:
	@echo "Cleaning build artifacts..."
	rm -f ansible_bu-query_file_generator-*.tar.gz
	rm -rf test_output/
	rm -f *_event_query.yml
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	@echo "Clean complete"

# Development helpers
dev-setup: install
	@echo "Setting up development environment..."
	pip install pylint ansible-lint yamllint
	@echo "Development environment ready!"

# Quick test with Azure
quick-test:
	@echo "Quick test with Azure collection..."
	@echo "---" > /tmp/quick_test.yml
	@echo "- hosts: localhost" >> /tmp/quick_test.yml
	@echo "  tasks:" >> /tmp/quick_test.yml
	@echo "    - ansible_bu.query_file_generator.generate_query_file:" >> /tmp/quick_test.yml
	@echo "        collection_source: 'https://github.com/ansible-collections/azure'" >> /tmp/quick_test.yml
	@echo "        collection_name: 'azure.azcollection'" >> /tmp/quick_test.yml
	@echo "        output_path: './test_azure_query.yml'" >> /tmp/quick_test.yml
	ansible-playbook /tmp/quick_test.yml
	@echo "Generated file:"
	@cat test_azure_query.yml

# CI/CD targets
ci-test:
	@echo "Running CI tests..."
	ansible-lint playbooks/*.yml
	ansible-playbook playbooks/test_generator.yml --check

publish:
	@echo "Publishing to Ansible Galaxy..."
	@if [ -z "$$GALAXY_TOKEN" ]; then \
		echo "ERROR: GALAXY_TOKEN environment variable not set"; \
		exit 1; \
	fi
	ansible-galaxy collection build --force
	ansible-galaxy collection publish ansible_bu-query_file_generator-*.tar.gz --token="$$GALAXY_TOKEN"
