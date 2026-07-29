# Contributing to Auto-Label-Owl

Thanks for your interest in contributing to [Auto-Label-Owl](https://github.com/ajaykumaar/Auto-Label-Owl).

## Development setup

```bash
git clone https://github.com/ajaykumaar/Auto-Label-Owl.git
cd Auto-Label-Owl

python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python download_model.py
python app.py
```

Open http://localhost:5000

## Guidelines

- Keep changes focused; prefer small pull requests.
- Match the existing code style (Flask backend, vanilla JS frontend).
- Do not commit model weights, personal images, or labeled datasets.
- Update the README when you change setup steps or user-facing behavior.
- Before opening a PR, smoke-test: start the app, label a few images, open Review, Finish, and download.

## Reporting issues

Open an issue at [github.com/ajaykumaar/Auto-Label-Owl/issues](https://github.com/ajaykumaar/Auto-Label-Owl/issues) and include:

- OS and Python version
- GPU / CPU and whether CUDA is available
- Steps to reproduce
- Expected vs actual behavior
- Relevant console / browser errors (no private images)

## Code of conduct

Be respectful and constructive. Harassment or personal attacks are not acceptable.
