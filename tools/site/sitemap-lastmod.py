#!/usr/bin/env python3
"""Keep the <lastmod> dates in docs/sitemap.xml equal to the last Git change of each page.

  python3 tools/site/sitemap-lastmod.py           update the dates in place
  python3 tools/site/sitemap-lastmod.py --check   exit 1 when a date is out of date

A page's date is the commit date of the last commit that changed its file in
docs/. Search engines use these dates to see which pages changed. The site
workflow runs --check for every pull request that touches docs/.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / 'docs'
SITE = 'https://lecomputeur.github.io/vibez/'
ENTRY = re.compile(r'(<loc>\s*([^<]+?)\s*</loc>\s*<lastmod>)([^<]*)(</lastmod>)')


def page_file(url):
    if not url.startswith(SITE):
        raise SystemExit('Sitemap URL outside the site: %s' % url)
    name = url[len(SITE):] or 'index.html'
    path = DOCS / name
    if not path.is_file():
        raise SystemExit('Sitemap URL has no page in docs/: %s' % url)
    return path


def last_change(path):
    date = subprocess.run(['git', 'log', '-1', '--format=%cs', '--', str(path.relative_to(ROOT))],
                          cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    if not date:
        raise SystemExit('No Git history for %s; commit the page first' % path.relative_to(ROOT))
    return date


def updated(text):
    changes = []

    def replace(match):
        url, old = match.group(2), match.group(3).strip()
        new = last_change(page_file(url))
        if new != old:
            changes.append((url, old, new))
        return match.group(1) + new + match.group(4)

    result, count = ENTRY.subn(replace, text)
    if not count:
        raise SystemExit('No <loc>/<lastmod> entries found in docs/sitemap.xml')
    return result, changes


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true', help='report only; exit 1 when a date is out of date')
    args = parser.parse_args(argv)
    sitemap = DOCS / 'sitemap.xml'
    text, changes = updated(sitemap.read_text())
    for url, old, new in changes:
        print('%s: %s -> %s' % (url, old or '(none)', new))
    if args.check:
        if changes:
            print('Sitemap dates are out of date; run: python3 tools/site/sitemap-lastmod.py')
            return 1
        print('Sitemap dates match the last change of every page.')
        return 0
    if changes:
        sitemap.write_text(text)
    print('Updated %d date(s) in docs/sitemap.xml' % len(changes))
    return 0


if __name__ == '__main__':
    sys.exit(main())
