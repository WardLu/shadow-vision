## Problem and resulting behavior

<!-- User-observable before/after; scope and explicit non-goals. -->

## Risk

- Level: low / medium / high — auth, payment, permissions, shared data and release infrastructure are high
- Rollback: revert commit / redeploy previous SHA / data restore steps / N/A, with who runs it

## Verification

<!-- Behavior fixes and acceptance gaps follow the repository's test quality guide, if it has one. -->

- Identity: HEAD / source and test hashes / environment
- Checks: exact commands, actual assertions and artifact references
- Red check: assertion failure / not run / N/A, with target assertion and reason
- Break check: killed / survived / invalid, with target assertion and reason
- Actual surface: component / local HTTP / browser / integration / production
- Sibling sweep: directly related paths, findings and disposition
- Not run: reason / next / owner

## Delivery impact

- Database: N/A or migration/control-plane follow-up
- Production: N/A or necessary controlled follow-up
- Human decision: remaining product, visual or risk decision

<!-- A local diagnostic report is not a trusted release receipt. -->
