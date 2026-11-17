---
name: code-review
title: Code and security review
title_tr: Kod ve güvenlik incelemesi
title_en: Code and security review
description: Reviews a project or its latest changes for bugs, security holes (OWASP), performance and maintainability, runs the tests and linters, and fixes what the user approves.
description_tr: Bir projeyi veya son değişikliklerini hata, güvenlik açığı (OWASP), performans ve bakım kolaylığı açısından inceler, testleri ve lint araçlarını çalıştırır, kullanıcının onayladıklarını düzeltir.
description_en: Reviews a project or its latest changes for bugs, security holes (OWASP), performance and maintainability, runs the tests and linters, and fixes what the user approves.
tools: run, read_file, list_dir, search_code, symbols, impact, edit_file, write_file, todo, make_doc
---
Review like a senior engineer: find real problems with evidence, not style opinions.

## 1. Scope
Git project: `git diff --stat` and `git diff` (or `git diff main...HEAD`) for the changes; otherwise the files
the user named or the whole project (list_dir, search_code for entry points).

## 2. Run the checks that exist (fast, in parallel when possible)
Tests (`pytest -q`, `npm test`, `php vendor/bin/phpunit`, `go test ./...`), linters / type checks (`ruff check`,
`npx eslint .`, `npx tsc --noEmit`, `phpstan`), dependency audits (`npm audit --omit=dev`, `pip-audit` if
installed, `composer audit`). Report their real output.

## 3. Read the code for
- Correctness: wrong conditions, off-by-one, unhandled None/null, race conditions, error paths that swallow errors,
  resources not closed.
- Security: SQL/command/template injection, XSS, path traversal, SSRF, missing auth checks, secrets in code or
  logs, weak crypto, unsafe deserialization, CORS and cookie settings, file upload validation.
- Performance: N+1 queries, work in loops, missing indexes, blocking calls in async code, large payloads.
- Maintainability only when it causes bugs (duplicated logic that diverged, dead code paths).

## 4. Report
A table sorted by severity (critical, high, medium, low): file:line, problem, concrete failure scenario, fix.
Then fix the approved ones (or all in full access when the user asked to fix), rerun the checks and show the result.
