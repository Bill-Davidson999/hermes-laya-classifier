# Third-party notices

The private `_vendor/laya_client` package contains unchanged Python source from
the standalone **laya-client v0.1.0** SDK, maintained in
[NandhaKishorM/laya](https://github.com/NandhaKishorM/laya) by Convai Innovations
and contributors. It is Apache-2.0 licensed. The full upstream license is retained
at `_vendor/laya_client/LICENSE`.

Source pin: `0565524a27bcb9821bcd7c42aaf49d925f6f8560`, directory `sdk/python`.
[UPSTREAM.json](UPSTREAM.json) records the source URL and SHA-256 digest of each
bundled SDK file. Only package placement changes: SDK source bytes are unchanged.
The wrapper uses relative imports; no global SDK installation is changed.
No separate upstream NOTICE file exists for this SDK at the pinned revision.

The upstream SDK declares Python >=3.10 and zero runtime dependencies. Its build
dependency, setuptools, is not needed by this vendored-source plugin. The Laya
inference package and model weights are not bundled or installed.

The local adapter, native plugin, skill, tests and documentation are distributed
under the root Apache-2.0 [LICENSE](LICENSE). Keep the license, NOTICE, upstream
license and provenance with redistributed copies.

**Hermes Agent**, developed by Nous Research and contributors, is a separate
MIT-licensed prerequisite. Its source is not copied into the release. Names and
links acknowledge the upstream projects; they do not imply endorsement.
