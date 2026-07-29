# Security Policy

## Supported versions

This project is a local single-user tool. Security fixes are applied on a best-effort basis to the latest `main` branch of [Auto-Label-Owl](https://github.com/ajaykumaar/Auto-Label-Owl).

## Reporting a vulnerability

Please **do not** open a public issue for security-sensitive reports.

Contact the maintainer via GitHub ([@ajaykumaar](https://github.com/ajaykumaar)) with:

- A description of the issue
- Steps to reproduce
- Impact assessment (if known)

We will acknowledge receipt when possible and work on a fix.

## Notes

- Do not expose `python app.py` (binds `0.0.0.0:5000`) to untrusted networks without a reverse proxy and access controls.
- Do not commit private images or credentials into the repository.
