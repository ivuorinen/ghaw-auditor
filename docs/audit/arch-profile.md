# Architecture Profile

Detected automatically from the module import graph (`ast`-parsed, not inferred
from naming). Regenerate by re-running `/nitpicker arch-profile`.

## Detected pattern

**Layered pipeline with a dependency-injection composition root.**

A CLI shell delegates to a factory that wires concrete collaborators into a
service, which drives a fixed pipeline of single-responsibility components over
a shared set of pydantic data contracts.

```text
L0  cli.py                          Typer commands, console I/O, exit codes
L1  factory.py                      composition root (AuditServiceFactory)
L2  services.py                     AuditService / DiffService orchestration
L3  scanner parser resolver         pipeline components
    analyzer policy renderer differ
L4  github_client.py cache.py       infrastructure (HTTP, disk)
L5  models.py                       pydantic contracts (leaf)
```

Pipeline order inside `AuditService.scan`:

```text
scanner.find_workflows ─┐
                        ├─> parser.parse_workflow ─> analyzer.deduplicate_actions
scanner.find_actions ───┘                                    │
                                                             v
                                              resolver.resolve_actions (network)
                                                             │
                              analyzer.analyze_workflows <───┤
                              policy.validate           <────┘
                                        │
                                        v
                          renderer.render_json / render_markdown
                          differ.diff_workflows / diff_actions
```

## Verified invariants

Measured across all 14 modules:

| Invariant | Result |
| --- | --- |
| Dependencies flow strictly downward (no upward imports) | **holds** — 0 violations |
| No import cycles | **holds** — 0 cycles |
| `models` imports nothing from the package (leaf contract layer) | **holds** |
| `github_client` / `cache` import nothing from the package | **holds** |
| `scanner` imports nothing from the package | **holds** |
| Infrastructure is injected, never constructed by pipeline components | **holds** — only `factory` constructs `GitHubClient`/`Cache` |

Full measured graph:

| Module | Layer | Imports (in-package) |
| --- | --- | --- |
| `cli` | 0 | analyzer, differ, factory, models, parser, policy, renderer, scanner, services |
| `factory` | 1 | analyzer, cache, github_client, models, parser, policy, resolver, scanner, services |
| `services` | 2 | analyzer, differ, models, parser, policy, resolver, scanner |
| `resolver` | 3 | cache, github_client, models, parser |
| `analyzer`, `differ`, `parser`, `policy`, `renderer` | 3 | models |
| `scanner` | 3 | — |
| `github_client`, `cache`, `models` | 4–5 | — |

## Known deviation

`cli.inventory` (`cli.py:185-188`) and `cli.validate` (`cli.py:220-222`)
construct `Scanner`, `Parser` and `Analyzer` directly instead of going through
`AuditServiceFactory`, bypassing L1 and L2. Only `scan` uses the composition
root.

This duplicates the factory's wiring (`factory.py:46-48`) and is the structural
reason those two commands diverge from `scan` in behaviour: they cannot receive
`exclude_patterns`, and each re-implements its own parse loop with its own error
handling (`cli.py:193-200` vs `cli.py:228-237` vs `services.py:66-73` — three
copies).

The deviation is deliberate to the extent that `inventory` and `validate` need
no network client, but the correct expression of that is a factory parameter
(`offline=True` already exists), not a parallel construction path.

## Rules this profile implies

1. A new pipeline component belongs at L3, imports only `models`, and is wired
   in `factory.create`.
2. Nothing below L1 may import `factory` or `cli`.
3. `models` stays free of package imports and of behaviour beyond validation and
   `canonical_key`-style derivations.
4. Objects owning OS resources (`Cache`, `GitHubClient`) are created only in the
   composition root, so that root owns closing them.
5. New CLI commands route through `AuditServiceFactory`, not direct construction.
