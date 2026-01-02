#!/usr/bin/env python3
"""
GitHub-based Automated Video Generator (Download Link Version)
- Reads Drive links from video.txt
- Downloads from Drive → Generates Video → Saves locally
- NO Drive upload - creates download links via GitHub Artifacts
"""

import os
import sys
import pickle
import subprocess
import re
from pathlib import Path
from datetime import datetime
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import io

class DriveVideoGenerator:
    def __init__(self, mode='1'):
        self.credentials = None
        self.service = None
        self.work_dir = Path('./work')
        self.output_dir = Path('./output')
        self.work_dir.mkdir(exist_ok=True)
        self.output_dir.mkdir(exist_ok=True)
        
        # Mode: '1' = video, '2' = with_template
        self.mode = 'video' if mode == '1' else 'with_template'
        
    def authenticate(self):
        """Load credentials from drive_token.pickle"""
        token_file = Path('drive_token.pickle')
        
        if not token_file.exists():
            print("❌ drive_token.pickle not found in repository!")
            print("Please add drive_token.pickle to your repository.")
            sys.exit(1)
        
        try:
            with open(token_file, 'rb') as token:
                self.credentials = pickle.load(token)
            
            self.service = build('drive', 'v3', credentials=self.credentials)
            print("✅ Drive authenticated successfully\n")
            
        except Exception as e:
            print(f"❌ Authentication failed: {e}")
            sys.exit(1)
    
    def extract_folder_id(self, drive_link):
        """Extract folder ID from Drive link"""
        patterns = [
            r'folders/([a-zA-Z0-9_-]+)',
            r'id=([a-zA-Z0-9_-]+)',
            r'^([a-zA-Z0-9_-]+)$'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, drive_link)
            if match:
                return match.group(1)
        
        return None
    
    def read_video_txt(self):
        """Read Drive links from video.txt"""
        video_txt = Path('video.txt')
        
        if not video_txt.exists():
            print("❌ video.txt not found!")
            return []
        
        folder_ids = []
        
        with open(video_txt, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                
                if not line or line.startswith('#'):
                    continue
                
                folder_id = self.extract_folder_id(line)
                
                if folder_id:
                    folder_ids.append(folder_id)
                    print(f"✅ Found project: {folder_id}")
                else:
                    print(f"⚠️  Invalid link: {line}")
        
        return folder_ids
    
    def list_folder_contents(self, folder_id):
        """List all files in a folder"""
        try:
            query = f"'{folder_id}' in parents and trashed=false"
            results = self.service.files().list(
                q=query,
                fields="files(id, name, mimeType)"
            ).execute()
            
            return results.get('files', [])
            
        except Exception as e:
            print(f"❌ Error listing folder {folder_id}: {e}")
            return []
    
    def download_file(self, file_id, file_name, destination):
        """Download a file from Drive"""
        try:
            request = self.service.files().get_media(fileId=file_id)
            
            dest_path = Path(destination) / file_name
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(dest_path, 'wb') as f:
                downloader = MediaIoBaseDownload(f, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                    if status:
                        progress = int(status.progress() * 100)
                        print(f"     {progress}% - {file_name}", end='\r')
            
            print(f"     ✅ Downloaded: {file_name}                    ")
            return dest_path
            
        except Exception as e:
            print(f"     ❌ Failed to download {file_name}: {e}")
            return None
    
    def download_folder_structure(self, folder_id, project_name):
        """Download entire folder structure recursively"""
        print(f"\n{'='*70}")
        print(f"📥 Downloading Project: {project_name}")
        print(f"{'='*70}\n")
        
        project_dir = self.work_dir / project_name
        project_dir.mkdir(exist_ok=True)
        
        structure = {
            '1st': None
        }
        
        # Get main folder contents
        files = self.list_folder_contents(folder_id)
        
        if not files:
            print("❌ Folder is empty or inaccessible!")
            return None
        
        for file in files:
            if file['mimeType'] == 'application/vnd.google-apps.folder':
                folder_name = file['name']
                folder_id = file['id']
                
                if folder_name == '1st':
                    print(f"\n📂 Processing: {folder_name}/")
                    folder_path = project_dir / folder_name
                    folder_path.mkdir(exist_ok=True)
                    
                    # Download folder contents recursively
                    self.download_folder_recursive(folder_id, folder_path)
                    
                    structure['1st'] = folder_path
        
        # Validate structure
        if not structure['1st']:
            print("\n❌ Invalid folder structure!")
            print("   Required: '1st' folder")
            return None
        
        print(f"\n{'='*70}")
        print("✅ Download Complete!")
        print(f"{'='*70}\n")
        
        return structure
    
    def download_folder_recursive(self, folder_id, destination):
        """Recursively download folder contents"""
        files = self.list_folder_contents(folder_id)
        
        for file in files:
            if file['mimeType'] == 'application/vnd.google-apps.folder':
                subfolder_name = file['name']
                subfolder_id = file['id']
                subfolder_path = destination / subfolder_name
                subfolder_path.mkdir(exist_ok=True)
                
                print(f"   📁 {subfolder_name}/")
                
                self.download_folder_recursive(subfolder_id, subfolder_path)
            else:
                self.download_file(file['id'], file['name'], destination)
    
    def get_video_duration(self, video_path):
        """Get video duration in seconds"""
        try:
            cmd = [
                'ffprobe', '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                str(video_path)
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            return float(result.stdout.strip())
        except:
            return 0
    
    def run_live_py(self, project_structure):
        """Run live.py to create final video"""
        first_dir = project_structure['1st']
        
        if not first_dir or not first_dir.exists():
            print("❌ '1st' folder not found!")
            return None
        
        print(f"\n{'='*70}")
        print(f"🎬 Running live.py (Mode: {self.mode})")
        print(f"{'='*70}\n")
        
        # Import live.py
        sys.path.insert(0, str(Path.cwd()))
        from live import NewsVideoCreator
        
        try:
            creator = NewsVideoCreator(str(first_dir), mode=self.mode)
            creator.create_final_video()
            
            # Find output
            output_video = first_dir / "output" / "final_video.mp4"
            
            if output_video.exists():
                print(f"\n✅ Video created successfully!")
                return output_video
            else:
                print("\n❌ Output video not found!")
                return None
                
        except Exception as e:
            print(f"\n❌ Error in live.py: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def save_to_output(self, video_path, project_name):
        """Save video to output folder with duration-based name"""
        print(f"\n{'='*70}")
        print("💾 Saving Output Video")
        print(f"{'='*70}\n")
        
        try:
            # Get video duration
            duration = self.get_video_duration(video_path)
            
            # Format: 5m30s
            minutes = int(duration // 60)
            seconds = int(duration % 60)
            time_name = f"{minutes}m{seconds}s"
            
            # Create output filename
            output_name = f"{project_name}_{time_name}.mp4"
            output_path = self.output_dir / output_name
            
            # Copy video
            subprocess.run(['cp', str(video_path), str(output_path)], check=True)
            
            file_size = output_path.stat().st_size / (1024*1024)
            
            print(f"   ✅ Saved: {output_name}")
            print(f"   📊 Size: {file_size:.1f} MB")
            print(f"   ⏱️  Duration: {time_name}")
            
            return output_path
            
        except Exception as e:
            print(f"\n   ❌ Save failed: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def process_project(self, project_folder_id, index=1, total=1):
        """Main processing pipeline for one project"""
        print("\n" + "="*70)
        print(f"🚀 PROJECT {index}/{total}")
        print("="*70)
        
        project_name = f"project_{index}_{datetime.now().strftime('%H%M%S')}"
        
        try:
            # Step 1: Download from Drive
            structure = self.download_folder_structure(project_folder_id, project_name)
            
            if not structure:
                print(f"\n❌ Project {index} failed: Invalid structure")
                return False
            
            # Step 2: Run live.py
            final_video = self.run_live_py(structure)
            
            if not final_video:
                print(f"\n❌ Project {index} failed: Could not create video")
                return False
            
            # Step 3: Save to output folder
            output_path = self.save_to_output(final_video, project_name)
            
            if not output_path:
                print(f"\n❌ Project {index} failed: Could not save video")
                return False
            
            print("\n" + "="*70)
            print(f"✅ PROJECT {index} COMPLETED SUCCESSFULLY!")
            print(f"📁 Output: {output_path.name}")
            print("="*70)
            
            return True
            
        except Exception as e:
            print(f"\n❌ Project {index} failed with error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def run(self):
        """Main entry point"""
        print("""
╔═══════════════════════════════════════════════════════════════════╗
║         GITHUB AUTOMATED VIDEO GENERATOR                          ║
║         Download Link Version - No Drive Upload                   ║
╚═══════════════════════════════════════════════════════════════════╝
        """)
        
        print(f"🎯 Mode Selected: {self.mode.upper()}\n")
        
        # Authenticate
        self.authenticate()
        
        # Read video.txt
        print("📄 Reading video.txt...")
        folder_ids = self.read_video_txt()
        
        if not folder_ids:
            print("\n❌ No valid folder IDs found in video.txt!")
            print("\nExample video.txt format:")
            print("https://drive.google.com/drive/folders/YOUR_FOLDER_ID")
            print("# or just the folder ID:")
            print("YOUR_FOLDER_ID")
            sys.exit(1)
        
        print(f"\n✅ Found {len(folder_ids)} project(s) to process")
        
        # Process each project
        results = []
        for i, folder_id in enumerate(folder_ids, 1):
            success = self.process_project(folder_id, i, len(folder_ids))
            results.append({
                'folder_id': folder_id,
                'success': success
            })
        
        # Summary
        print("\n" + "="*70)
        print("📊 FINAL SUMMARY")
        print("="*70)
        
        successful = sum(1 for r in results if r['success'])
        failed = len(results) - successful
        
        print(f"\n✅ Successful: {successful}/{len(results)}")
        print(f"❌ Failed: {failed}/{len(results)}")
        
        if successful > 0:
            print("\n📥 DOWNLOAD YOUR VIDEOS:")
            print("   1. Go to GitHub Actions page")
            print("   2. Find this workflow run")
            print("   3. Scroll to bottom")
            print("   4. Click 'Artifacts' section")
            print("   5. Download ZIP file")
            print("\n⏱️  Files available for 7 days")
        
        if failed > 0:
            print("\n⚠️  Failed projects:")
            for i, r in enumerate(results, 1):
                if not r['success']:
                    print(f"   {i}. {r['folder_id']}")
        
        print("\n" + "="*70)
        
        # Exit with error if any failed
        if failed > 0:
            sys.exit(1)


def main():
    # Get mode from command line argument
    mode = sys.argv[1] if len(sys.argv) > 1 else '1'
    
    if mode not in ['1', '2']:
        print("❌ Invalid mode! Use 1 or 2")
        sys.exit(1)
    
    generator = DriveVideoGenerator(mode)
    generator.run()


if __name__ == "__main__":
    main()
