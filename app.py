from flask import Flask, request, send_file, jsonify
import requests
import re
import json
import urllib.parse
import os
import tempfile
from urllib.parse import parse_qs, unquote

app = Flask(__name__)

class SimpleYouTubeDownloader:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
    
    def get_video_info(self, video_url):
        """YouTube video information extract করা - updated for 2024"""
        try:
            response = requests.get(video_url, headers=self.headers, timeout=30)
            html = response.text
            
            # Multiple patterns for player response - updated patterns
            patterns = [
                r'var ytInitialPlayerResponse\s*=\s*({.*?});',
                r'window\["ytInitialPlayerResponse"\]\s*=\s*({.*?});',
                r'ytInitialPlayerResponse\s*=\s*({.*?});',
                r'ytInitialData\s*=\s*({.*?});',
                r'window\["ytInitialData"\]\s*=\s*({.*?});'
            ]
            
            player_response = None
            for pattern in patterns:
                match = re.search(pattern, html, re.DOTALL)
                if match:
                    try:
                        player_response = json.loads(match.group(1))
                        break
                    except json.JSONDecodeError:
                        continue
            
            if not player_response:
                # Alternative method: look for embedded data
                return self._extract_alternative_info(html, video_url)
            
            # Try different response structures
            streaming_data = None
            video_details = None
            
            # Structure 1: Direct player response
            if 'streamingData' in player_response:
                streaming_data = player_response.get('streamingData', {})
                video_details = player_response.get('videoDetails', {})
            # Structure 2: Nested in contents
            elif 'contents' in player_response:
                contents = player_response['contents']
                if 'twoColumnWatchNextResults' in contents:
                    # This is ytInitialData, not player response
                    return self._extract_from_initial_data(player_response, video_url)
            
            if not streaming_data:
                return {"error": "Streaming data not found in response"}
            
            return {
                'title': video_details.get('title', 'video'),
                'duration': video_details.get('lengthSeconds', '0'),
                'author': video_details.get('author', 'Unknown'),
                'formats': self._parse_formats(streaming_data)
            }
            
        except Exception as e:
            return {"error": f"Failed to get video info: {str(e)}"}
    
    def _extract_alternative_info(self, html, video_url):
        """Alternative method to extract video info"""
        try:
            # Extract from ytInitialData
            pattern = r'var ytInitialData\s*=\s*({.*?});'
            match = re.search(pattern, html, re.DOTALL)
            if match:
                initial_data = json.loads(match.group(1))
                return self._extract_from_initial_data(initial_data, video_url)
            
            # Try to find video title from HTML
            title_match = re.search(r'<title>(.*?)</title>', html)
            title = title_match.group(1).replace(' - YouTube', '') if title_match else 'video'
            
            return {
                'title': title,
                'duration': '0',
                'author': 'Unknown',
                'formats': [],
                'error': 'Could not extract full video info'
            }
            
        except Exception as e:
            return {"error": f"Alternative extraction failed: {str(e)}"}
    
    def _extract_from_initial_data(self, initial_data, video_url):
        """Extract info from ytInitialData"""
        try:
            # Complex extraction from initial data structure
            video_info = {
                'title': 'video',
                'duration': '0',
                'author': 'Unknown',
                'formats': []
            }
            
            # Extract title
            if 'contents' in initial_data:
                contents = initial_data['contents']
                if 'twoColumnWatchNextResults' in contents:
                    results = contents['twoColumnWatchNextResults']
                    if 'results' in results and 'results' in results['results']:
                        for item in results['results']['results']['contents']:
                            if 'videoPrimaryInfoRenderer' in item:
                                title_element = item['videoPrimaryInfoRenderer'].get('title', {})
                                if 'runs' in title_element and len(title_element['runs']) > 0:
                                    video_info['title'] = title_element['runs'][0]['text']
                            
                            if 'videoSecondaryInfoRenderer' in item:
                                author_element = item['videoSecondaryInfoRenderer'].get('owner', {})
                                if 'videoOwnerRenderer' in author_element:
                                    author_name = author_element['videoOwnerRenderer'].get('title', {})
                                    if 'runs' in author_name and len(author_name['runs']) > 0:
                                        video_info['author'] = author_name['runs'][0]['text']
            
            # Get formats using innerTube API
            formats_result = self._get_formats_via_inner_tube(video_url)
            if 'formats' in formats_result:
                video_info['formats'] = formats_result['formats']
            elif 'error' in formats_result:
                video_info['error'] = formats_result['error']
            
            return video_info
            
        except Exception as e:
            return {"error": f"Initial data extraction failed: {str(e)}"}
    
    def _get_formats_via_inner_tube(self, video_url):
        """Get formats using innerTube API"""
        try:
            # Extract video ID
            video_id = self._extract_video_id(video_url)
            if not video_id:
                return {"error": "Could not extract video ID"}
            
            # Use innertube API
            innertube_url = "https://www.youtube.com/youtubei/v1/player"
            
            payload = {
                "context": {
                    "client": {
                        "clientName": "ANDROID",
                        "clientVersion": "19.08.35",
                        "androidSdkVersion": 30,
                        "osName": "Android",
                        "osVersion": "11"
                    }
                },
                "videoId": video_id,
                "params": "CgIQBg==",
                "playbackContext": {
                    "contentPlaybackContext": {
                        "html5Preference": "HTML5_PREF_WANTS"
                    }
                },
                "contentCheckOk": True,
                "racyCheckOk": True
            }
            
            headers = {
                'User-Agent': 'com.google.android.youtube/19.08.35 (Linux; U; Android 11) gzip',
                'Content-Type': 'application/json',
                'X-YouTube-Client-Name': '3',
                'X-YouTube-Client-Version': '19.08.35'
            }
            
            response = requests.post(innertube_url, json=payload, headers=headers, timeout=30)
            response_data = response.json()
            
            if 'streamingData' in response_data:
                return {
                    'formats': self._parse_formats(response_data['streamingData'])
                }
            else:
                return {"error": "No streaming data in API response"}
                
        except Exception as e:
            return {"error": f"InnerTube API failed: {str(e)}"}
    
    def _extract_video_id(self, url):
        """Extract video ID from YouTube URL"""
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
    
    def _parse_formats(self, streaming_data):
        """Available formats parse করা"""
        formats = []
        
        if not streaming_data:
            return formats
        
        # Combined formats (video + audio)
        combined_formats = streaming_data.get('formats', [])
        # Adaptive formats (video/audio separate)
        adaptive_formats = streaming_data.get('adaptiveFormats', [])
        
        all_formats = combined_formats + adaptive_formats
        
        for fmt in all_formats:
            format_info = self._extract_format_info(fmt)
            if format_info and format_info.get('url'):
                formats.append(format_info)
        
        return formats
    
    def _extract_format_info(self, fmt):
        """Individual format information extract করা"""
        mime_type = fmt.get('mimeType', '')
        quality_label = fmt.get('qualityLabel', '')
        
        if not quality_label and 'video' in mime_type:
            if fmt.get('height'):
                quality_label = f"{fmt.get('height')}p"
        
        format_info = {
            'itag': fmt.get('itag'),
            'url': fmt.get('url', ''),
            'mimeType': mime_type,
            'quality': quality_label,
            'bitrate': fmt.get('bitrate', 0),
            'width': fmt.get('width', 0),
            'height': fmt.get('height', 0),
            'contentLength': fmt.get('contentLength', '0'),
            'hasVideo': 'video' in mime_type,
            'hasAudio': 'audio' in mime_type,
        }
        
        # Handle signature cipher
        if 'signatureCipher' in fmt:
            cipher_data = self._parse_signature_cipher(fmt['signatureCipher'])
            format_info.update(cipher_data)
        
        return format_info
    
    def _parse_signature_cipher(self, cipher_string):
        """Signature cipher decode করা"""
        try:
            params = {}
            for item in cipher_string.split('&'):
                if '=' in item:
                    key, value = item.split('=', 1)
                    params[key] = unquote(value)
            
            return {
                'url': params.get('url', ''),
                's': params.get('s', ''),
                'sp': params.get('sp', 'signature')
            }
        except:
            return {}

