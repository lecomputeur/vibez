#!/usr/bin/python3
"""Point the public download texts at the current V4 Alpha.

The public repository (lecomputeur/vibez) carries the download buttons and a
short highlights paragraph in README.md and docs/ (index, Linux, macOS,
Windows). Those five files fell three versions behind once; this tool rewrites
them from `management/release.json`:

  python3 tools/refresh-alpha-downloads.py --site <clone of lecomputeur/vibez>

* every `4.0.0-alpha.N` and `Alpha N` of the previous Alpha becomes the new one;
* the highlights paragraph ("Alpha N is available for Linux, Windows, Intel and
  Apple Silicon Macs. ...") is replaced by `download_highlights` from
  release.json, or by --highlights / --highlights-file;
* with --check-links every release link in the five files must answer.

VibeZ 3.0.9 and its links are never touched: only the Alpha version strings and
the one Alpha paragraph change. Nothing is committed or pushed here.
"""
import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
FILES = ('README.md', 'docs/index.html', 'docs/linux.html', 'docs/macos.html', 'docs/windows.html')
LEAD = '%s is available for Linux, Windows, Intel and Apple Silicon Macs. '
VERSION_RE = re.compile(r'^4\.0\.0-(alpha|beta)\.(\d+)$')
README_PARAGRAPH = re.compile(r'^> (?:Alpha|Beta) (\d+) is available for Linux, Windows, Intel and Apple Silicon Macs\. .*$', re.M)
HTML_PARAGRAPH = re.compile(r'<p class="alpha-feedback">(?:Alpha|Beta) (\d+) is available for Linux, Windows, Intel and Apple Silicon Macs\. .*?</p>')


def release_key(version):
    """Order of V4 versions: every Alpha before every Beta. A bare number means Alpha N."""
    if isinstance(version, int):
        return (0, version)
    match = VERSION_RE.match(version or '')
    if not match:
        raise ValueError('Not a V4 Alpha or Beta version: %r' % (version,))
    return (('alpha', 'beta').index(match.group(1)), int(match.group(2)))


def alpha_number(version):
    return release_key(version)[1]


def as_version(value):
    return '4.0.0-alpha.%d' % value if isinstance(value, int) else value


def label(version):
    stage, number = release_key(version)
    return '%s %d' % (('Alpha', 'Beta')[stage], number)


def clean_highlights(text):
    text = ' '.join((text or '').split())
    if not 40 <= len(text) <= 1200:
        raise ValueError('Highlights must be one paragraph of 40 to 1200 characters')
    if '<' in text or '>' in text or '\\' in text:
        raise ValueError('Highlights must be plain text without markup')
    if not text.endswith('.'):
        text += '.'
    return text


def current_alpha(text):
    """The V4 version the file points at now, from its download buttons."""
    versions = set(re.findall(r'4\.0\.0-(?:alpha|beta)\.\d+', text))
    if len(versions) != 1:
        raise ValueError('The file points at %s V4 versions; expected exactly one' % (len(versions) or 'no'))
    return versions.pop()


def refresh_text(name, text, new_version, highlights):
    new_version = as_version(new_version)
    old_version = current_alpha(text)
    if release_key(old_version) > release_key(new_version):
        raise ValueError('%s already points at %s, newer than %s' % (name, label(old_version), label(new_version)))
    paragraph = LEAD % label(new_version) + highlights
    pattern = README_PARAGRAPH if name.endswith('.md') else HTML_PARAGRAPH
    if len(pattern.findall(text)) != 1:
        raise ValueError('%s does not contain exactly one Alpha highlights paragraph' % name)
    text = pattern.sub(('> ' + paragraph) if name.endswith('.md') else ('<p class="alpha-feedback">' + paragraph + '</p>'), text, count=1)
    text = text.replace(old_version, new_version)
    text = re.sub(r'\b%s\b' % label(old_version), label(new_version), text)
    return text


def release_links(text):
    return sorted(set(re.findall(r'https://github\.com/lecomputeur/vibez/releases/[^\s"\')<>]+', text)))


def link_answers(url, timeout=20):
    request = urllib.request.Request(url, method='HEAD', headers={'User-Agent': 'VibeZ-release-check'})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return 200 <= response.status < 400
    except urllib.error.HTTPError as error:
        return 200 <= error.code < 400
    except (urllib.error.URLError, OSError, ValueError):
        return False


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--site', type=Path, required=True, help='clone of the public lecomputeur/vibez repository')
    parser.add_argument('--release', type=Path, default=BASE / 'management/release.json')
    parser.add_argument('--version', help='Alpha version to point at (default: release.json version)')
    parser.add_argument('--highlights', help='highlights paragraph (default: download_highlights in release.json)')
    parser.add_argument('--highlights-file', type=Path)
    parser.add_argument('--check-links', action='store_true', help='require every release link to answer')
    parser.add_argument('--dry-run', action='store_true', help='report, change nothing')
    args = parser.parse_args(argv)
    spec = json.loads(args.release.read_text())
    version = args.version or spec['version']
    number = version
    release_key(version)
    highlights = args.highlights_file.read_text() if args.highlights_file else (args.highlights or spec.get('download_highlights'))
    if not highlights:
        parser.error('No highlights: add "download_highlights" to release.json or pass --highlights')
    highlights = clean_highlights(highlights)
    changed = []
    for name in FILES:
        path = args.site / name
        if not path.is_file():
            parser.error('Missing in --site: ' + name)
        before = path.read_text()
        after = refresh_text(name, before, number, highlights)
        if after != before:
            changed.append(name)
            if not args.dry_run:
                path.write_text(after)
        if args.check_links:
            dead = [url for url in release_links(after) if not link_answers(url)]
            if dead:
                print('Dead links in %s:\n  %s' % (name, '\n  '.join(dead)))
                return 2
    print(json.dumps({'version': version, 'changed': changed, 'dry_run': args.dry_run,
                      'links_checked': args.check_links}, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
