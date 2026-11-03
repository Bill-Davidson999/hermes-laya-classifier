# Laya Classifier for Hermes Agent

**v0.1.0-beta** — A native Hermes tool and bundled skill for fast, bounded,
advisory classification through a separately hosted Laya service.

Laya is a probabilistic decision model, not a conversational LLM or an independent
proof of correctness. This third-party integration sends concise text and named
categories to Laya and returns structured probabilities. It does not change
Hermes orchestration, invoke itself automatically, or authorize actions.

## Features and requirements

- One native tool: `laya_classify`; one bundled skill: `laya-classifier:decisions`.
- Custom categories with descriptions, a selected category, complete probabilities,
  separate confidence fields, token usage and adapter-measured elapsed time.
- Private external JSON credentials and a configurable HTTP(S) service origin.
- Structured errors, no retries, no hosted fallback and no credential logging.
- No pip installation, local model download, inference libraries or extra server.

Requires Hermes Agent **v0.22.5 or a compatible later native-plugin API**, Python
**3.10+**, and a reachable Laya service with bearer authentication and the
`POST /v1/systemone` Choice protocol. The pinned standalone `laya-client` SDK
v0.1.0 is included under `_vendor`; it has no runtime dependencies. The plugin
declares no additional Python dependencies. See [UPSTREAM.json](UPSTREAM.json).

Release checks ran on Windows with Python 3.14.9 and 3.15.2. The real Hermes
loader, settings reader, tool registry and bundled-skill discovery were tested
in an isolated home. Other operating systems and later Hermes releases are not
certified. Maintainer-reported prior integration tests include Gemma, DeepSeek
and OpenAI-backed Hermes sessions; this is not a guarantee for every model.

## Install

1. Extract the release ZIP. Copy its **whole `laya-classifier` folder** to
   `<active Hermes home>/plugins/laya-classifier`. Keep `_vendor` and `skills`.
   `plugin.yaml` and `__init__.py` must be directly inside that directory. Do not
   copy a private credential file into it. Review an existing installation before
   replacing files.
2. Use the home for the intended profile. Defaults are `%LOCALAPPDATA%\hermes`
   on Windows and `~/.hermes` on Linux/macOS. Custom homes and named profiles can
   differ. For a named profile, use the supported `hermes -p NAME ...` commands.
3. Create the private configuration described below, then validate and enable
   from the functioning Hermes command environment:

   ```text
   hermes plugins doctor <absolute-plugin-directory> --ci
   hermes plugins enable laya-classifier --no-allow-tool-override
   hermes plugins list --plain
   ```

   Replace the placeholder with your plugin directory, quoted if needed.
   These are Hermes's native commands. No built-in tool override is needed.
4. Start a **new Hermes session** after activation. Compatible live backends can
   rediscover enabled plugins without a service restart; native tools stay
   deferred to the next session so existing prompts remain stable. If your
   backend does not reload plugins, follow its normal controlled restart process.

The loader calls `register(ctx)`. That registers the tool in toolset `laya` and
the read-only skill through `ctx.register_skill`; **no separate skill installation
is needed**. Load the skill with `skill_view(name="laya-classifier:decisions")`.
Hermes may expose native tools through deferred discovery; use the normal tool
search/description flow if `laya_classify` is not immediately listed.

## Configure

Copy [laya.example.json](laya.example.json) to a private location outside the
repository and plugin directory. A **fictitious Windows example** is
`C:\AI-Credentials\laya.json`; a Unix example is `/secure/laya.json`. Neither is
a hardcoded default. The private filename can be different.

```json
{
  "schema_version": 1,
  "provider": "laya",
  "api_key": "REPLACE_WITH_YOUR_BEARER_TOKEN",
  "base_url": "https://laya.example.invalid:8000",
  "endpoint": "/v1/systemone",
  "auth_type": "bearer",
  "method": "POST"
}
```

