# Contributing

Thank you for your interest in contributing!

## Getting Started

```bash
git clone https://github.com/YOUR_ORG/query-file-generator.git
cd query-file-generator
pip install -r requirements.txt
ansible-galaxy collection install .
```

## Testing

```bash
export DEBUG_PARSER=1
ansible-playbook playbooks/generate_vmware_queries.yml
```

## Code Style

- Follow PEP 8
- Add comments for complex logic
- Update documentation

## Pull Requests

1. Fork the repo
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit PR with description

## License

GPL-3.0 - See LICENSE
