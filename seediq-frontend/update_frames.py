import zipfile
import os
import shutil
import re

zip_path = r"C:\Users\SUMITH R\Downloads\frames_4k_upscaled.zip"
target_dir = r"c:\Users\SUMITH R\Desktop\SeedIQ1\seediq-frontend\public\scroll-frames"
index_tsx_path = r"c:\Users\SUMITH R\Desktop\SeedIQ1\seediq-frontend\src\routes\index.tsx"

# 1. Clear existing frames
if os.path.exists(target_dir):
    shutil.rmtree(target_dir)
os.makedirs(target_dir, exist_ok=True)

# 2. Extract ZIP
print(f"Extracting {zip_path}...")
with zipfile.ZipFile(zip_path, 'r') as zip_ref:
    zip_ref.extractall(target_dir)

# 3. Clean up folder structure if it extracted into a subfolder
extracted_items = os.listdir(target_dir)
if len(extracted_items) == 1:
    subfolder = os.path.join(target_dir, extracted_items[0])
    if os.path.isdir(subfolder):
        print(f"Moving files from subfolder {extracted_items[0]}...")
        for item in os.listdir(subfolder):
            shutil.move(os.path.join(subfolder, item), target_dir)
        os.rmdir(subfolder)

# 4. Count frames (assuming they are named frame_1.jpg, frame_2.jpg, etc.)
frames = [f for f in os.listdir(target_dir) if f.startswith('frame_') and f.endswith('.jpg')]
num_frames = len(frames)
print(f"Found {num_frames} frames.")

if num_frames > 0:
    # 5. Update index.tsx
    print(f"Updating {index_tsx_path} with {num_frames} frames...")
    with open(index_tsx_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Regex to find: for (let i = 1; i <= 200; i++) {
    new_content = re.sub(r'for \((let i = 1; i <= )\d+(; i\+\+)\)', rf'for (\g<1>{num_frames}\g<2>)', content)
    
    with open(index_tsx_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print("Done! Frames replaced and React component updated.")
else:
    print("Warning: No files matching 'frame_X.jpg' found in the extracted folder.")