# Global downloader instance
downloader = SimpleYouTubeDownloader()

@app.route('/')
def home():
    return """
    <html>
        <head>
            <title>YouTube Downloader API</title>
            <style>
                body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
                .endpoint { background: #f5f5f5; padding: 15px; margin: 10px 0; border-radius: 5px; }
                code { background: #eee; padding: 2px 5px; border-radius: 3px; }
                .success { color: green; }
                .error { color: red; }
            </style>
        </head>
        <body>
            <h1>YouTube Downloader API</h1>
            <p>Simple API to download YouTube videos</p>
            
            <div class="endpoint">
                <h3>Download Endpoint</h3>
                <p><code>GET /download?url=YOUTUBE_URL&format=QUALITY</code></p>
                <p><strong>Parameters:</strong></p>
                <ul>
                    <li><code>url</code> - YouTube video URL (required)</li>
                    <li><code>format</code> - Video quality (optional, default: best)</li>
                </ul>
                <p><strong>Example:</strong></p>
                <p><code>/download?url=https://www.youtube.com/watch?v=VIDEO_ID&format=720p</code></p>
            </div>
            
            <div class="endpoint">
                <h3>Info Endpoint</h3>
                <p><code>GET /info?url=YOUTUBE_URL</code></p>
                <p>Get available formats for a video</p>
            </div>
            
            <div class="endpoint">
                <h3>Available Formats:</h3>
                <p>144p, 240p, 360p, 480p, 720p, 1080p, best</p>
            </div>
            
            <div class="endpoint">
                <h3>Test the API:</h3>
                <form action="/info" method="get">
                    <input type="text" name="url" placeholder="Enter YouTube URL" style="width: 300px; padding: 8px;">
                    <button type="submit" style="padding: 8px 16px;">Get Info</button>
                </form>
            </div>
        </body>
    </html>
    """