Set your real service origin and key **only in the private copy**. The example
domain is reserved and does not run a service. `base_url` is the origin, without
a route, user information, query or fragment; `endpoint` must be `/v1/systemone`.
HTTP and HTTPS are accepted. Prefer HTTPS across untrusted networks; plain HTTP
does not encrypt state or the bearer token.

Required fields are `api_key`, `base_url`, `endpoint`, `auth_type` and `method`.
`schema_version` and `provider` preserve the existing credential-file format;
they are optional metadata and do not select a provider or wire protocol.
The key must be nonempty printable ASCII without whitespace. JSON files can use
a UTF-8 BOM and must be at most 16 KiB. Do not place secrets in tool arguments.

Merge this into the **active profile's** `config.yaml`, keeping other settings:

```yaml
plugins:
  entries:
    laya-classifier:
      settings:
        credentials_file: 'C:\AI-Credentials\laya.json'
```

Replace the example with your own absolute file path. Only the path is stored in
Hermes settings. There is no implicit credential path, secret environment variable
or key-copy step. Code reads the external file for each invocation. Existing JSON
credential files with the fields above can be reused in place.

## Use

Ask Hermes to load `laya-classifier:decisions` and call `laya_classify` once with:

```json
{
  "state": "A technology company has released a new artificial intelligence processor designed to accelerate AI training and inference in data centers.",
  "question_name": "category",
  "question": "Choose the primary news category for this summary.",
  "categories": {
    "Technology": "Computing, artificial intelligence, processors, and technology products",
    "Business": "Corporate finances, markets, acquisitions, and general business activity",
    "Politics": "Government, elections, public policy, and political affairs",
    "Sports": "Athletic competitions, teams, players, and sporting events"
  }
}
```

These are exact tool arguments, not an OpenAI chat request. The tool converts the
question into `questions.category = {type: "choice", instructions, criteria}` and
leaves checkpoint selection to the service.

On success, `ok:true` accompanies `category`, the complete `probabilities` mapping,
`confidence`, `answer_confidence`, `model`, `usage`, `question_name`,
`advisory_only:true` and `latency_ms`. Optional `x_jev_confidence` retains its name.
On failure, `ok:false` accompanies an `error` object; no category or probability
distribution is invented. HTTP errors include `status_code`, not provider bodies.

For scope drift, include the assigned task and the **complete short response** in
`state`. Ask how closely it follows the task and define categories such as
`On task`, `Minor drift`, `Major drift` and `Uncertain`. Do not treat an excerpt
as the full response. Other uses include task routing and research categorization.

## Interpret the result

- `probabilities` names exactly the supplied labels. Values are preserved rather
  than renormalized; independent rounding can make the sum slightly different
  from one. Labels and their order are preserved.
- For upstream Choice answers, `confidence` measures distribution concentration
  (`1 - H(p)/log(k)`). It is **not** a probability that the classification is correct.
- `answer_confidence` is upstream's answer-confidence field, normally the maximum
  class probability. Missing optional values return null, never an invented value.
- Neither field is assumed calibrated. Upstream describes fitting and validating
  calibration on held-out data for the actual checkpoint and option count.
- `latency_ms` is **elapsed time measured by the adapter**, including configuration
  reading, transport and parsing. It is not a service-reported inference timer or
  end-to-end Hermes/model latency. There is no performance guarantee.

Use ambiguous distributions as a reason to inspect the evidence. A top-ranked
label does not establish relevance, factual accuracy, technical correctness or
completion. Normal tests, readbacks and permission boundaries still apply.

## Limits and troubleshooting

| Adapter limit | Value |
|---|---:|
| Questions per call | 1 Choice question |
| State | 2,000 characters |
| Question instruction | 300 characters |
| Categories | 2–16 |
| Category label / description | 64 / 160 characters |
| Encoded request | 8,192 bytes |

