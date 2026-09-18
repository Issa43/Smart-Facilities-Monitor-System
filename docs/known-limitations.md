# Known Limitations

- AI/Computer Vision models, training, and inference are intentionally deferred
  to a dedicated specialist. `apps/ai_engine` is only an integration-ready
  foundation and must not be described as an implemented AI engine.
- Public production rollout is blocked on external hosting choices: domain,
  TLS certificate/termination, image registry, secret manager, offsite backup
  destination, alert receiver, and log/metrics collector.
- Docker Scout image CVE verification requires an authenticated Docker ID in
  this environment. Application dependency checks are clean, but the release
  gate must retain the container-scan requirement until an authenticated scan
  succeeds.
- `check --deploy` currently emits non-security drf-spectacular enum naming
  warnings. The generated schema is valid; names can be stabilized later with
  `ENUM_NAME_OVERRIDES` without changing runtime contracts.
- The tested backup mechanism is complete, but production RPO/RTO, legal
  retention, and offsite-provider policy require business-owner approval.
- CI/CD is not configured because repository hosting and deployment credentials
  were not supplied. All release commands currently run manually.

This file lists only confirmed current gaps. Remove entries only after the
corresponding evidence-based gate passes.