@app.route('/download')
def download():
    """Main download endpoint"""
    video_url = request.args.get('url', '')
    quality = request.args.get('format', 'best')
    
    if not video_url:
        return jsonify({"error": "URL parameter is required"}), 400
    
    # Validate YouTube URL
    if 'youtube.com' not in video_url and 'youtu.be' not in video_url:
        return jsonify({"error": "Invalid YouTube URL"}), 400
    
    try:
        # Get video info first
        video_info = downloader.get_video_info(video_url)
        if 'error' in video_info:
            return jsonify({"error": video_info['error']}), 400
        
        formats = video_info.get('formats', [])
        if not formats:
            return jsonify({"error": "No downloadable formats found"}), 400
        
        # Find selected format
        selected_format = None
        
        if quality == 'best':
            # Highest quality with both video and audio
            for fmt in formats:
                if fmt.get('hasVideo') and fmt.get('hasAudio') and fmt.get('url'):
                    selected_format = fmt
                    break
            if not selected_format:
                selected_format = formats[0] if formats else None
        else:
            # Specific quality
            for fmt in formats:
                if (fmt.get('quality') == quality and 
                    fmt.get('hasVideo') and 
                    fmt.get('hasAudio') and 
                    fmt.get('url')):
                    selected_format = fmt
                    break
        
        if not selected_format:
            available_formats = list(set([f.get('quality', 'unknown') for f in formats if f.get('hasVideo')]))
            return jsonify({
                "error": f"Format {quality} not available",
                "available_formats": available_formats
            }), 400
        
        # Get download URL
        download_url = selected_format.get('url', '')
        if not download_url:
            return jsonify({"error": "No download URL available"}), 400
        
        # Sanitize filename
        title = video_info.get('title', 'video')
        safe_title = re.sub(r'[<>:"/\\|?*]', '', title)
        file_extension = 'mp4' if 'mp4' in selected_format.get('mimeType', '') else 'webm'
        filename = f"{safe_title}_{quality}.{file_extension}"
        
        # Download to temporary file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Range': 'bytes=0-'
        }
        
        response = requests.get(download_url, headers=headers, stream=True, timeout=60)
        response.raise_for_status()
        
        # Download file
        total_size = 0
        with open(temp_file.name, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    total_size += len(chunk)
        
        return send_file(
            temp_file.name,
            as_attachment=True,
            download_name=filename,
            mimetype='video/mp4'
        )
        
    except Exception as e:
        return jsonify({"error": f"Download failed: {str(e)}"}), 500

@app.route('/info')
def video_info():
    """Get video information and available formats"""
    video_url = request.args.get('url', '')
    
    if not video_url:
        return jsonify({"error": "URL parameter is required"}), 400
    
    if 'youtube.com' not in video_url and 'youtu.be' not in video_url:
        return jsonify({"error": "Invalid YouTube URL"}), 400
    
    result = downloader.get_video_info(video_url)
    
    # Return raw result for debugging
    return jsonify(result)

@app.route('/health')
def health_check():
    """Health check endpoint for Render"""
    return jsonify({"status": "healthy", "service": "youtube-downloader"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)