`question_name` must match `[A-Za-z][A-Za-z0-9_]{0,63}`. Overlength tool inputs
are **rejected, not truncated**. These transport guards do not guarantee that
text fits the service's model-token window. Keep summaries and categories short.
The service may truncate text or option descriptions within its own model budget;
this adapter does not override that budget or certify a model's capacity.

- **Tool missing:** check the active profile, enabled plugin, Doctor output and
  toolset availability, then start a new session after supported plugin activation.
- **`configuration_error`:** check the absolute `credentials_file` setting and
  external JSON schema. Do not paste the file into a chat or issue.
- **HTTP 401 / connection error:** check your service/token and network. Do not
  report headers or credential values.
- **`proxy_configured`:** the plugin refuses an applicable HTTP(S)/all-proxy
  configuration before sending a bearer. Direct access is required; `NO_PROXY`
  does not override this conservative check. The plugin does not change proxies.
- **`invalid_response`:** the service returned malformed JSON, mismatched labels,
  invalid probabilities or another incompatible result. No synthetic fallback is used.
- **Slow or timed-out call:** cold loading, queueing or transport can affect time.
  The SDK's 30-second timeout is per blocking I/O operation, not a total deadline;
  server processing may continue after the client stops waiting. There are no retries.

Inputs/results may appear in Hermes's normal tool transcript even though this
plugin writes no request logs. Never classify credentials. The SDK refuses
redirects and reads successful responses without a byte cap; use a trusted Laya
deployment. This beta supports Choice only and does not establish classification
accuracy or production reliability.

## Verification and development

From the extracted directory, run the focused offline checks with Python 3.10+:

```text
python verify.py
```

If the default temporary directory is restricted, add `--scratch-dir` with an
existing writable directory. No real credential or network is used by these tests.
From an existing Hermes Python environment, `python verify_hermes.py` also checks
the real loader, bundled skill and configured tool call in a disposable home with
a synthetic loopback HTTP fixture. It does not connect to a running gateway.

An explicit live check makes exactly one request through the tool handler:

```text
python verify.py --live --credentials "C:\AI-Credentials\laya.json"
```

The path is an example; use your private file. Do not enable tracing or print it.
See [release notes](RELEASE_NOTES.md) for the validation boundary.

## License and acknowledgments

The integration code is licensed under [Apache License 2.0](LICENSE). The
unchanged bundled SDK has the same license and retains its own license file,
source pin and hashes. See [NOTICE](NOTICE) and [third-party notices](THIRD_PARTY_NOTICES.md).
Hermes itself is not bundled.

Thank you to **Nous Research and the Hermes Agent developers and contributors**
for [Hermes Agent](https://github.com/NousResearch/hermes-agent), its native tools
and skill interfaces. Hermes is MIT-licensed.

Thank you to **Convai Innovations, repository maintainer NandhaKishorM, and the
Laya developers and contributors** for [Laya](https://github.com/NandhaKishorM/laya)
and the Apache-2.0 standalone HTTP SDK. The source metadata names Convai Innovations
as the author. See the pinned [HTTP contract](https://github.com/NandhaKishorM/laya/blob/0565524a27bcb9821bcd7c42aaf49d925f6f8560/docs/http-api.md)
and [confidence documentation](https://github.com/NandhaKishorM/laya/blob/0565524a27bcb9821bcd7c42aaf49d925f6f8560/docs/questions-and-answers.md).

This is an independent third-party integration. It is not an official Hermes or
Laya release, and no endorsement by either upstream project is implied.

## Acknowledgments

### Development acknowledgments

This integration was conceived and developed as part of the FrankenCenter AI development laboratory.

**OpenAI Codex** served as the primary software engineering agent, responsible for implementation, testing, integration, and release preparation.

**OpenAI ChatGPT** contributed requirements development, architectural discussions, experimental design, documentation, and release review.

The project was directed and maintained by Bill Davidson.

Special thanks to the Laya and Hermes Agent developers and contributors whose work made this integration possible.

OpenAI, Nous Research, and the Laya developers do not officially sponsor, endorse,
or maintain this independent project.
