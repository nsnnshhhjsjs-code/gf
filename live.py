import os
import subprocess
from pathlib import Path
import re
import random
from PIL import Image

class NewsVideoCreator:
    def __init__(self, base_folder, mode='video'):
        self.base_folder = Path(base_folder)
        self.mode = mode  # 'video' or 'with_template'
        self.transition_video = self.base_folder / "transaction.mp4"
        self.record_video = self.base_folder / "record.mp4"
        self.template_image = self.base_folder / "template.png"
        self.anchor_video = self.base_folder / "anchor.mp4"
        self.output_folder = self.base_folder / "output"
        self.temp_folder = self.base_folder / "temp"
        
        self.output_folder.mkdir(exist_ok=True)
        self.temp_folder.mkdir(exist_ok=True)
        
        self.audio_formats = ['.mp3', '.wav', '.m4a', '.aac', '.ogg', '.flac']
        self.image_formats = ['.jpg', '.jpeg', '.png', '.bmp', '.webp', '.tiff']
        
        # Video settings
        self.width = 1920
        self.height = 1080
        self.fps = 30
        
        # Will be set by detect_template_regions()
        self.main_x = None
        self.main_y = None
        self.main_w = None
        self.main_h = None
        self.anchor_x = None
        self.anchor_y = None
        self.anchor_w = None
        self.anchor_h = None
    
    def detect_template_regions(self):
        """Auto-detect main screen and anchor positions from template.png"""
        if not self.template_image.exists():
            print("❌ template.png not found!")
            return False
        
        print("\n🔍 Analyzing template.png...")
        
        img = Image.open(self.template_image).convert('RGB')
        pixels = img.load()
        width, height = img.size
        
        # Find green regions
        green_regions = []
        visited = set()
        
        def is_green(pixel):
            r, g, b = pixel
            return g > 200 and r < 100 and b < 100
        
        def flood_fill(x, y):
            stack = [(x, y)]
            region = []
            while stack:
                cx, cy = stack.pop()
                if (cx, cy) in visited or cx < 0 or cy < 0 or cx >= width or cy >= height:
                    continue
                if not is_green(pixels[cx, cy]):
                    continue
                visited.add((cx, cy))
                region.append((cx, cy))
                stack.extend([(cx+1, cy), (cx-1, cy), (cx, cy+1), (cx, cy-1)])
            return region
        
        # Find all green regions
        for y in range(0, height, 5):
            for x in range(0, width, 5):
                if (x, y) not in visited and is_green(pixels[x, y]):
                    region = flood_fill(x, y)
                    if len(region) > 100:
                        green_regions.append(region)
        
        if len(green_regions) < 2:
            print(f"❌ Found {len(green_regions)} green regions, need 2 (main + anchor)")
            return False
        
        # Calculate bounding boxes
        boxes = []
        for region in green_regions:
            xs = [p[0] for p in region]
            ys = [p[1] for p in region]
            x1, x2 = min(xs), max(xs)
            y1, y2 = min(ys), max(ys)
            w = x2 - x1
            h = y2 - y1
            area = w * h
            boxes.append({'x': x1, 'y': y1, 'w': w, 'h': h, 'area': area})
        
        # Sort by area (largest first)
        boxes.sort(key=lambda b: b['area'], reverse=True)
        
        # Main screen (largest)
        self.main_x = boxes[0]['x']
        self.main_y = boxes[0]['y']
        self.main_w = boxes[0]['w']
        self.main_h = boxes[0]['h']
        
        # Anchor (second largest)
        self.anchor_x = boxes[1]['x']
        self.anchor_y = boxes[1]['y']
        self.anchor_w = boxes[1]['w']
        self.anchor_h = boxes[1]['h']
        
        print(f"✅ Template analyzed:")
        print(f"   Main Screen: {self.main_w}x{self.main_h} at ({self.main_x}, {self.main_y})")
        print(f"   Anchor: {self.anchor_w}x{self.anchor_h} at ({self.anchor_x}, {self.anchor_y})")
        
        return True
    
    def get_sorted_items(self, items):
        """Sort items numerically"""
        def extract_number(item):
            match = re.search(r'(\d+)', item.name)
            return int(match.group(1)) if match else 0
        return sorted(items, key=extract_number)
    
    def get_audio_duration(self, audio_path):
        """Get audio duration in seconds"""
        cmd = [
            'ffprobe', '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            str(audio_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return float(result.stdout.strip())
    
    def get_video_duration(self, video_path):
        """Get video duration in seconds"""
        return self.get_audio_duration(video_path)
    
    def get_video_info(self, video_path):
        """Get video resolution"""
        cmd = [
            'ffprobe', '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height',
            '-of', 'csv=p=0',
            str(video_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        width, height = map(int, result.stdout.strip().split(','))
        return width, height
    
    def get_audio_files(self):
        """Get all audio files from base folder"""
        audio_files = []
        for ext in self.audio_formats:
            audio_files.extend(self.base_folder.glob(f'*{ext}'))
        return self.get_sorted_items(audio_files)
    
    def get_image_folders(self):
        """Get all image folders sorted numerically"""
        folders = [f for f in self.base_folder.iterdir() 
                  if f.is_dir() and f.name not in ['output', 'temp']]
        return self.get_sorted_items(folders)
    
    def get_images_from_folder(self, folder):
        """Get all images from a folder"""
        images = []
        for ext in self.image_formats:
            images.extend(folder.glob(f'*{ext}'))
        return self.get_sorted_items(images)
    
    def create_image_effect_filter(self, duration, target_w=1920, target_h=1080):
        """Create ultra-subtle consistent zoom effect for all images"""
        
        # Always use slow zoom in - consistent for all images
        # Ultra minimal: 1.0 to 1.025 (only 2.5% zoom)
        # Speed: 0.00012 (very very slow)
        zoom_filter = f"scale={int(target_w*1.025)}:{int(target_h*1.025)},zoompan=z='min(zoom+0.00012,1.025)':d={int(duration*30)}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={target_w}x{target_h}"
        
        # Ultra minimal vibration - 2px range only
        vibration = f"crop=iw-4:ih-4:2+2*sin(n/20):2+2*sin(n/17)"
        
        return f"{zoom_filter},{vibration},scale={target_w}:{target_h},setsar=1"
    
    def normalize_transition(self):
        """Normalize transition to match segment specs - simple re-encode"""
        if not self.transition_video.exists():
            print("⚠️  No transaction.mp4 found - skipping transitions")
            return None
        
        normalized_transition = self.temp_folder / "normalized_transition.mp4"
        
        print("🔧 Preparing transition...")
        
        # Simple re-encode to match segments exactly
        cmd = [
            'ffmpeg', '-y',
            '-i', str(self.transition_video),
            '-vf', 'scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black,fps=30',
            '-c:v', 'libx264',
            '-preset', 'fast',
            '-crf', '18',
            '-pix_fmt', 'yuv420p',
            '-c:a', 'aac',
            '-b:a', '192k',
            '-ar', '48000',
            str(normalized_transition)
        ]
        
        subprocess.run(cmd, check=True, stderr=subprocess.DEVNULL)
        print("✅ Transition ready")
        
        return normalized_transition
    
    def create_segment_video_simple(self, audio_path, images, output_path):
        """Create simple video segment (MODE: video) - original functionality"""
        if not images:
            print(f"⚠️  No images found for {audio_path.name}")
            return False
        
        audio_duration = self.get_audio_duration(audio_path)
        duration_per_image = audio_duration / len(images)
        
        # Create individual image videos with effects
        temp_videos = []
        for i, img in enumerate(images):
            temp_vid = self.temp_folder / f"img_{audio_path.stem}_{i}.mp4"
            
            # Apply effects for full screen
            effect_filter = self.create_image_effect_filter(duration_per_image, 1920, 1080)
            
            cmd = [
                'ffmpeg', '-y',
                '-loop', '1',
                '-i', str(img),
                '-vf', effect_filter,
                '-t', str(duration_per_image),
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-crf', '18',
                '-pix_fmt', 'yuv420p',
                '-r', '30',
                str(temp_vid)
            ]
            
            subprocess.run(cmd, check=True, stderr=subprocess.DEVNULL)
            temp_videos.append(temp_vid)
        
        # Concat all image videos
        concat_file = self.temp_folder / f"concat_{audio_path.stem}.txt"
        with open(concat_file, 'w') as f:
            for vid in temp_videos:
                f.write(f"file '{vid.absolute()}'\n")
        
        temp_video = self.temp_folder / f"temp_video_{audio_path.stem}.mp4"
        
        cmd = [
            'ffmpeg', '-y',
            '-f', 'concat',
            '-safe', '0',
            '-i', str(concat_file),
            '-c:v', 'libx264',
            '-preset', 'fast',
            '-crf', '18',
            '-pix_fmt', 'yuv420p',
            str(temp_video)
        ]
        
        subprocess.run(cmd, check=True, stderr=subprocess.DEVNULL)
        
        # Add audio
        cmd = [
            'ffmpeg', '-y',
            '-i', str(temp_video),
            '-i', str(audio_path),
            '-c:v', 'copy',
            '-c:a', 'aac',
            '-b:a', '192k',
            '-ar', '48000',
            '-shortest',
            str(output_path)
        ]
        
        subprocess.run(cmd, check=True, stderr=subprocess.DEVNULL)
        
        # Cleanup
        concat_file.unlink()
        temp_video.unlink()
        for vid in temp_videos:
            vid.unlink()
        
        return True
    
    def create_segment_video_template(self, audio_path, images, output_path):
        """Create templated video segment (MODE: with_template)"""
        if not images:
            print(f"⚠️  No images found for {audio_path.name}")
            return False
        
        audio_duration = self.get_audio_duration(audio_path)
        
        # Step 1: Create slideshow for main screen
        print(f"     → Creating slideshow for main screen...")
        slideshow = self.create_slideshow_for_main(images, audio_duration)
        
        # Step 2: Loop anchor video
        print(f"     → Processing anchor...")
        anchor_loop = self.loop_anchor(audio_duration)
        
        # Step 3: Composite with template
        print(f"     → Compositing with template...")
        template_video = self.composite_template_part(slideshow, anchor_loop, audio_duration)
        
        # Step 4: Add audio
        print(f"     → Adding audio...")
        cmd = [
            'ffmpeg', '-y',
            '-i', str(template_video),
            '-i', str(audio_path),
            '-c:v', 'copy',
            '-c:a', 'aac',
            '-b:a', '192k',
            '-ar', '48000',
            '-shortest',
            str(output_path)
        ]
        
        subprocess.run(cmd, check=True, stderr=subprocess.DEVNULL)
        
        # Cleanup
        slideshow.unlink()
        anchor_loop.unlink()
        template_video.unlink()
        
        return True
    
    def create_slideshow_for_main(self, images, duration):
        """Create slideshow for main screen area with effects"""
        output = self.temp_folder / f"slideshow_{id(images)}.mp4"
        
        img_duration = duration / len(images)
        
        # Create individual image clips with effects
        clips = []
        for i, img in enumerate(images):
            clip_path = self.temp_folder / f"clip_{id(images)}_{i:03d}.mp4"
            
            # Apply effects for main screen size
            effect_filter = self.create_image_effect_filter(img_duration, self.main_w, self.main_h)
            
            cmd = [
                'ffmpeg', '-y',
                '-loop', '1',
                '-i', str(img),
                '-vf', effect_filter,
                '-t', str(img_duration),
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-crf', '18',
                '-pix_fmt', 'yuv420p',
                '-r', str(self.fps),
                str(clip_path)
            ]
            
            subprocess.run(cmd, check=True, stderr=subprocess.DEVNULL)
            clips.append(clip_path)
        
        # Concatenate clips
        if len(clips) == 1:
            subprocess.run(['ffmpeg', '-y', '-i', str(clips[0]), '-c', 'copy', str(output)], 
                         check=True, stderr=subprocess.DEVNULL)
        else:
            concat_file = self.temp_folder / f"clips_concat_{id(images)}.txt"
            with open(concat_file, 'w') as f:
                for clip in clips:
                    f.write(f"file '{Path(clip).absolute()}'\n")
            
            cmd = [
                'ffmpeg', '-y',
                '-f', 'concat',
                '-safe', '0',
                '-i', str(concat_file),
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-crf', '18',
                '-pix_fmt', 'yuv420p',
                str(output)
            ]
            
            subprocess.run(cmd, check=True, stderr=subprocess.DEVNULL)
            concat_file.unlink()
        
        # Cleanup individual clips
        for clip in clips:
            clip.unlink()
        
        return output
    
    def loop_anchor(self, duration):
        """Loop and crop anchor video"""
        output = self.temp_folder / f"anchor_loop_{id(self)}.mp4"
        
        cmd = [
            'ffmpeg', '-y',
            '-stream_loop', '-1',
            '-i', str(self.anchor_video),
            '-vf', f'scale={self.anchor_w}:{self.anchor_h}:force_original_aspect_ratio=increase,'
                   f'crop={self.anchor_w}:{self.anchor_h},'
                   f'fps={self.fps}',
            '-t', str(duration),
            '-c:v', 'libx264',
            '-preset', 'fast',
            '-crf', '18',
            '-pix_fmt', 'yuv420p',
            '-an',
            str(output)
        ]
        
        subprocess.run(cmd, check=True, stderr=subprocess.DEVNULL)
        return output
    
    def composite_template_part(self, slideshow, anchor, duration):
        """Composite slideshow with template and anchor"""
        output = self.temp_folder / f"template_part_{id(self)}.mp4"
        
        filter_complex = (
            f"color=black:s={self.width}x{self.height}:d={duration},fps={self.fps}[base];"
            f"[base][0:v]overlay={self.main_x}:{self.main_y}[with_main];"
            f"[with_main][1:v]overlay={self.anchor_x}:{self.anchor_y}[with_anchor];"
            f"[2:v]chromakey=0x00ff00:0.1:0.0[template_keyed];"
            f"[with_anchor][template_keyed]overlay=0:0[final]"
        )
        
        cmd = [
            'ffmpeg', '-y',
            '-i', str(slideshow),
            '-i', str(anchor),
            '-stream_loop', '-1',
            '-i', str(self.template_image),
            '-filter_complex', filter_complex,
            '-map', '[final]',
            '-t', str(duration),
            '-c:v', 'libx264',
            '-preset', 'fast',
            '-crf', '18',
            '-pix_fmt', 'yuv420p',
            str(output)
        ]
        
        subprocess.run(cmd, check=True, stderr=subprocess.DEVNULL)
        return output
    
    def prepare_looping_record(self, total_duration):
        """Prepare record.mp4 to loop for total duration with green screen removed"""
        if not self.record_video.exists():
            return None
        
        print(f"\n🎬 Processing record.mp4 (Green Screen Removal + Looping)...")
        
        # Get current resolution
        width, height = self.get_video_info(self.record_video)
        aspect_ratio = width / height
        target_aspect = 16 / 9
        
        print(f"   Current size: {width}x{height}")
        
        # Determine if resize needed
        if abs(aspect_ratio - target_aspect) < 0.01:
            print("   Already 16:9")
            scale_filter = 'scale=1920:1080'
        else:
            print("   Converting to 16:9")
            scale_filter = 'scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black'
        
        # Get record duration
        record_duration = self.get_video_duration(self.record_video)
        loop_times = int(total_duration / record_duration) + 2
        
        print(f"   Looping {loop_times} times for {total_duration:.1f}s duration")
        
        processed_record = self.temp_folder / "processed_record.mov"
        
        # Remove ONLY pure green screen with strict settings
        cmd = [
            'ffmpeg', '-y',
            '-stream_loop', str(loop_times),
            '-i', str(self.record_video),
            '-vf', f'{scale_filter},chromakey=0x00FF00:0.15:0.05',
            '-t', str(total_duration),
            '-c:v', 'png',
            '-r', '30',
            '-pix_fmt', 'rgba',
            '-an',
            str(processed_record)
        ]
        
        subprocess.run(cmd, check=True, stderr=subprocess.DEVNULL)
        print("✅ Record.mp4 processed (only pure green removed)")
        
        return processed_record
    
    def create_final_video(self):
        """Create final video with all segments and transitions"""
        print("🎬 Starting News Video Creation...")
        print("=" * 60)
        print(f"Mode: {self.mode.upper()}")
        print("=" * 60)
        
        # Check mode requirements
        if self.mode == 'with_template':
            if not self.template_image.exists():
                print("❌ template.png required for with_template mode!")
                return
            if not self.anchor_video.exists():
                print("❌ anchor.mp4 required for with_template mode!")
                return
            
            # Detect template regions
            if not self.detect_template_regions():
                return
        
        audio_files = self.get_audio_files()
        image_folders = self.get_image_folders()
        
        if not audio_files:
            print("❌ Error: No audio files found!")
            return
        
        if len(audio_files) != len(image_folders):
            print(f"⚠️  Warning: Audio ({len(audio_files)}) and folders ({len(image_folders)}) mismatch!")
        
        # Normalize transition
        normalized_transition = self.normalize_transition()
        transition_duration = 0
        if normalized_transition:
            transition_duration = self.get_video_duration(normalized_transition)
        
        # Create segments
        segments = []
        for i, (audio, folder) in enumerate(zip(audio_files, image_folders), 1):
            print(f"\n📹 Processing Segment {i}/{len(audio_files)}")
            print(f"   Audio: {audio.name}")
            print(f"   Folder: {folder.name}")
            
            images = self.get_images_from_folder(folder)
            print(f"   Images: {len(images)} found")
            
            if not images:
                print(f"   ⚠️  Skipping - no images")
                continue
            
            segment_output = self.temp_folder / f"segment_{i:02d}.mp4"
            
            # Choose method based on mode
            if self.mode == 'video':
                success = self.create_segment_video_simple(audio, images, segment_output)
            else:  # with_template
                success = self.create_segment_video_template(audio, images, segment_output)
            
            if success:
                segments.append(segment_output)
                print(f"   ✅ Created")
        
        if not segments:
            print("\n❌ Error: No segments created!")
            return
        
        # Calculate total duration (for record.mp4 overlay)
        # In with_template mode, we need ONLY segment durations (not transitions)
        segment_duration = 0
        for segment in segments:
            segment_duration += self.get_video_duration(segment)
        
        total_duration = segment_duration
        if normalized_transition:
            total_duration += transition_duration * (len(segments) - 1)
        
        print(f"\n📊 Total video duration: {total_duration:.1f} seconds")
        if self.mode == 'with_template':
            print(f"   Segments only: {segment_duration:.1f}s (for record.mp4)")
        
        # Create concat with transitions
        print(f"\n🔗 Merging {len(segments)} segments...")
        final_concat = self.temp_folder / "final_concat.txt"
        
        with open(final_concat, 'w') as f:
            for i, segment in enumerate(segments):
                f.write(f"file '{segment.absolute()}'\n")
                
                if i < len(segments) - 1 and normalized_transition:
                    f.write(f"file '{normalized_transition.absolute()}'\n")
        
        # Create base video
        base_output = self.temp_folder / "base_video.mp4"
        
        cmd = [
            'ffmpeg', '-y',
            '-f', 'concat',
            '-safe', '0',
            '-i', str(final_concat),
            '-c:v', 'libx264',
            '-preset', 'fast',
            '-crf', '18',
            '-pix_fmt', 'yuv420p',
            '-c:a', 'aac',
            '-b:a', '192k',
            '-ar', '48000',
            str(base_output)
        ]
        
        subprocess.run(cmd, check=True, stderr=subprocess.DEVNULL)
        
        # Process record.mp4 if exists (ONLY for with_template mode)
        processed_record = None
        if self.mode == 'with_template' and self.record_video.exists():
            # record.mp4 should only appear during segments, not transitions
            processed_record = self.prepare_looping_record(segment_duration)
        elif self.mode == 'video' and self.record_video.exists():
            # In video mode, record appears throughout
            processed_record = self.prepare_looping_record(total_duration)
        
        final_output = self.output_folder / "final_video.mp4"
        
        if processed_record and self.mode == 'with_template':
            # Special handling for with_template mode
            # Need to overlay record.mp4 only during segments, not transitions
            print("\n🎨 Overlaying record.mp4 ONLY during segments (not transitions)...")
            
            # Create timeline for when to show record.mp4
            timeline = []
            current_time = 0
            for i, segment in enumerate(segments):
                seg_duration = self.get_video_duration(segment)
                # Show record during segment
                timeline.append((current_time, current_time + seg_duration, True))
                current_time += seg_duration
                
                # Don't show during transition
                if i < len(segments) - 1 and normalized_transition:
                    timeline.append((current_time, current_time + transition_duration, False))
                    current_time += transition_duration
            
            # Build enable expression for overlay
            enable_parts = []
            for start, end, show in timeline:
                if show:
                    enable_parts.append(f"between(t,{start},{end})")
            
            enable_expr = '+'.join(enable_parts)
            
            cmd = [
                'ffmpeg', '-y',
                '-i', str(base_output),
                '-i', str(processed_record),
                '-filter_complex', f'[1:v]format=rgba[fg];[0:v][fg]overlay=0:main_h-overlay_h+32:enable=\'{enable_expr}\':format=auto',
                '-c:v', 'libx264',
                '-preset', 'medium',
                '-crf', '23',
                '-c:a', 'copy',
                '-pix_fmt', 'yuv420p',
                str(final_output)
            ]
            
            subprocess.run(cmd, check=True, stderr=subprocess.DEVNULL)
            processed_record.unlink()
            base_output.unlink()
            
        elif processed_record and self.mode == 'video':
            # Simple overlay for video mode
            print("\n🎨 Overlaying record.mp4 throughout video...")
            
            cmd = [
                'ffmpeg', '-y',
                '-i', str(base_output),
                '-i', str(processed_record),
                '-filter_complex', '[1:v]format=rgba[fg];[0:v][fg]overlay=0:main_h-overlay_h+32:format=auto',
                '-c:v', 'libx264',
                '-preset', 'medium',
                '-crf', '23',
                '-c:a', 'copy',
                '-pix_fmt', 'yuv420p',
                str(final_output)
            ]
            
            subprocess.run(cmd, check=True, stderr=subprocess.DEVNULL)
            processed_record.unlink()
            base_output.unlink()
        else:
            print("\n✅ No record.mp4 - using base video")
            base_output.rename(final_output)
        
        # Cleanup
        print("\n🧹 Cleaning up...")
        for segment in segments:
            segment.unlink()
        final_concat.unlink()
        if normalized_transition:
            normalized_transition.unlink()
        
        print("\n" + "=" * 60)
        print(f"✅ Video completed successfully!")
        print(f"📁 Output: {final_output}")
        print(f"⏱️  Duration: {total_duration:.1f} seconds")
        print(f"📊 Segments: {len(segments)}")
        if self.mode == 'with_template':
            print(f"🎨 Template mode: Main screen + Anchor")
            if processed_record:
                print(f"🎥 record.mp4: Only during segments (not transitions)")
        print("=" * 60)


def main():
    print("""
    ╔══════════════════════════════════════════════════════════════╗
    ║         NEWS VIDEO CREATOR TOOL v4.0 ENHANCED               ║
    ║      2 Modes: Simple Video + Template with Anchor           ║
    ╚══════════════════════════════════════════════════════════════╝
    """)
    
    print("\n📋 Select Mode:")
    print("   1. video         - Simple full-screen video (original)")
    print("   2. with_template - Template + Main Screen + Anchor\n")
    
    mode_input = input("Enter mode (1 or 2): ").strip()
    
    if mode_input == '1':
        mode = 'video'
    elif mode_input == '2':
        mode = 'with_template'
    else:
        print("❌ Invalid mode! Using 'video' mode.")
        mode = 'video'
    
    print(f"\n✅ Mode selected: {mode.upper()}\n")
    
    base_folder = input("📂 Enter folder path (or press Enter for current): ").strip()
    
    if not base_folder:
        base_folder = os.getcwd()
    
    if not os.path.exists(base_folder):
        print(f"❌ Error: Folder '{base_folder}' not found!")
        return
    
    creator = NewsVideoCreator(base_folder, mode=mode)
    
    try:
        creator.create_final_video()
    except subprocess.CalledProcessError as e:
        print(f"\n❌ FFmpeg Error: {e}")
        print("Make sure FFmpeg is installed properly.")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()