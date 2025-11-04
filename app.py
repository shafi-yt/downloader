from flask import Flask, request, send_file, jsonify
import requests
import re
import json
import urllib.parse
import os
import tempfile
import random
import string
from urllib.parse import parse_qs, unquote
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

class YouTubeDownloader:
    def __init__(self):
        self.session = requests.Session()
        self.visitor_data = None
        self._get_visitor_data()
    
    def _get_visitor_data(self):
        """Get visitor data from YouTube homepage using exact VR user agent"""
        try:
            headers = {
                'User-Agent': "com.google.android.apps.youtube.vr.oculus/1.65.10 (Linux; U; Android 12L; eureka-user Build/SQ3A.220605.009.A1) gzip",
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
            }
            
            print("Fetching visitor data from YouTube...")
            response = self.session.get('https://www.youtube.com/', headers=headers, timeout=10)
            
            # Extract visitor data from response using multiple patterns
            visitor_patterns = [
                r'"VISITOR_DATA"\s*:\s*"([^"]+)"',
                r'VISITOR_DATA["\']?\s*:\s*["\']([^"\']+)["\']',
                r'visitorData["\']?\s*:\s*["\']([^"\']+)["\']',
                r'cvar\s*.*?VISITOR_DATA.*?:\s*["\']([^"\']+)["\']',
            ]
            
            for pattern in visitor_patterns:
                match = re.search(pattern, response.text)
                if match:
                    self.visitor_data = match.group(1)
                    print(f"Found visitor data: {self.visitor_data[:50]}...")
                    break
            
            if not self.visitor_data:
                # Generate a fallback visitor data
                self.visitor_data = self._generate_visitor_data()
                print("Using generated visitor data")
            
        except Exception as e:
            print(f"Error getting visitor data: {e}")
            self.visitor_data = self._generate_visitor_data()
    
    def _generate_visitor_data(self):
        """Generate a fallback visitor data"""
        # Format: Cgt<random_12_chars>... (similar to real visitor data)
        random_chars = ''.join(random.choices(string.ascii_letters + string.digits, k=12))
        return f"Cgt{random_chars}="
    
    def get_video_info(self, video_url):
        """YouTube video information extract using exact VR client with visitor data"""
        try:
            video_id = self._extract_video_id(video_url)
            if not video_id:
                return {"error": "Could not extract video ID from URL"}
            
            # Use the exact innerTube API as in your request
            innertube_url = "https://www.youtube.com/youtubei/v1/player?prettyPrint=false"
            
            # Exact payload matching your request
            payload = {
                "context": {
                    "client": {
                        "clientName": "ANDROID_VR",
                        "clientVersion": "1.65.10",
                        "userAgent": "com.google.android.apps.youtube.vr.oculus/1.65.10 (Linux; U; Android 12L; eureka-user Build/SQ3A.220605.009.A1) gzip",
                        "deviceMake": "Oculus",
                        "deviceModel": "Quest 3",
                        "androidSdkVersion": 32,
                        "osName": "Android",
                        "osVersion": "12L",
                        "hl": "en"
                    }
                },
                "videoId": video_id,
                "contentCheckOk": True,
                "racyCheckOk": True
            }
            
            # Exact headers matching your request with visitor data
            headers = {
                'User-Agent': "com.google.android.apps.youtube.vr.oculus/1.65.10 (Linux; U; Android 12L; eureka-user Build/SQ3A.220605.009.A1) gzip",
                'Connection': "Keep-Alive",
                'Accept-Encoding': "gzip",
                'Content-Type': "application/json",
                'Origin': "https://www.youtube.com",
                'X-Youtube-Client-Name': "28",
                'X-Youtube-Client-Version': "1.65.10",
                'X-Goog-Visitor-Id': self.visitor_data
            }
            
            print(f"Making API request for video ID: {video_id}")
            print(f"Using visitor data: {self.visitor_data[:30]}...")
            
            response = self.session.post(innertube_url, json=payload, headers=headers, timeout=30)
            
            if response.status_code != 200:
                return {"error": f"API request failed with status {response.status_code}: {response.text}"}
            
            response_data = response.json()
            print(f"API Response received successfully")
            
            # Parse the response
            return self._parse_player_response(response_data)
            
        except Exception as e:
            return {"error": f"Failed to get video info: {str(e)}"}
    
    def _parse_player_response(self, response_data):
        """Parse the player response"""
        try:
            # Check if response has playability status
            playability_status = response_data.get('playabilityStatus', {})
            status = playability_status.get('status', 'UNKNOWN')
            
            if status != 'OK':
                error_reason = playability_status.get('reason', 'Video not playable')
                # Check if it's a bot detection error
                if 'bot' in error_reason.lower() or 'sign in' in error_reason.lower():
                    # Refresh visitor data and retry
                    self._refresh_visitor_data()
                    return {"error": f"Bot detection triggered. Please try again. Reason: {error_reason}"}
                return {"error": f"Video not playable: {error_reason}"}
            
            # Extract video details
            video_details = response_data.get('videoDetails', {})
            streaming_data = response_data.get('streamingData', {})
            
            if not streaming_data:
                return {"error": "No streaming data available"}
            
            # Parse formats
            formats = self._parse_streaming_data(streaming_data)
            
            if not formats:
                return {"error": "No downloadable formats found"}
            
            result = {
                'title': video_details.get('title', 'Unknown Title'),
                'duration': video_details.get('lengthSeconds', '0'),
                'author': video_details.get('author', 'Unknown Channel'),
                'viewCount': video_details.get('viewCount', '0'),
                'thumbnail': self._get_best_thumbnail(video_details.get('thumbnail', {})),
                'formats': formats,
                'videoId': video_details.get('videoId', ''),
                'playabilityStatus': status
            }
            
            print(f"Found {len(formats)} formats for video: {result['title']}")
            return result
            
        except Exception as e:
            return {"error": f"Failed to parse response: {str(e)}"}
    
    def _refresh_visitor_data(self):
        """Refresh visitor data"""
        print("Refreshing visitor data...")
        self._get_visitor_data()
    
    def _get_best_thumbnail(self, thumbnail_data):
        """Get the highest quality thumbnail"""
        thumbnails = thumbnail_data.get('thumbnails', [])
        if thumbnails:
            # Return the last (highest quality) thumbnail
            return thumbnails[-1].get('url', '')
        return ''
    
    def _parse_streaming_data(self, streaming_data):
        """Parse streaming data from response"""
        formats = []
        
        # Combined formats (video + audio)
        combined_formats = streaming_data.get('formats', [])
        # Adaptive formats (separate video/audio)
        adaptive_formats = streaming_data.get('adaptiveFormats', [])
        
        all_formats = combined_formats + adaptive_formats
        
        for fmt in all_formats:
            format_info = self._extract_format_details(fmt)
            if format_info and format_info.get('url'):
                formats.append(format_info)
        
        # Sort by quality (highest first)
        formats.sort(key=lambda x: (
            x.get('hasVideo', False),
            x.get('height', 0),
            x.get('bitrate', 0)
        ), reverse=True)
        
        return formats
    
    def _extract_format_details(self, fmt):
        """Extract detailed format information"""
        try:
            mime_type = fmt.get('mimeType', '')
            itag = fmt.get('itag')
            
            # Get quality label
            quality_label = fmt.get('qualityLabel', '')
            if not quality_label and 'video' in mime_type:
                height = fmt.get('height', 0)
                if height:
                    quality_label = f"{height}p"
            
            # Determine format type
            has_video = 'video' in mime_type
            has_audio = 'audio' in mime_type
            
            # Get download URL
            download_url = fmt.get('url', '')
            
            # Handle signature cipher if present
            if 'signatureCipher' in fmt:
                cipher_data = self._decode_signature_cipher(fmt['signatureCipher'])
                download_url = cipher_data.get('url', '')
            
            if not download_url:
                return None
            
            # Calculate approximate file size
            content_length = fmt.get('contentLength')
            file_size = self._format_file_size(content_length) if content_length else 'Unknown'
            
            format_info = {
                'itag': itag,
                'url': download_url,
                'mimeType': mime_type,
                'quality': quality_label,
                'bitrate': fmt.get('bitrate', 0),
                'width': fmt.get('width', 0),
                'height': fmt.get('height', 0),
                'contentLength': content_length,
                'fileSize': file_size,
                'hasVideo': has_video,
                'hasAudio': has_audio,
                'type': 'video+audio' if has_video and has_audio else 'video' if has_video else 'audio',
                'fps': fmt.get('fps', 0),
                'qualityOrdinal': fmt.get('qualityOrdinal', '')
            }
            
            return format_info
            
        except Exception as e:
            print(f"Error extracting format details: {e}")
            return None
    
    def _format_file_size(self, size_bytes):
        """Format file size in human readable format"""
        try:
            size_bytes = int(size_bytes)
            for unit in ['B', 'KB', 'MB', 'GB']:
                if size_bytes < 1024.0:
                    return f"{size_bytes:.1f} {unit}"
                size_bytes /= 1024.0
            return f"{size_bytes:.1f} TB"
        except:
            return "Unknown"
    
    def _decode_signature_cipher(self, cipher_string):
        """Decode signature cipher to get actual URL"""
        try:
            params = {}
            for item in cipher_string.split('&'):
                if '=' in item:
                    key, value = item.split('=', 1)
                    params[key] = unquote(value)
            
            url = params.get('url', '')
            signature = params.get('s', '')
            
            if url and signature:
                # For now, return the URL without signature (will work for some videos)
                return {'url': url}
            
            return {'url': url}
        except:
            return {'url': ''}
    
    def _extract_video_id(self, url):
        """Extract video ID from various YouTube URL formats"""
        patterns = [
            r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
            r'(?:embed\/)([0-9A-Za-z_-]{11})',
            r'(?:youtu\.be\/)([0-9A-Za-z_-]{11})'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None
    
    def download_video(self, download_url, filename):
        """Download video to temporary file"""
        try:
            # Create temporary file
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
            
            # Download headers with same user agent
            headers = {
                'User-Agent': "com.google.android.apps.youtube.vr.oculus/1.65.10 (Linux; U; Android 12L; eureka-user Build/SQ3A.220605.009.A1) gzip",
                'Range': 'bytes=0-',
                'Accept': '*/*',
                'Accept-Encoding': 'identity',
                'Connection': 'keep-alive'
            }
            
            print(f"Starting download from: {download_url[:100]}...")
            
            # Stream download
            response = self.session.get(download_url, headers=headers, stream=True, timeout=60)
            response.raise_for_status()
            
            # Download file
            total_size = 0
            content_length = response.headers.get('content-length')
            if content_length:
                total_size = int(content_length)
            
            downloaded = 0
            with open(temp_file.name, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
            
            print(f"Download completed: {downloaded} bytes")
            return temp_file.name, downloaded
            
        except Exception as e:
            if 'temp_file' in locals() and os.path.exists(temp_file.name):
                os.unlink(temp_file.name)
            raise e

# Global downloader instance
downloader = YouTubeDownloader()

@app.route('/')
def home():
    return """
    <html>
        <head>
            <title>YouTube Downloader API - VR Client with Visitor Data</title>
            <style>
                body { font-family: Arial, sans-serif; max-width: 1000px; margin: 0 auto; padding: 20px; }
                .endpoint { background: #f5f5f5; padding: 15px; margin: 10px 0; border-radius: 5px; }
                code { background: #eee; padding: 2px 5px; border-radius: 3px; }
                .format { margin: 5px 0; padding: 10px; background: white; border-radius: 4px; border-left: 4px solid #007cba; }
                .video-info { background: #e7f3ff; padding: 15px; border-radius: 5px; margin: 10px 0; }
                .success { color: green; }
                .error { color: red; }
                .btn { background: #007cba; color: white; padding: 10px 15px; text-decoration: none; border-radius: 4px; display: inline-block; margin: 5px; }
            </style>
        </head>
        <body>
            <h1>YouTube Downloader API</h1>
            <p>Using Android VR Client with Real Visitor Data</p>
            
            <div class="video-info">
                <h3>Current Implementation:</h3>
                <ul>
                    <li><strong>Client:</strong> ANDROID_VR (Oculus Quest 3)</li>
                    <li><strong>Version:</strong> 1.65.10</li>
                    <li><strong>User Agent:</strong> Exact VR Oculus user agent</li>
                    <li><strong>Visitor Data:</strong> Real data from YouTube</li>
                    <li><strong>Anti-Bot:</strong> Visitor data integration</li>
                </ul>
            </div>
            
            <div class="endpoint">
                <h3>Download Endpoint</h3>
                <p><code>GET /download?url=YOUTUBE_URL&quality=QUALITY</code></p>
                <p><strong>Parameters:</strong></p>
                <ul>
                    <li><code>url</code> - YouTube video URL (required)</li>
                    <li><code>quality</code> - Video quality (optional, default: best available)</li>
                </ul>
                <p><strong>Example:</strong></p>
                <p><code>/download?url=https://www.youtube.com/watch?v=TxG1opTR0Yc&quality=720p</code></p>
            </div>
            
            <div class="endpoint">
                <h3>Info Endpoint</h3>
                <p><code>GET /info?url=YOUTUBE_URL</code></p>
                <p>Get available formats for a video</p>
                <p><strong>Example:</strong></p>
                <p><code>/info?url=https://www.youtube.com/watch?v=TxG1opTR0Yc</code></p>
            </div>
            
            <div class="endpoint">
                <h3>Test the API:</h3>
                <form action="/info" method="get">
                    <input type="text" name="url" placeholder="Enter YouTube URL" style="width: 400px; padding: 10px; font-size: 16px;" 
                           value="https://www.youtube.com/watch?v=TxG1opTR0Yc">
                    <button type="submit" style="padding: 10px 20px; font-size: 16px;">Get Video Info</button>
                </form>
            </div>
        </body>
    </html>
    """

@app.route('/download')
def download_video():
    """Download YouTube video"""
    video_url = request.args.get('url', '')
    quality = request.args.get('quality', 'best')
    
    if not video_url:
        return jsonify({"error": "URL parameter is required"}), 400
    
    # Validate YouTube URL
    if 'youtube.com' not in video_url and 'youtu.be' not in video_url:
        return jsonify({"error": "Invalid YouTube URL"}), 400
    
    try:
        # Get video info
        print(f"Processing download request for: {video_url}")
        video_info = downloader.get_video_info(video_url)
        if 'error' in video_info:
            return jsonify({"error": video_info['error']}), 400
        
        formats = video_info.get('formats', [])
        if not formats:
            return jsonify({"error": "No downloadable formats found"}), 400
        
        # Find the best format based on quality preference
        selected_format = _select_best_format(formats, quality)
        if not selected_format:
            available_formats = list(set([f.get('quality', 'unknown') for f in formats if f.get('hasVideo') and f.get('quality')]))
            return jsonify({
                "error": f"Requested quality '{quality}' not available",
                "available_formats": sorted(available_formats),
                "all_formats": [f['quality'] for f in formats if f.get('hasVideo')]
            }), 400
        
        # Get download URL
        download_url = selected_format.get('url')
        if not download_url:
            return jsonify({"error": "No download URL available for selected format"}), 400
        
        # Create filename
        title = video_info.get('title', 'video')
        safe_title = re.sub(r'[<>:"/\\|?*]', '', title)
        file_extension = 'mp4' if 'mp4' in selected_format.get('mimeType', '') else 'webm'
        filename = f"{safe_title}_{selected_format.get('quality', 'video')}.{file_extension}"
        
        print(f"Downloading: {title} at {selected_format.get('quality')} quality")
        
        # Download video
        temp_file_path, file_size = downloader.download_video(download_url, filename)
        
        # Send file
        response = send_file(
            temp_file_path,
            as_attachment=True,
            download_name=filename,
            mimetype=selected_format.get('mimeType', 'video/mp4')
        )
        
        # Cleanup temp file after send
        @response.call_on_close
        def cleanup():
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
                print(f"Cleaned up temp file: {temp_file_path}")
        
        return response
        
    except Exception as e:
        print(f"Download error: {str(e)}")
        return jsonify({"error": f"Download failed: {str(e)}"}), 500

@app.route('/info')
def video_info():
    """Get video information and available formats"""
    video_url = request.args.get('url', '')
    
    if not video_url:
        return jsonify({"error": "URL parameter is required"}), 400
    
    if 'youtube.com' not in video_url and 'youtu.be' not in video_url:
        return jsonify({"error": "Invalid YouTube URL"}), 400
    
    print(f"Getting info for: {video_url}")
    result = downloader.get_video_info(video_url)
    
    # Format the response for better readability
    if 'formats' in result:
        result['available_qualities'] = list(set(
            [f['quality'] for f in result['formats'] if f.get('hasVideo') and f.get('quality')]
        ))
    
    return jsonify(result)

@app.route('/refresh-visitor')
def refresh_visitor():
    """Refresh visitor data manually"""
    downloader._refresh_visitor_data()
    return jsonify({
        "status": "success", 
        "message": "Visitor data refreshed",
        "visitor_data": downloader.visitor_data[:50] + "..."
    })

@app.route('/health')
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy", 
        "service": "youtube-downloader",
        "version": "4.0",
        "client": "ANDROID_VR",
        "clientVersion": "1.65.10",
        "visitor_data": downloader.visitor_data[:30] + "..." if downloader.visitor_data else "None"
    })

def _select_best_format(formats, quality):
    """Select the best format based on quality preference"""
    video_formats = [f for f in formats if f.get('hasVideo')]
    
    if not video_formats:
        return None
    
    if quality == 'best':
        # Return highest quality with both audio and video
        for fmt in video_formats:
            if fmt.get('hasAudio') and fmt.get('hasVideo'):
                return fmt
        # If no combined format, return highest video quality
        return max(video_formats, key=lambda x: x.get('height', 0))
    else:
        # Return specific quality
        for fmt in video_formats:
            if (fmt.get('quality') == quality and 
                fmt.get('hasVideo') and 
                (fmt.get('hasAudio') or quality in ['1080p', '720p', '480p'])):
                return fmt
        return None

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)