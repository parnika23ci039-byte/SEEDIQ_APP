import zipfile
import os
import shutil

zip_path = r"C:\Users\SUMITH R\Downloads\frames_4k_upscaled.zip"
extract_path = r"c:\Users\SUMITH R\Desktop\SeedIQ1\seediq-frontend\public\scroll-frames"

if os.path.exists(extract_path):
    shutil.rmtree(extract_path)
os.makedirs(extract_path, exist_ok=True)

with zipfile.ZipFile(zip_path, 'r') as zip_ref:
    zip_ref.extractall(extract_path)

print("Extraction complete. Listing files in extract_path:")
for root, dirs, files in os.walk(extract_path):
    for f in files:
        print(os.path.join(root, f))
