from flask import Flask, render_template, request, send_file, jsonify
from yt_dlp import YoutubeDL
import os
import re
import uuid
import traceback

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024

def sanitize_filename(filename):
    return re.sub(r'[^a-zA-Z0-9_.-]', '_', filename)

def get_video_info(url):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
    }
    
    try:
        with YoutubeDL(ydl_opts) as ydl:
            # Validate URL first
            try:
                info = ydl.extract_info(url, download=False)
            except Exception as e:
                return {'error': f'Video not accessible: {str(e)}'}
            
            formats = []
            for f in info.get('formats', []):
                if f.get('filesize') or f.get('filesize_approx') or f.get('url'):
                    format_info = {
                        'format_id': f['format_id'],
                        'ext': f['ext'],
                        'resolution': f.get('format_note', 'audio'),
                        'filesize': f.get('filesize') or f.get('filesize_approx', 0),
                        'format': f['format']
                    }
                    # Filter only common formats
                    if format_info['ext'] in ['mp4', 'webm', 'm4a', 'mp3']:
                        formats.append(format_info)
            
            video_info = {
                'title': info.get('title', 'Unknown Title'),
                'duration': info.get('duration', 0),
                'thumbnail': info.get('thumbnail', ''),
                'formats': formats,
                'uploader': info.get('uploader', 'Unknown Uploader'),
                'description': info.get('description', '')[:100] + '...' if info.get('description') else ''
            }
            
            return video_info
            
    except Exception as e:
        return {'error': f'Failed to fetch video info: {str(e)}'}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_info', methods=['POST'])
def get_info():
    try:
        url = request.json.get('url', '').strip()
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        # Basic URL validation
        if 'youtube.com' not in url and 'youtu.be' not in url:
            return jsonify({'error': 'Please enter a valid YouTube URL'}), 400
        
        video_info = get_video_info(url)
        
        if 'error' in video_info:
            return jsonify({'error': video_info['error']}), 400
        
        return jsonify(video_info)
        
    except Exception as e:
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@app.route('/download', methods=['POST'])
def download():
    try:
        url = request.form.get('url', '').strip()
        format_id = request.form.get('format', '').strip()
        
        if not url or not format_id:
            return "URL and format are required", 400
        
        temp_filename = f"temp_{uuid.uuid4().hex}"
        
        ydl_opts = {
            'format': format_id,
            'outtmpl': temp_filename + '.%(ext)s',
            'quiet': False,
        }
        
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            actual_filename = ydl.prepare_filename(info)
            
            response = send_file(
                actual_filename,
                as_attachment=True,
                download_name=sanitize_filename(info['title']) + '.' + info['ext']
            )
            
            @response.call_on_close
            def cleanup():
                try:
                    if os.path.exists(actual_filename):
                        os.remove(actual_filename)
                except:
                    pass
            
            return response
            
    except Exception as e:
        return f"Download failed: {str(e)}", 500

@app.errorhandler(413)
def too_large(e):
    return "File too large", 413

@app.errorhandler(500)
def internal_error(e):
    return "Internal server error", 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)