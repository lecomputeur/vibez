# Help improve VibeZ

Testing, clear bug reports, wording suggestions and code all help. You do not need to be a programmer.

**Start here:** [Contributor guide](https://lecomputeur.github.io/vibez/contribute.html) · [Current test discussion](https://github.com/lecomputeur/vibez/discussions/56) · [Release progress](https://github.com/lecomputeur/vibez/milestones)

| I want to… | Go here |
|---|---|
| Report something broken | [Open a bug report](https://github.com/lecomputeur/vibez/issues/new/choose) |
| Suggest a feature or discuss a change | [Ideas](https://github.com/lecomputeur/vibez/discussions/categories/ideas) |
| Ask how something works | [Questions and answers](https://github.com/lecomputeur/vibez/discussions/categories/q-a) |
| Help test V4 Beta | [The V4 testing discussion](https://github.com/lecomputeur/vibez/discussions/56) |
| Improve a translation | [Start a wording discussion](https://github.com/lecomputeur/vibez/discussions/new?category=ideas) with the language, current wording and your suggestion |
| Contribute code or documentation | Read [Code and documentation](#code-and-documentation), then [open a pull request](https://github.com/lecomputeur/vibez/compare) |

English makes reports easier to share, but your own language is welcome. Please search existing Issues and Discussions first. Add follow-up results to the original report; use one issue for each separate bug.

## Test a release

Use an installer linked from the [published releases](https://github.com/lecomputeur/vibez/releases), and record its full version. V4 Beta installs separately from VibeZ 3 and never changes it. Start with copies of files in a temporary folder.

Useful checks include choosing or creating a folder, connecting it to a project or conversation, switching between them, reading a file, approving or refusing an edit, and downloading a generated file. Include whether you were using Work or Code. A result on one system does not establish that every other system works.

For a short test result, copy this:

```text
VibeZ version:
OS and version / Linux distribution:
Package and processor: (DEB / RPM / Flatpak / AppImage / Arch / EXE / MSI / DMG; x64 / ARM64)
Mode: (Work / Code)
What I tested:
Expected result:
Actual result:
Steps or screenshot:
```

Share a successful test in the [V4 testing discussion](https://github.com/lecomputeur/vibez/discussions/56). For a reproducible failure, [open a bug report](https://github.com/lecomputeur/vibez/issues/new/choose) and link it from the discussion if needed. Remove access tokens, passwords and private file contents from screenshots or logs.

## Following progress

[Milestones](https://github.com/lecomputeur/vibez/milestones) show which issues are planned for a version. Status labels explain the next step:

- `status:triage` — the report needs investigation or more information.
- `status:in-progress` — work is underway.
- `status:ready-to-test` — a candidate fix needs testing; the issue states which published version contains it.
- `status:verified` — the relevant checks or a tester confirmed the result; the issue records the scope.

A proposed fix is not automatically a released fix. Please confirm again using the published version named in the issue. If the problem remains, reply there with the version and result. The maintainer will link the release and any remaining limitations before closing the report.

## Code and documentation

**Check the version before changing code.** This repository holds two apps side by side:

| Folder | App |
|---|---|
| [`v4/`](v4/) | VibeZ V4 (beta): Rust/Tauri app with a Python file connector. Build and test steps are in [`v4/README.md`](v4/README.md). |
| [`desktop/`](desktop/) | VibeZ 3, the stable app. |

- **How a contribution works:** fork this repository, create a focused branch and open a pull request against `main`. Link the related issue and describe what changed and how you checked it. For a larger change, discuss it in an issue first. The **V4 tests** workflow runs the Node, Python and Rust tests for every pull request that touches `v4/`; it needs no secrets. The maintainer reviews, merges and later ships the change in a signed release.
- **V4 rules:** a new V4 source file must be added to `v4/management/source-files.json` and to the allowlist in `v4/.gitignore`. User-facing technical messages are in English and translated through the existing catalogs. Never commit keys, tokens, account data or personal project IDs; the live self-test reads its test projects from an untracked local file.
- **V3 and V4 are separate:** a patch to `desktop/` (V3) is not a V4 patch, and the other way round.
- **Wording or translations:** you can suggest the existing text and replacement in a discussion; no coding tools are needed. Say whether the text is in VibeZ or on Mistral's website, because Mistral controls its own translations.

For VibeZ 3 desktop changes, install the native Tauri prerequisites for your OS, then run:

```sh
cd desktop
npm ci --ignore-scripts
npm test
npm run build -- -- --locked
```

Keep unrelated changes out of a pull request. Include the operating system and checks you actually ran, plus anything you could not test. Do not include signing keys, credentials, personal projects or generated installers. The maintainer reviews contributions and decides when to merge or release them.

## Updates and thanks

One release announcement gathers the changes, download links and testing priorities. Subscribe to the [V4 testing discussion](https://github.com/lecomputeur/vibez/discussions/56) for V4 release updates. Older general announcements remain in the [Announcements archive](https://github.com/lecomputeur/vibez/discussions/categories/announcements). Your original issue remains the place for its detailed follow-up; no need to repeat it across threads.

Maintainers can follow the [release guide](RELEASING.md). See [Community contributions](CONTRIBUTORS.md) for acknowledgements. Testing and useful reports count alongside code. If an acknowledgement needs correcting, leave a message in [General](https://github.com/lecomputeur/vibez/discussions/categories/general).
