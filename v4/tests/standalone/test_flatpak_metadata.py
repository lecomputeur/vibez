"""Check application-store metadata without installing or launching an app."""
import configparser
import gzip
import importlib.util
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('alpha_flatpak_metadata_builder',ROOT/'tools/alpha-flatpak.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)


class FlatpakMetadataTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix='vibez-alpha-appstream-')
        self.root=Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def catalogue(self,*,launchable=None,category='Development'):
        path=self.root/'share/app-info/xmls';path.mkdir(parents=True,exist_ok=True)
        source=ET.Element('components',version='0.16',origin=builder.APP)
        component=ET.SubElement(source,'component',type='desktop-application')
        for tag,value in [('id',builder.APP),('name',builder.LABEL)]:ET.SubElement(component,tag).text=value
        ET.SubElement(component,'launchable',type='desktop-id').text=launchable or builder.APP+'.desktop'
        ET.SubElement(ET.SubElement(component,'categories'),'category').text=category
        ET.SubElement(component,'icon',type='stock').text=builder.APP
        (path/'alpha.xml.gz').write_bytes(gzip.compress(ET.tostring(source)))

    def test_menu_entry_is_visible_and_uses_exec_instead_of_unsupported_dbus_activation(self):
        path=self.root/(builder.APP+'.desktop');path.write_text(builder.desktop_entry())
        config=configparser.ConfigParser(interpolation=None);config.read(path)
        entry=config['Desktop Entry']
        self.assertEqual(entry['Exec'],builder.BIN)
        self.assertEqual(entry['Categories'],'Development;')
        self.assertEqual(entry['Icon'],builder.APP)
        self.assertFalse(entry.getboolean('DBusActivatable'))
        for key in ['TryExec','Hidden','NoDisplay','OnlyShowIn','NotShowIn']:self.assertNotIn(key,entry)
    
    def test_desktop_entry_passes_the_platform_validator(self):
        validator=shutil.which('desktop-file-validate')
        if not validator:self.skipTest('desktop-file-validate is not installed on this platform')
        path=self.root/(builder.APP+'.desktop');path.write_text(builder.desktop_entry())
        subprocess.run([validator,str(path)],check=True,capture_output=True)

    @unittest.skipUnless(sys.platform.startswith('linux'),'Gio desktop visibility is Linux-specific')
    def test_menu_entry_is_visible_to_gio(self):
        try:
            import gi
            gi.require_version('Gio','2.0')
            from gi.repository import Gio
        except (ImportError,ValueError):self.skipTest('Gio introspection is not installed on this platform')
        if not hasattr(Gio,'DesktopAppInfo'):self.skipTest('Gio desktop application support is not installed')
        path=self.root/(builder.APP+'.desktop');path.write_text(builder.desktop_entry())
        desktop=Gio.DesktopAppInfo.new_from_filename(str(path))
        self.assertIsNotNone(desktop)
        self.assertTrue(desktop.should_show())
        self.assertIn('Development',desktop.get_categories())
        self.assertEqual(desktop.get_executable(),builder.BIN)

    def test_raw_metainfo_without_composed_catalogue_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError,'catalogue is missing'):builder.check_appstream_catalog(self.root)

    def test_composed_catalogue_requires_the_exact_launchable_and_category(self):
        self.catalogue()
        self.assertEqual(builder.check_appstream_catalog(self.root)['launchable'],builder.APP+'.desktop')
        self.catalogue(launchable='nl.lecomputeur.vibez3.desktop')
        with self.assertRaisesRegex(RuntimeError,'launchable'):builder.check_appstream_catalog(self.root)
        self.catalogue(category='Utility')
        with self.assertRaisesRegex(RuntimeError,'category'):builder.check_appstream_catalog(self.root)

    def test_real_composer_publishes_launchable_icon_and_development_category(self):
        composer=ROOT/'.cache/appstream-compose-tools/compose'
        if not composer.is_file():self.skipTest('Private AppStream compose tool has not been staged')
        for name in ['applications','metainfo','icons/hicolor/512x512/apps']:(self.root/'share'/name).mkdir(parents=True)
        (self.root/'share/applications'/f'{builder.APP}.desktop').write_text(builder.desktop_entry())
        (self.root/'share/metainfo'/f'{builder.APP}.metainfo.xml').write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n<component type="desktop-application">'
            f'<id>{builder.APP}</id><metadata_license>CC0-1.0</metadata_license><project_license>MIT</project_license>'
            f'<name>{builder.LABEL}</name><summary>Mistral client with local project workspaces</summary>'
            '<description><p>Use local text files from one chosen project folder.</p></description>'
            f'<launchable type="desktop-id">{builder.APP}.desktop</launchable>'
            '<url type="homepage">https://github.com/lecomputeur/vibez</url>'
            f'<releases><release version="{builder.VERSION}" date="2026-11-01"/></releases>'
            '<content_rating type="oars-1.1"/></component>')
        shutil.copyfile(ROOT/'icon.png',self.root/'share/icons/hicolor/512x512/apps'/f'{builder.APP}.png')
        proof=builder.compose_appstream(self.root,composer,self.root/'compose.log')
        self.assertEqual(proof['component_id'],builder.APP)
        self.assertEqual(proof['category'],'Development')
        self.assertTrue(any((self.root/'share/app-info/icons/flatpak').rglob('*.png')))


if __name__=='__main__':unittest.main()
