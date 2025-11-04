from flask import Flask, request, send_file, jsonify
import requests
import re
import json
import urllib.parse
import os
import tempfile
import random
import string
import time
from urllib.parse import parse_qs, unquote
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

class YouTubeDownloader:
    def __init__(self):
        self.session = requests.Session()
        self.visitor_data = None
        self.api_keys = [
            "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8",  # Common YouTube API key
            "AIzaSyCtkvNIR1HCEwzsqK6JuE6KqpyjusTIUEQ",  # Another common key
            "AIzaSyA8eiZmM1FaDVjRy-df2KTyQ_vz_yYM39w",  # Web client key
            "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8",  # Android key
        ]
        self._get_visitor_data()
    
    def _get_visitor_data(self):
        """Get visitor data from YouTube using multiple methods"""
        try:
            # Method 1: Direct YouTube homepage
            headers = {
                'User-Agent': "com.google.android.youtube/19.08.35 (Linux; U; Android 12) gzip",
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
            }
            
            response = self.session.get('https://www.youtube.com/', headers=headers, timeout=10)
            
            # Try multiple patterns for visitor data
            patterns = [
                r'"VISITOR_DATA"\s*:\s*"([^"]+)"',
                r'VISITOR_DATA["\']?\s*:\s*["\']([^"\']+)["\']',
                r'visitorData["\']?\s*:\s*["\']([^"\']+)["\']',
                r'cvar\s*.*?VISITOR_DATA.*?:\s*["\']([^"\']+)["\']',
                r'X-Goog-Visitor-Id["\']?\s*:\s*["\']([^"\']+)["\']',
            ]
            
            for pattern in patterns:
                match = re.search(pattern, response.text)
                if match:
                    self.visitor_data = match.group(1)
                    print(f"Found visitor data: {self.visitor_data[:50]}...")
                    return
            
            # Method 2: Generate realistic visitor data
            self.visitor_data = self._generate_realistic_visitor_data()
            print("Using generated visitor data")
            
        except Exception as e:
            print(f"Error getting visitor data: {e}")
            self.visitor_data = self._generate_realistic_visitor_data()
    
    def _generate_realistic_visitor_data(self):
        """Generate realistic visitor data format"""
        # Real format: Cgt<12_chars_base64>=.<timestamp>
        random_part = ''.join(random.choices(string.ascii_letters + string.digits, k=12))
        timestamp = str(int(time.time()))
        return f"Cgt{random_part}=.{timestamp}"
    
    def get_video_info(self, video_url):
        """Try multiple methods to get video info"""
        methods = [
            self._try_innertube_api,
            self._try_web_client,
            self._try_android_client,
            self._try_embedded_client
        ]
        
        for method in methods:
            result = method(video_url)
            if result and 'error' not in result:
                return result
            elif result and 'bot' not in result.get('error', '').lower():
                return result
        
        return {"error": "All methods failed. Video may be restricted or unavailable."}
    
    def _try_innertube_api(self, video_url):
        """Try with different client configurations"""
        video_id = self._extract_video_id(video_url)
        if not video_id:
            return {"error": "Could not extract video ID"}
        
        clients = [
            {
                "clientName": "ANDROID",
                "clientVersion": "19.08.35",
                "userAgent": "com.google.android.youtube/19.08.35 (Linux; U; Android 12) gzip",
                "androidSdkVersion": 31
            },
            {
                "clientName": "WEB",
                "clientVersion": "2.20240101.00.00",
                "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            },
            {
                "clientName": "ANDROID_EMBEDDED_PLAYER",
                "clientVersion": "19.08.35",
                "userAgent": "com.google.android.youtube/19.08.35 (Linux; U; Android 12) gzip",
                "androidSdkVersion": 31
            },
            {
                "clientName": "TV_EMBEDDED_PLAYER",
                "clientVersion": "2.0",
                "userAgent": "Mozilla/5.0 (SMART-TV; Linux; Tizen 6.5) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/5.2 Chrome/85.0.4183.93 Safari/537.36"
            }
        ]
        
        for client_config in clients:
            try:
                result = self._make_api_request(video_id, client_config)
                if result and 'error' not in result:
                    return result
            except Exception as e:
                continue
        
        return {"error": "All client configurations failed"}
    
    def _make_api_request(self, video_id, client_config):
        """Make API request with specific client config"""
        innertube_url = "https://www.youtube.com/youtubei/v1/player"
        
        payload = {
            "context": {
                "client": client_config
            },
            "videoId": video_id,
            "contentCheckOk": True,
            "racyCheckOk": True
        }
        
        # Add common client fields
        if client_config["clientName"] in ["ANDROID", "ANDROID_EMBEDDED_PLAYER"]:
            payload["context"]["client"].update({
                "osName": "Android",
                "osVersion": "12",
                "hl": "en"
            })
        
        headers = {
            'User-Agent': client_config.get("userAgent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"),
            'Content-Type': "application/json",
            'Origin': "https://www.youtube.com",
            'X-YouTube-Client-Name': "1" if client_config["clientName"] == "WEB" else "3",
            'X-YouTube-Client-Version': client_config["clientVersion"],
            'X-Goog-Visitor-Id': self.visitor_data,
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        
        # Add API key for some clients
        if client_config["clientName"] == "WEB":
            innertube_url += f"?key={self.api_keys[2]}"
        
        print(f"Trying with client: {client_config['clientName']}")
        response = self.session.post(innertube_url, json=payload, headers=headers, timeout=30)
        
        if response.status_code != 200:
            return {"error": f"API request failed with status {response.status_code}"}
        
        response_data = response.json()
        return self._parse_player_response(response_data)
    
    def _try_web_client(self, video_url):
        """Try using web client with different approach"""
        try:
            video_id = self._extract_video_id(video_url)
            if not video_id:
                return {"error": "Could not extract video ID"}
            
            # Use web client with embed page
            embed_url = f"https://www.youtube.com/embed/{video_id}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
            }
            
            response = self.session.get(embed_url, headers=headers, timeout=15)
            
            # Extract from embed page
            patterns = [
                r'var ytInitialPlayerResponse\s*=\s*({.*?});',
                r'ytInitialPlayerResponse\s*=\s*({.*?});',
                r'window\["ytInitialPlayerResponse"\]\s*=\s*({.*?});'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, response.text, re.DOTALL)
                if match:
                    try:
                        player_response = json.loads(match.group(1))
                        return self._parse_player_response(player_response)
                    except:
                        continue
            
            return {"error": "Could not extract from embed page"}
            
        except Exception as e:
            return {"error": f"Web client method failed: {str(e)}"}
    
    def _try_android_client(self, video_url):
        """Try Android client with simplified approach"""
        try:
            video_id = self._extract_video_id(video_url)
            if not video_id:
                return {"error": "Could not extract video ID"}
            
            # Simple Android client request
            url = f"https://www.youtube.com/youtubei/v1/player?key={self.api_keys[0]}"
            
            payload = {
                "context": {
                    "client": {
                        "clientName": "ANDROID",
                        "clientVersion": "19.08.35",
                        "androidSdkVersion": 31,
                        "osName": "Android",
                        "osVersion": "12",
                        "hl": "en"
                    }
                },
                "videoId": video_id,
                "params": "CgIQBg=="
            }
            
            headers = {
                'User-Agent': 'com.google.android.youtube/19.08.35 (Linux; U; Android 12) gzip',
                'Content-Type': 'application/json',
            }
            
            response = self.session.post(url, json=payload, headers=headers, timeout=20)
            
            if response.status_code == 200:
                return self._parse_player_response(response.json())
            else:
                return {"error": f"Android client failed: {response.status_code}"}
                
        except Exception as e:
            return {"error": f"Android client method failed: {str(e)}"}
    
    def _try_embedded_client(self, video_url):
        """Try embedded player client"""
        try:
            video_id = self._extract_video_id(video_url)
            if not video_id:
                return {"error": "Could not extract video ID"}
            
            url = "https://www.youtube.com/youtubei/v1/player"
            
            payload = {
                "context": {
                    "client": {
                        "clientName": "ANDROID_EMBEDDED_PLAYER",
                        "clientVersion": "19.08.35",
                        "clientScreen": "EMBED",
                        "androidSdkVersion": 31,
                        "osName": "Android",
                        "osVersion": "12",
                        "hl": "en"
                    }
                },
                "videoId": video_id,
                "params": "CgIQBg=="
            }
            
            headers = {
                'User-Agent': 'com.google.android.youtube/19.08.35 (Linux; U; Android 12) gzip',
                'Content-Type': 'application/json',
            }
            
            response = self.session.post(url, json=payload, headers=headers, timeout=20)
            
            if response.status_code == 200:
                return self._parse_player_response(response.json())
            else:
                return {"error": f"Embedded client failed: {response.status_code}"}
                
        except Exception as e:
            return {"error": f"Embedded client method failed: {str(e)}"}
    
    def _parse_player_response(self, response_data):
        """Parse the player response"""
        try:
            playability_status = response_data.get('playabilityStatus', {})
            status = playability_status.get('status', 'UNKNOWN')
            
            if status != 'OK':
                error_reason = playability_status.get('reason', 'Video not playable')
                return {"error": f"Video not playable: {error_reason}"}
            
            video_details = response_data.get('videoDetails', {})
            streaming_data = response_data.get('streamingData', {})
            
            if not streaming_data:
                return {"error": "No streaming data available"}
            
            formats = self._parse_streaming_data(streaming_data)
            
            if not formats:
                return {"error": "No downloadable formats found"}
            
            return {
                'title': video_details.get('title', 'Unknown Title'),
                'duration': video_details.get('lengthSeconds', '0'),
                'author': video_details.get('author', 'Unknown Channel'),
                'viewCount': video_details.get('viewCount', '0'),
                'thumbnail': self._get_best_thumbnail(video_details.get('thumbnail', {})),
                'formats': formats,
                'videoId': video_details.get('videoId', ''),
                'playabilityStatus': status
            }
            
        except Exception as e:
            return {"error": f"Failed to parse response: {str(e)}"}
    
    def _get_best_thumbnail(self, thumbnail_data):
        thumbnails = thumbnail_data.get('thumbnails', [])
        if thumbnails:
            return thumbnails[-1].get('url', '')
        return ''
    
    def _parse_streaming_data(self, streaming_data):
        formats = []
        combined_formats = streaming_data.get('formats', [])
        adaptive_formats = streaming_data.get('adaptiveFormats', [])
        all_formats = combined_formats + adaptive_formats
        
        for fmt in all_formats:
            format_info = self._extract_format_details(fmt)
            if format_info and format_info.get('url'):
                formats.append(format_info)
        
        formats.sort(key=lambda x: (
            x.get('hasVideo', False),
            x.get('height', 0),
            x.get('bitrate', 0)
        ), reverse=True)
        
        return formats
    
    def _extract_format_details(self, fmt):
        try:
            mime_type = fmt.get('mimeType', '')
            quality_label = fmt.get('qualityLabel', '')
            if not quality_label and 'video' in mime_type:
                height = fmt.get('height', 0)
                if height:
                    quality_label = f"{height}p"
            
            has_video = 'video' in mime_type
            has_audio = 'audio' in mime_type
            
            download_url = fmt.get('url', '')
            
            if 'signatureCipher' in fmt:
                cipher_data = self._decode_signature_cipher(fmt['signatureCipher'])
                download_url = cipher_data.get('url', '')
            
            if not download_url:
                return None
            
            content_length = fmt.get('contentLength')
            file_size = self._format_file_size(content_length) if content_length else 'Unknown'
            
            return {
                'itag': fmt.get('itag'),
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
            }
            
        except Exception as e:
            return None
    
    def _format_file_size(self, size_bytes):
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
        try:
            params = {}
            for item in cipher_string.split('&'):
                if '=' in item:
                    key, value = item.split('=', 1)
                    params[key] = unquote(value)
            return {'url': params.get('url', '')}
        except:
            return {'url': ''}
    
    def _extract_video_id(self, url):
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
        try:
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Range': 'bytes=0-',
                'Accept': '*/*',
            }
            
            response = self.session.get(download_url, headers=headers, stream=True, timeout=60)
            response.raise_for_status()
            
            downloaded = 0
            with open(temp_file.name, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
            
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
        <head><title>YouTube Downloader - Multi-Client Approach</title></head>
        <body>
            <h1>YouTube Downloader API</h1>
            <p>Using Multiple Client Methods to Avoid Bot Detection</p>
            
            <div style="background: #f5f5f5; padding: 15px; margin: 10px 0; border-radius: 5px;">
                <h3>Endpoints:</h3>
                <p><code>GET /info?url=YOUTUBE_URL</code> - Get video info</p>
                <p><code>GET /download?url=YOUTUBE_URL&quality=QUALITY</code> - Download video</p>
            </div>
            
            <form action="/info" method="get">
                <input type="text" name="url" placeholder="Enter YouTube URL" style="width: 400px; padding: 10px;" 
                       value="https://www.youtube.com/watch?v=dQw4w9WgXcQ">
                <button type="submit" style="padding: 10px 20px;">Get Video Info</button>
            </form>
        </body>
    </html>
    """

@app.route('/download')
def download_video():
    video_url = request.args.get('url', '')
    quality = request.args.get('quality', 'best')
    
    if not video_url:
        return jsonify({"error": "URL parameter is required"}), 400
    
    try:
        video_info = downloader.get_video_info(video_url)
        if 'error' in video_info:
            return jsonify({"error": video_info['error']}), 400
        
        formats = video_info.get('formats', [])
        if not formats:
            return jsonify({"error": "No downloadable formats found"}), 400
        
        selected_format = _select_best_format(formats, quality)
        if not selected_format:
            available_formats = list(set([f.get('quality', 'unknown') for f in formats if f.get('hasVideo') and f.get('quality')]))
            return jsonify({
                "error": f"Quality '{quality}' not available",
                "available_formats": sorted(available_formats)
            }), 400
        
        download_url = selected_format.get('url')
        if not download_url:
            return jsonify({"error": "No download URL available"}), 400
        
        title = video_info.get('title', 'video')
        safe_title = re.sub(r'[<>:"/\\|?*]', '', title)
        file_extension = 'mp4' if 'mp4' in selected_format.get('mimeType', '') else 'webm'
        filename = f"{safe_title}_{selected_format.get('quality', 'video')}.{file_extension}"
        
        temp_file_path, file_size = downloader.download_video(download_url, filename)
        
        response = send_file(
            temp_file_path,
            as_attachment=True,
            download_name=filename,
            mimetype=selected_format.get('mimeType', 'video/mp4')
        )
        
        @response.call_on_close
        def cleanup():
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
        
        return response
        
    except Exception as e:
        return jsonify({"error": f"Download failed: {str(e)}"}), 500

@app.route('/info')
def video_info():
    video_url = request.args.get('url', '')
    if not video_url:
        return jsonify({"error": "URL parameter is required"}), 400
    
    result = downloader.get_video_info(video_url)
    return jsonify(result)

@app.route('/health')
def health_check():
    return jsonify({"status": "healthy", "service": "youtube-downloader"})

def _select_best_format(formats, quality):
    video_formats = [f for f in formats if f.get('hasVideo')]
    if not video_formats:
        return None
    
    if quality == 'best':
        for fmt in video_formats:
            if fmt.get('hasAudio') and fmt.get('hasVideo'):
                return fmt
        return max(video_formats, key=lambda x: x.get('height', 0))
    else:
        for fmt in video_formats:
            if (fmt.get('quality') == quality and fmt.get('hasVideo')):
                return fmt
        return None

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)