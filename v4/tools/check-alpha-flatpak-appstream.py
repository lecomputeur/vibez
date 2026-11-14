#!/usr/bin/python3
"""Read the exact AppStream data app stores receive from a Flatpak bundle."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

APP='nl.lecomputeur.vibez4.alpha'


def inspect_bundle(path,expected_version):
    import gi
    gi.require_version('Flatpak','1.0')
    from gi.repository import Flatpak,Gio
    ref=Flatpak.BundleRef.new(Gio.File.new_for_path(str(path)))
    report={'bundle':str(path),'bundle_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'passed':False,'installed':False,'launched':False,'host_flatpak_state_changed':False,
        'app_id':ref.get_name(),'branch':ref.get_branch(),'architecture':ref.get_arch()}
    appstream=ref.get_appstream()
    raw=appstream.get_data() if appstream else b''
    report['embedded_appstream_bytes']=len(raw)
    try:
        if report['app_id']!=APP or report['branch']!='alpha' or report['architecture']!='x86_64':
            raise ValueError('Bundle is not the independent x86_64 V4 Alpha application')
        if not raw:raise ValueError('Bundle has no embedded AppStream catalogue for app-store launch')
        source=gzip.decompress(raw) if raw.startswith(b'\x1f\x8b') else raw
        root=ET.fromstring(source)
        components=root.findall('component')
        owned=[component for component in components if component.findtext('id')==APP]
        if len(owned)!=1:raise ValueError('Embedded AppStream does not contain the exact Alpha component')
        component=owned[0]
        launchable=component.find('launchable[@type="desktop-id"]')
        if launchable is None or launchable.text!=APP+'.desktop':raise ValueError('App-store desktop launchable is missing or incorrect')
        categories=[category.text for category in component.findall('categories/category')]
        if 'Development' not in categories:raise ValueError('Development menu category is absent')
        if not component.findall('icon'):raise ValueError('App-store icon is absent')
        versions=[release.get('version') for release in component.findall('releases/release')]
        if expected_version not in versions:raise ValueError('AppStream release version differs from the intended package')
        report.update(passed=True,launchable=launchable.text,categories=categories,release_versions=versions,
                      application_name=component.findtext('name'),app_store_catalogue_complete=True)
    except (ValueError,ET.ParseError,OSError) as error:
        report['error']=str(error)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--expected-version',required=True)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    report=inspect_bundle(args.bundle.resolve(strict=True),args.expected_version)
    text=json.dumps(report,indent=2)+'\n'
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(text)
    print(text,end='')
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
