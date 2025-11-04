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
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        }
    
    def get_video_info(self, video_url):
        """YouTube video information extract করা"""
        try:
            response = requests.get(video_url, headers=self.headers, timeout=30)
            html = response.text
            
            # Multiple patterns for player response
            patterns = [
                r'var ytInitialPlayerResponse\s*=\s*({.*?});',
                r'window\["ytInitialPlayerResponse"\]\s*=\s*({.*?});',
                r'ytInitialPlayerResponse\s*=\s*({.*?});'
            ]
            
            player_response = None
            for pattern in patterns:
                match = re.search(pattern, html)
                if match:
                    try:
                        player_response = json.loads(match.group(1))
                        break
                    except:
                        continue
            
            if not player_response:
                return {"error": "Video information not found"}
            
            video_details = player_response.get('videoDetails', {})
            streaming_data = player_response.get('streamingData', {})
            
            return {
                'title': video_details.get('title', 'video'),
                'duration': video_details.get('lengthSeconds', '0'),
                'author': video_details.get('author', 'Unknown'),
                'formats': self._parse_formats(streaming_data)
            }
            
        except Exception as e:
            return {"error": f"Failed to get video info: {str(e)}"}
    
    def _parse_formats(self, streaming_data):
        """Available formats parse করা"""
        formats = []
        
        # Combined formats (video + audio)
        combined_formats = streaming_data.get('formats', [])
        # Adaptive formats (video/audio separate)
        adaptive_formats = streaming_data.get('adaptiveFormats', [])
        
        all_formats = combined_formats + adaptive_formats
        
        for fmt in all_formats:
            format_info = self._extract_format_info(fmt)
            if format_info:
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
    
    def download_video(self, video_url, quality='best'):
        """Video download করা"""
        try:
            # Get video info
            video_info = self.get_video_info(video_url)
            if 'error' in video_info:
                return {"error": video_info['error']}
            
            # Find selected format
            selected_format = None
            formats = video_info.get('formats', [])
            
            if quality == 'best':
                # Highest quality with both video and audio
                for fmt in formats:
                    if fmt.get('hasVideo') and fmt.get('hasAudio'):
                        selected_format = fmt
                        break
                if not selected_format:
                    selected_format = formats[0] if formats else None
            else:
                # Specific quality
                for fmt in formats:
                    if fmt.get('quality') == quality and fmt.get('hasVideo') and fmt.get('hasAudio'):
                        selected_format = fmt
                        break
            
            if not selected_format:
                return {"error": f"No {quality} format found"}
            
            # Get download URL
            download_url = selected_format.get('url', '')
            if not download_url:
                return {"error": "No download URL available"}
            
            # Sanitize filename
            title = video_info['title']
            safe_title = re.sub(r'[<>:"/\\|?*]', '', title)
            file_extension = 'mp4' if 'mp4' in selected_format.get('mimeType', '') else 'webm'
            filename = f"{safe_title}_{quality}.{file_extension}"
            
            # Download to temporary file
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
            
            response = requests.get(download_url, headers=self.headers, stream=True, timeout=60)
            response.raise_for_status()
            
            # Download file
            with open(temp_file.name, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            return {
                "status": "success",
                "filename": filename,
                "filepath": temp_file.name,
                "title": title,
                'quality': quality,
                "size": os.path.getsize(temp_file.name)
            }
            
        except Exception as e:
            return {"error": f"Download failed: {str(e)}"}

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
        </body>
    </html>
    """

@app.route('/download')
def download():
    """Main download endpoint - Render + GitHub compatible"""
    video_url = request.args.get('url', '')
    quality = request.args.get('format', 'best')
    
    if not video_url:
        return jsonify({"error": "URL parameter is required"}), 400
    
    # Validate YouTube URL
    if 'youtube.com' not in video_url and 'youtu.be' not in video_url:
        return jsonify({"error": "Invalid YouTube URL"}), 400
    
    # Download video
    result = downloader.download_video(video_url, quality)
    
    if 'error' in result:
        return jsonify({"error": result['error']}), 400
    
    # Send file as response
    try:
        return send_file(
            result['filepath'],
            as_attachment=True,
            download_name=result['filename'],
            mimetype='video/mp4'
        )
    except Exception as e:
        return jsonify({"error": f"File send failed: {str(e)}"}), 500
    finally:
        # Clean up temporary file after sending
        try:
            if os.path.exists(result['filepath']):
                os.unlink(result['filepath'])
        except:
            pass

@app.route('/info')
def video_info():
    """Get video information and available formats"""
    video_url = request.args.get('url', '')
    
    if not video_url:
        return jsonify({"error": "URL parameter is required"}), 400
    
    if 'youtube.com' not in video_url and 'youtu.be' not in video_url:
        return jsonify({"error": "Invalid YouTube URL"}), 400
    
    result = downloader.get_video_info(video_url)
    
    if 'error' in result:
        return jsonify({"error": result['error']}), 400
    
    # Extract available qualities
    formats = result.get('formats', [])
    available_qualities = []
    
    for fmt in formats:
        if fmt.get('hasVideo') and fmt.get('hasAudio') and fmt.get('quality'):
            available_qualities.append(fmt['quality'])
    
    # Remove duplicates and sort
    available_qualities = sorted(set(available_qualities), 
                                key=lambda x: int(x.replace('p', '')) if x.replace('p', '').isdigit() else 0)
    
    return jsonify({
        "title": result.get('title'),
        "author": result.get('author'),
        "duration": result.get('duration'),
        "available_qualities": available_qualities,
        "formats_count": len(formats)
    })

@app.route('/health')
def health_check():
    """Health check endpoint for Render"""
    return jsonify({"status": "healthy", "service": "youtube-downloader"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)