#!/usr/bin/env python3
"""Install the optional CPU locator without replacing live OpenCV/NumPy files.
Prepare dependencies/model/drop-ins; the normal hash-checked deploy restarts the
services only after pending jobs finish. Run as root on the owned backend host.
"""
import argparse,hashlib,json,os,re,subprocess,time,urllib.request
from pathlib import Path

SHA='64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff'
URL='https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task'

def run(*args):return subprocess.run(args,check=True,capture_output=True,text=True).stdout.strip()

def main():
 p=argparse.ArgumentParser();p.add_argument('--dependencies',type=Path,default=Path('/opt/gensticker-fusion-20261027'));p.add_argument('--model',type=Path,default=Path('/var/lib/gensticker/features/models/face_landmarker-v1.task'));a=p.parse_args()
 if os.geteuid()!=0:raise SystemExit('run on the backend host as root')
 for path in [a.dependencies,a.model]:
  if not path.is_absolute() or not re.fullmatch(r'/[A-Za-z0-9_./-]+',str(path)):raise SystemExit('use simple absolute install paths')
 if not (a.dependencies/'bin/python').is_file():run('python3','-m','venv',str(a.dependencies))
 run(str(a.dependencies/'bin/pip'),'install','-r',str(Path(__file__).with_name('requirements-fusion.txt')))
 run(str(a.dependencies/'bin/pip'),'check')
 if not a.model.is_file() or hashlib.sha256(a.model.read_bytes()).hexdigest()!=SHA:
  with urllib.request.urlopen(URL,timeout=45) as response:raw=response.read(5_000_001)
  if len(raw)>5_000_000 or hashlib.sha256(raw).hexdigest()!=SHA:raise SystemExit('public model checksum mismatch')
  a.model.parent.mkdir(parents=True,exist_ok=True);tmp=a.model.with_suffix('.part');tmp.write_bytes(raw);tmp.chmod(0o644);tmp.replace(a.model)
 site=run(str(a.dependencies/'bin/python'),'-c','import sysconfig;print(sysconfig.get_paths()["purelib"])')
 release=Path('/opt/gensticker-current').resolve()
 # Probe using each actual caller's Python. Its already-loaded OpenCV, Pillow
 # and NumPy win; optional packages are searched only after its own site-packages.
 code='import site;import cv2,numpy;from PIL import Image;site.addsitedir('+repr(site)+');from mediapipe.tasks import python;from mediapipe.tasks.python import vision;m=vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(base_options=python.BaseOptions(model_asset_path='+repr(str(a.model))+',delegate=python.BaseOptions.Delegate.CPU),num_faces=1));m.close();print("cpu locator ready")'
 for runtime in ['api-venv','worker-venv']:run(str(release/runtime/'bin/python'),'-c',code)
 backup=Path('/var/backups')/('gensticker-cpu-fusion-'+str(int(time.time())));backup.mkdir(mode=0o700)
 for name in ['gensticker','gensticker-worker']:
  directory=Path('/etc/systemd/system')/(name+'.service.d');directory.mkdir(exist_ok=True)
  target=directory/'10-cpu-fusion.conf'
  if target.exists():(backup/(name+'.conf')).write_bytes(target.read_bytes())
  target.write_text('[Service]\nEnvironment="GENSTICKER_FUSION_SITE='+site+'"\nEnvironment="GENSTICKER_FACE_LANDMARK_MODEL='+str(a.model)+'"\n')
 run('systemctl','daemon-reload')
 print(json.dumps({'status':'prepared','model_sha256':SHA,'model_bytes':a.model.stat().st_size,'dependencies':str(a.dependencies),'backup':str(backup),'restarted':False}))

if __name__=='__main__':main()
