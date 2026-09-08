import importlib.util,json,tempfile,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('versions',Path(__file__).with_name('versions.py'));v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
class Copies(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();v.ROOT=Path(self.temp.name);v.CATALOG=v.ROOT/'versions/catalog.json'
  self.source=v.ROOT/'versions/2026-09-08-campus';(self.source/'public/data').mkdir(parents=True)
  (self.source/'public/data/entity.json').write_text('{"building":"HKUST"}')
  (self.source/'VERSION.json').write_text(json.dumps({'id':self.source.name,'kind':'project-checkpoint'}))
  v.CATALOG.write_text(json.dumps({'latest':self.source.name,'versions':[{'id':self.source.name}]}))
 def tearDown(self):self.temp.cleanup()
 def test_independent_copy_and_preserved_parent(self):
  original=v.inventory(self.source);v.fork(self.source,'2026-10-01-campus');child=v.selected()
  self.assertNotEqual((child/'public/data/entity.json').stat().st_ino,(self.source/'public/data/entity.json').stat().st_ino)
  (child/'public/data/entity.json').write_text('changed')
  self.assertEqual(v.inventory(self.source),original)
  with self.assertRaises(ValueError):v.fork(self.source,'2026-10-01-campus')
 def test_invalid_copy_does_not_change_latest(self):
  (self.source/'linked').symlink_to('/tmp');before=v.CATALOG.read_text()
  with self.assertRaises(ValueError):v.fork(self.source,'2026-11-01-campus')
  self.assertEqual(v.CATALOG.read_text(),before)
if __name__=='__main__':unittest.main()
