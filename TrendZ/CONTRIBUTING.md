# Contributing to TrendZ

Thanks for your interest in TrendZ. The project is a research prototype, and contributions that make evidence more inspectable, reproducible and useful are especially welcome.

## Good first collaborations

- **Reproducibility:** propose a legally shareable, clearly synthetic fixture that exercises the public measured-mode pathway without impersonating the stored research evidence.
- **Evaluation:** design independently reviewed product/creator holdouts, with clear denominators and label instructions.
- **Ingestion:** improve source provenance, error handling, quotas, repeat-snapshot coverage and source license compliance.
- **UX and accessibility:** clarify uncertainty, keyboard support, contrast, mobile views and explainability.
- **Security:** review local-to-hosted boundaries, authentication, privacy and safe handling of external-source content.

## Working style

1. Start with an issue explaining the user problem, evidence boundary and proposed scope.
2. Prefer small, testable changes. Do not replace evidence-aware states with a single unvalidated score.
3. Record data provenance, missingness and the difference between observation, assisted review and user assumption.
4. Never commit `.env`, API keys, local SQLite, raw captured media, private review sessions, or restricted third-party data.
5. Add targeted tests and document exactly which tests ran and which could not run without the private research archive.
6. For analytical method changes, propose an evaluation plan *before* tuning on the fixed reviewed sets.

**Licensing:** this initial publication contains no open-source license. Please discuss code reuse rights and contribution licensing with the owner before redistribution or submitting substantive code. External source content retains its respective rights.
