#!/usr/bin/python3
"""Compare the MCP protocol versions VibeZ speaks with the published specification.

Mistral started sending the 2026-07-28 protocol version on 10 November 2026
while VibeZ knew 2025-06-18 as its newest; the specification had been public
for three months. This check makes that visible early:

  python3 tools/check-mcp-versions.py            # report, exit 1 when a newer published version exists
  python3 tools/check-mcp-versions.py --json     # machine-readable report
  python3 tools/check-mcp-versions.py --offline  # only the recorded state, no network

Sources, in order: the specification repository's version folders on GitHub,
then the public versioning page. Drafts are listed but never count as
published. The result is recorded in management/mcp-versions.json so a release
carries the date of its last check.
"""
import argparse
import importlib.util
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
RECORD = BASE / 'management/mcp-versions.json'
LISTING = 'https://api.github.com/repos/modelcontextprotocol/modelcontextprotocol/contents/docs/specification'
PAGE = 'https://modelcontextprotocol.io/specification/versioning'
DATE = re.compile(r'^20\d{2}-[01]\d-[0-3]\d$')


def known_versions():
    spec = importlib.util.spec_from_file_location('vibez_web_connector_versions', BASE / 'backend/web_connector.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return list(getattr(module, 'ALL_VERSIONS', module.VERSIONS))


def fetch(url, timeout=20):
    request = urllib.request.Request(url, headers={'User-Agent': 'VibeZ-mcp-version-check', 'Accept': 'application/vnd.github+json, text/html'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode('utf-8', 'replace')


def published_versions(fetcher=fetch):
    """Dated specification versions, newest first, and where they came from."""
    try:
        entries = json.loads(fetcher(LISTING))
        names = [e.get('name', '') for e in entries if isinstance(e, dict) and e.get('type') == 'dir']
        versions = sorted((n for n in names if DATE.match(n)), reverse=True)
        if versions:
            return versions, 'repository'
    except (OSError, ValueError):
        pass
    text = fetcher(PAGE)
    versions = sorted(set(re.findall(r'20\d{2}-[01]\d-[0-3]\d', text)), reverse=True)
    # The page also carries today's date and blog dates; keep only versions that
    # the page names as specification versions (they appear in links).
    linked = sorted({v for v in versions if re.search(r'specification/' + re.escape(v), text)}, reverse=True)
    return (linked or versions), 'page'


def compare(known, published):
    newest_known = max(known) if known else None
    newer = [v for v in published if newest_known is None or v > newest_known]
    unknown_older = [v for v in published if v not in known and newest_known is not None and v < newest_known]
    return {'known': sorted(known, reverse=True), 'published': published, 'newest_known': newest_known,
            'newest_published': published[0] if published else None,
            'newer_than_known': newer, 'unknown_older': unknown_older, 'up_to_date': not newer}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--offline', action='store_true', help='report the recorded state only')
    parser.add_argument('--record', type=Path, default=RECORD)
    args = parser.parse_args(argv)
    known = known_versions()
    if args.offline:
        try:
            recorded = json.loads(args.record.read_text())
        except (OSError, ValueError):
            recorded = {}
        report = compare(known, recorded.get('published', []))
        report['checked_at'] = recorded.get('checked_at'); report['source'] = recorded.get('source', 'record')
    else:
        try:
            published, source = published_versions()
        except (OSError, ValueError) as error:
            print('Could not read the specification versions: %s' % error)
            return 2
        report = compare(known, published)
        report['checked_at'] = time.strftime('%Y-%m-%dT%H:%M:%S%z'); report['source'] = source
        args.record.write_text(json.dumps({'known': report['known'], 'published': published, 'checked_at': report['checked_at'],
                                           'source': source}, indent=2) + '\n')
    if args.json:
        print(json.dumps(report, indent=1))
    else:
        print('VibeZ speaks: %s' % ', '.join(report['known']))
        print('Published:    %s (%s, checked %s)' % (', '.join(report['published']) or 'unknown', report['source'], report['checked_at']))
        if report['newer_than_known']:
            print('NEWER THAN VIBEZ: %s. Mistral may send these; the header is tolerated, full support is work.' % ', '.join(report['newer_than_known']))
        elif report['unknown_older']:
            print('Older versions VibeZ does not list: %s (harmless while clients negotiate down).' % ', '.join(report['unknown_older']))
        else:
            print('Up to date with the published specification.')
    return 0 if report['up_to_date'] else 1


if __name__ == '__main__':
    sys.exit(main())
