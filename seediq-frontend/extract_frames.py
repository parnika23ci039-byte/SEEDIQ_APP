import zipfile
import os
import shutil

zip_path = r"C:\Users\SUMITH R\Downloads\ezgif-7e43e4e59488b34f-jpg.zip"
out_dir = r"C:\Users\SUMITH R\Desktop\SeedIQ1\seediq-frontend\public\scroll-frames"

os.makedirs(out_dir, exist_ok=True)

with zipfile.ZipFile(zip_path, 'r') as z:
    z.extractall(out_dir)

# Rename files to a clean sequence (frame_1.jpg, frame_2.jpg, ...)
files = sorted([f for f in os.listdir(out_dir) if f.endswith('.jpg') or f.endswith('.jpeg') or f.endswith('.png')])

for i, f in enumerate(files):
    ext = os.path.splitext(f)[1]
    old_path = os.path.join(out_dir, f)
    new_path = os.path.join(out_dir, f"frame_{i + 1}.jpg")
    os.rename(old_path, new_path)

print(f"Extracted and renamed {len(files)} frames to {out_dir}")
