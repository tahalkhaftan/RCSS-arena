import io
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path
from app import extract


def archive(entries):
    blob=io.BytesIO()
    with zipfile.ZipFile(blob,'w') as z:
        for name,data,mode,system in entries:
            info=zipfile.ZipInfo(name)
            info.create_system=system
            info.external_attr=mode<<16
            z.writestr(info,data)
    return blob.getvalue()


class ZipTeams(unittest.TestCase):
    def test_linux_library_symlink_chain(self):
        blob=archive([
            ('Team/lib/libfoo.so','libfoo.so.1',stat.S_IFLNK|0o777,3),
            ('Team/lib/libfoo.so.1','libfoo.so.1.2',stat.S_IFLNK|0o777,3),
            ('Team/lib/libfoo.so.1.2',b'\x7fELFtest',stat.S_IFREG|0o755,3),
            ('Team/bin/start','../scripts/start',stat.S_IFLNK|0o777,3),
            ('Team/scripts/start','#!/bin/sh\nexit 0',stat.S_IFREG|0o755,3),
        ])
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            extract(blob,root)
            self.assertTrue((root/'Team/lib/libfoo.so').is_symlink())
            self.assertEqual((root/'Team/lib/libfoo.so').read_bytes(),b'\x7fELFtest')
            self.assertTrue((root/'Team/bin/start').stat().st_mode&stat.S_IXUSR)

    def test_dos_metadata_is_not_unix_file_type(self):
        blob=archive([('Team/config','test',stat.S_IFIFO|0o644,0)])
        with tempfile.TemporaryDirectory() as d:
            extract(blob,Path(d))
            self.assertEqual((Path(d)/'Team/config').read_text(),'test')

    def test_reject_unsafe_or_unresolvable_links(self):
        cases=[
            [('a','/etc/passwd',stat.S_IFLNK,3)],
            [('a','../outside',stat.S_IFLNK,3)],
            [('a','missing',stat.S_IFLNK,3)],
            [('a','b',stat.S_IFLNK,3),('b','a',stat.S_IFLNK,3)],
            [('a','folder',stat.S_IFLNK,3),('a/file','bad',stat.S_IFREG,3)],
            [('pipe','',stat.S_IFIFO,3)],
            [('file','one',stat.S_IFREG,3),('file','two',stat.S_IFREG,3)],
        ]
        for entries in cases:
            with self.subTest(entries=entries),tempfile.TemporaryDirectory() as d:
                with self.assertRaises(ValueError): extract(archive(entries),Path(d))

    def test_later_link_cannot_redirect_parent_traversal_outside_root(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'team'
            (Path(d)/'target').write_text('outside')
            blob=archive([
                ('target','inside',stat.S_IFREG,3),
                ('a','b/../target',stat.S_IFLNK,3),
                ('b','.',stat.S_IFLNK,3),
            ])
            with self.assertRaises(ValueError): extract(blob,root)


if __name__=='__main__': unittest.main()
