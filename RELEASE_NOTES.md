# v0.1.0-beta

First portable public beta of Laya Classifier for Hermes Agent.

- Preserves the `laya_classify` Choice interface, probability validation,
  separate confidence fields, structured errors and bundled `decisions` skill.
- Replaces machine-specific settings with the native plugin setting
  `credentials_file` and a configurable HTTP(S) origin in the existing JSON format.
- Includes a sanitized JSON example, installation guidance and input/error limits.
- Bundles the unchanged standalone laya-client v0.1.0 SDK at upstream commit
  `0565524a27bcb9821bcd7c42aaf49d925f6f8560`; no runtime dependency installation.
- Retains upstream Apache-2.0 licensing and adds integration licensing and attribution.

## Validation boundary

All 17 focused offline tests passed, covering request/response parsing, portable configuration,
credential-safe errors and registration callbacks. The real Hermes Plugin Doctor,
tool registry and bundled-skill lookup were exercised in an isolated Windows
environment with a synthetic HTTP service. The installed service was not modified.
The package includes the scripts needed to repeat those checks.

One explicit live call through the release handler returned the expected Technology
classification and complete distribution in 281.4 ms of adapter-measured elapsed
time. This single observation is not a latency guarantee or an accuracy benchmark.

Prior maintainer tests exercised Hermes v0.22.5 with Gemma, DeepSeek and
OpenAI-backed sessions. They do not certify all providers, operating systems or
later Hermes versions. No automated tool-selection test or accuracy benchmark is
part of this release audit.

## Upgrade and limits

Set `plugins.entries.laya-classifier.settings.credentials_file` in the active
profile. There is no longer a built-in credential path or service address.
Existing external JSON files can stay in place. Nothing migrates or copies keys.

One Choice question per call; 2–16 described categories; state capped at 2,000
characters. Overlength tool inputs are rejected. Service-side token truncation,
calibration, total deadlines, proxies and untrusted service response size remain
limitations described in the README. Results are advisory.

This package is prepared for review. Publication is a separate maintainer action.
