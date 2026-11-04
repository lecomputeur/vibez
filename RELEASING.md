# VibeZ release process

This is the maintainer's checklist. To report a problem or help test, start at [Contributing](CONTRIBUTING.md).

A local candidate, an installed test build and a public release are different states. A version is downloadable only after its release and packages are public. Do not mark an issue as released because a fix exists only locally.

## One version, one source snapshot

- Keep V3 stable and V4 Alpha separate: app identity, profile, packages and update channels. V4 packages must not replace VibeZ 3.0.9. MSIX is outside the V4 Alpha package set.
- Keep V4 source in private version control. The public `desktop/` source is V3; a public release tag does not make its existing source archive the V4 implementation.
- Use the private V4 working tree's `management/release.json` as the source of version, source revision, required targets, package names, changes and related issues. Its `management/manage.py` commands `check`, `status`, `plan` and `snapshot` validate and prepare that record. Generate build requests and publication text from it rather than editing independent copies. These management files belong to the private checkout, not the public V3 tree.
- Freeze the approved source before building. Save the source revision and a file-hash manifest with the private release record. Validate that delivered resources match that snapshot.
- A published version keeps the same package bytes. A subsequent code fix gets a new version. Local experiments need a private build reference; they are not a reason to announce another public release.

The existing encrypted V4 build route stays in place until a replacement is implemented and verified. Do not upload plaintext V4 source or private signing keys to this repository. Introducing a release manifest does not by itself make the existing native build or publication steps automatic.

## Before publication

1. **Plan.** Link related issues and pull requests to a milestone for the intended version. Use the [workflow labels](CONTRIBUTING.md#following-progress) to show whether work is being investigated, implemented or tested. Record who reported each problem.
2. **Prepare.** Read the candidate version from the release manifest. Synchronise generated version fields, then check them. Freeze the exact source and prepare a draft release. An Alpha is a prerelease, not the stable `latest` release.
3. **Build.** Build every package declared as required in the manifest from that source. Keep validation records for Linux, Windows, Intel Mac and Apple Silicon as applicable. Never silently substitute an older package for a missing target. If a platform must be delayed, obtain an explicit decision and state the limitation in the release description.
4. **Verify.** Run the appropriate unit, interface, backend and native runtime checks. Test installation and update paths, V3/V4 separation and unchanged profiles. Validate checksums and update signatures; verify Mac signing, notarization and stapled tickets. Record skipped tests and live-account or platform limits accurately.
5. **Review.** Confirm the final download list, readable release notes, acknowledgements and known limitations. Review the draft with the maintainer and obtain approval before publishing. A passing automated test is not approval to publish.

## Publish and communicate

1. Publish the approved, complete release with the correct tag and frozen source reference. V4 Alpha remains a prerelease; keep VibeZ 3.0.9 as the stable release while it is the approved stable version.
2. Verify the public downloads at their normal URLs. Advance each signed update channel only after the referenced packages are available and validated. No target may point to a different version's bytes. Keep a channel at its previous working version when its required target is unavailable.
3. Update the website, README, platform download pages and the current Alpha testing invitation from the same release information. Clearly distinguish installers from technical update files.
4. Keep the existing [Alpha testing conversation](https://github.com/lecomputeur/vibez/discussions/56) as the V4 announcement and testing thread. Update its opening information and add one grouped update for the public release: download link, main changes, known limits and what needs testing. Do not start a parallel V4 thread for every version or repeatedly tag testers and stargazers for local builds or minor edits.
5. Reply in each original issue when its fix is publicly available. Name the exact release and ask the reporter to confirm on their system. Keep discussion in that thread; do not create a second report for the same problem. Credit substantive testing, suggestions and code in the release notes.
6. Use `status:ready-to-test` for a released change awaiting confirmation and `status:verified` once the result is confirmed, then close the issue when appropriate. If verification is still only local or limited to some systems, state that explicitly. An issue may remain open across releases.

## Release notes and contributors

The [release-note categories](.github/release.yml) group labelled public pull requests when GitHub's **Generate release notes** option is used. Review the result: generated notes cannot infer unpublished private V4 fixes or the results of a tester's checks. Add those verified changes, links and acknowledgements yourself. Do not claim that someone wrote code when their contribution was testing or feedback.

## Preserve update delivery

Numbered installer releases and the technical update channel have different roles. Technical channel metadata must be replaceable as signed updates advance. Do not enable a repository-wide immutable-release rule without a separate, verified migration for that mutable channel. Do not remove update archives or metadata simply to tidy the installer list.

If a published release has a problem, record it in its notes and prepare the next version. Do not overwrite the old installers or conceal a repair under an existing version number.
