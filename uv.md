# UV Package Manager for Python

UV is a modern, high-performance package manager and installer for Python. This document outlines how to use UV in this project.

## Why UV?

- **Speed**: UV is significantly faster than pip, especially for large dependency trees
- **Reproducibility**: Better dependency resolution and lockfile support
- **Modern Features**: Native virtual environment management integrated with package installation

## Installation

If you don't have UV installed yet:

```bash
# Install UV using the official installer
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or on macOS with Homebrew
brew install uv
```

## Project Setup

### Creating a Virtual Environment

```bash
# Create a new virtual environment in the .venv directory
uv venv
```

### Installing Dependencies

```bash
# Install all dependencies from requirements.txt
uv pip install -r requirements.txt

# Install the project in development mode
uv pip install -e .
```

### Adding New Dependencies

```bash
# Add a new package
uv pip install <package-name>

# Add a new package and update requirements.txt
uv pip install <package-name> --update-requirements requirements.txt
```

## GitHub Actions Configuration

Our CI/CD workflows use UV to ensure consistent dependency installation. An example from our workflow:

```yaml
- name: Install uv
  uses: astral-sh/setup-uv@v5

- name: Install dependencies with uv
  run: |
    uv venv
    uv pip install -r requirements.txt
```

## Best Practices

1. **Always use UV instead of pip** for dependency management in this project
2. **Use `uv pip freeze > requirements.txt`** when updating dependency lists
3. **Keep the virtual environment outside of version control** (it should be in .gitignore)
4. **Use the same Python version locally as in CI** to avoid compatibility issues

## Troubleshooting

If you encounter issues with UV:

- Try deactivating and recreating the virtual environment: `rm -rf .venv && uv venv`
- Ensure you have the latest UV version: `uv --version`
- Clear the UV cache if needed: `uv cache clean`

## Additional Resources

- [UV Official Documentation](https://github.com/astral-sh/uv)
- [UV vs pip Comparison](https://astral.sh/blog/uv) 