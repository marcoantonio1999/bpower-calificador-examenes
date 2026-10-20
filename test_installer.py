from pathlib import Path
import tempfile
import unittest
import installer
from grader import VERSION


class InstallerTest(unittest.TestCase):
    def test_separate_install_and_preserve_data(self):
        self.assertEqual(installer.VERSION,VERSION)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);payload=root/'payload';payload.write_bytes(b'MZsynthetic')
            target=root/'BPower-Calificador-Examenes';target.mkdir()
            original=target/'user-note.txt';original.write_text('preserve')
            exe=installer.install(target,payload)
            self.assertEqual(exe.read_bytes(),b'MZsynthetic')
            self.assertEqual(original.read_text(),'preserve')
            self.assertEqual(exe.name,f'BPower-Calificador-{VERSION}.exe')


if __name__=='__main__':unittest.main()
