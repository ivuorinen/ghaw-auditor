# GitHub Actions & Workflows Audit Report

**Generated:** 2025-10-02T00:00:00.000000

## Summary

- **Workflows:** 1
- **Actions:** 1
- **Policy Violations:** 0

## Analysis

- **Total Jobs:** 1
- **Reusable Workflows:** 0

### Triggers

- `pull_request`: 1
- `push`: 1

### Runners

- `ubuntu-latest`: 1

### Secrets

Total unique secrets: 1

- `GITHUB_TOKEN`

## Workflows

### Test Workflow

**Path:** `test.yml`

**Triggers:** `push`, `pull_request`

**Jobs:** 1

#### Jobs

- **test**
  - Runner: `ubuntu-latest`

## Actions Inventory

### Checkout

**Key:** `actions/checkout@abc123`

Checkout a Git repository

**Inputs:**

- `repository` (optional): Repository name with owner
- `ref` (optional): The branch, tag or SHA to checkout
