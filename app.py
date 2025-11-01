from flask import Flask, render_template, request, send_file, jsonify
from yt_dlp import YoutubeDL
import os
import re
import uuid

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB limit

def sanitize_filename(filename):
    """ফাইলের নাম সেফ করতে"""
    return re.sub(r'[^a-zA-Z0-9_.-]', '_', filename)

def get_video_info(url):
    """ভিডিওর ইনফর্মেশন fetch করে"""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
    }
    
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            formats = []
            for f in info.get('formats', []):
                if f.get('filesize') or f.get('filesize_approx'):
                    format_info = {
                        'format_id': f['format_id'],
                        'ext': f['ext'],
                        'resolution': f.get('format_note', 'Unknown'),
                        'filesize': f.get('filesize') or f.get('filesize_approx', 0),
                        'format': f['format']
                    }
                    formats.append(format_info)
            
            video_info = {
                'title': info.get('title', 'Unknown'),
                'duration': info.get('duration', 0),
                'thumbnail': info.get('thumbnail', ''),
                'formats': formats,
                'uploader': info.get('uploader', 'Unknown')
            }
            
            return video_info
    except Exception as e:
        return None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_info', methods=['POST'])
def get_info():
    url = request.json.get('url')
    if not url:
        return jsonify({'error': 'URL is required'}), 400
    
    video_info = get_video_info(url)
    if not video_info:
        return jsonify({'error': 'Invalid URL or video not available'}), 400
    
    return jsonify(video_info)

@app.route('/download', methods=['POST'])
def download():
    url = request.form.get('url')
    format_id = request.form.get('format')
    
    if not url or not format_id:
        return "URL and format are required", 400
    
    # Temporary filename
    temp_filename = f"temp_{uuid.uuid4().hex}"
    
    ydl_opts = {
        'format': format_id,
        'outtmpl': temp_filename + '.%(ext)s',
        'quiet': True,
    }
    
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = f"{temp_filename}.{info['ext']}"
            
            # Get the actual generated filename
            actual_filename = ydl.prepare_filename(info)
            
            # Send file
            response = send_file(
                actual_filename,
                as_attachment=True,
                download_name=sanitize_filename(info['title']) + '.' + info['ext']
            )
            
            # Cleanup after sending
            @response.call_on_close
            def cleanup():
                try:
                    if os.path.exists(actual_filename):
                        os.remove(actual_filename)
                except:
                    pass
            
            return response
            
    except Exception as e:
        return f"Download error: {str(e)}", 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)