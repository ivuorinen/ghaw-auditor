# Architecture Profile

Detected automatically from the module import graph (`ast`-parsed, not inferred
from naming) and from the call sites in each entry point. Regenerate by
re-running `/nitpicker arch-profile`.

## Detected pattern

**Layered pipeline with a dependency-injection composition root.**

A CLI shell delegates to a factory that wires concrete collaborators into a
service, which drives a fixed pipeline of single-responsibility components over
a shared set of pydantic data contracts.

```text
L0  cli.py                          Typer commands, console I/O, exit codes,
                                    report rendering and diff orchestration
L1  factory.py                      composition root (AuditServiceFactory)
L2  services.py                     AuditService / DiffService orchestration
L3  scanner parser resolver         pipeline components
    analyzer policy renderer differ
L4  github_client.py cache.py       infrastructure (HTTP, disk)
L5  models.py                       pydantic contracts (leaf)
```

`AuditService.scan` covers discovery through validation and **stops there** — it
calls only `scanner`, `parser`, `analyzer`, `resolver` and `validator`:

```text
scanner.find_workflows ─┐
                        ├─> parser.parse_workflow ─> analyzer.deduplicate_actions
scanner.find_actions ───┘                                    │
                                                             v
                                              resolver.resolve_actions (network)
                                                             │
                              analyzer.analyze_workflows <───┤
                              validator.validate        <────┘
                                        │
                                        v
                                   ScanResult
```

Rendering and diffing are **not** part of the service pipeline. `cli.scan`
constructs `Renderer` directly and calls `_handle_diff_mode`, which builds a
`DiffService` around `Differ`:

```text
ScanResult ──> cli.scan ──> Renderer.render_json / render_markdown
                       └──> _handle_diff_mode ──> DiffService ──> Differ
```

## Verified invariants

Measured across all 14 modules (`__init__`, `analyzer`, `cache`, `cli`,
`differ`, `factory`, `github_client`, `models`, `parser`, `policy`, `renderer`,
`resolver`, `scanner`, `services`):

| Invariant | Result |
| --- | --- |
| Dependencies flow strictly downward (no upward imports) | **holds** — 0 violations |
| No import cycles | **holds** — 0 cycles |
| `models` imports nothing from the package (leaf contract layer) | **holds** |
| `github_client` / `cache` import nothing from the package | **holds** |
| `scanner` imports nothing from the package | **holds** |
| Infrastructure is injected, never constructed by pipeline components | **holds** — only `factory` constructs `GitHubClient`/`Cache` |

Full measured graph — every one of the 14 modules:

| Module | Layer | Imports (in-package) |
| --- | --- | --- |
| `cli` | 0 | analyzer, differ, factory, models, parser, policy, renderer, scanner, services |
| `factory` | 1 | analyzer, cache, github_client, models, parser, policy, resolver, scanner, services |
| `services` | 2 | analyzer, differ, models, parser, policy, resolver, scanner |
| `resolver` | 3 | cache, github_client, models, parser |
| `analyzer` | 3 | models |
| `differ` | 3 | models |
| `parser` | 3 | models |
| `policy` | 3 | models |
| `renderer` | 3 | models |
| `scanner` | 3 | — |
| `github_client` | 4 | — |
| `cache` | 4 | — |
| `models` | 5 | — |
| `__init__` | — | — (version string only) |

## Known deviation

`cli.inventory` and `cli.validate` bypass L1 and L2, constructing pipeline
components directly instead of going through `AuditServiceFactory`:

| Entry point | Constructs directly | Routes through factory |
| --- | --- | --- |
| `cli.scan` | `Renderer` | **yes** — `AuditServiceFactory.create` |
| `cli.inventory` | `Scanner`, `Parser`, `Analyzer` | no |
| `cli.validate` | `Scanner`, `Parser`, `PolicyValidator` | no |

This duplicates the factory's wiring (`factory.py`) and is the structural reason
those two commands diverge from `scan`: neither can receive `exclude_patterns`,
and the parse-and-collect loop exists in three copies (`cli.inventory`,
`cli.validate`, `AuditService.scan`).

The deviation is deliberate to the extent that neither command needs a network
client, but the correct expression of that is a factory parameter (`offline=True`
already exists), not a parallel construction path.

## Rules this profile implies

1. A new pipeline component belongs at L3, imports only `models`, and is wired
   in `factory.create`.
2. Nothing below L1 may import `factory` or `cli`.
3. `models` stays free of package imports and of behaviour beyond validation and
   `canonical_key`-style derivations.
4. Objects owning OS resources (`Cache`, `GitHubClient`) are created only in the
   composition root, so that root owns closing them.
5. New CLI commands route through `AuditServiceFactory`, not direct construction.
6. Output concerns (`Renderer`, `Differ`) stay outside `AuditService.scan`; the
   service returns a `ScanResult` and the caller decides how to present it.
