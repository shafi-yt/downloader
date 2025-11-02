from flask import Flask, request, jsonify
import os
import logging

# লগিং কনফিগারেশন
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

def send_telegram_message(chat_id, text, parse_mode='Markdown'):
    """
    Telegram-এ মেসেজ সেন্ড করার জন্য সহায়ক ফাংশন
    """
    return {
        'method': 'sendMessage',
        'chat_id': chat_id,
        'text': text,
        'parse_mode': parse_mode
    }

@app.route('/', methods=['GET', 'POST'])
def handle_request():
    try:
        # URL থেকে টোকেন নেওয়া
        token = request.args.get('token')
        
        if not token:
            return jsonify({
                'error': 'Token required',
                'solution': 'Add ?token=YOUR_BOT_TOKEN to URL'
            }), 400

        # GET request হ্যান্ডেল
        if request.method == 'GET':
            return jsonify({
                'status': 'Bot is running',
                'token_received': True
            })

        # POST request হ্যান্ডেল
        if request.method == 'POST':
            update = request.get_json()
            
            if not update:
                return jsonify({'error': 'Invalid JSON data'}), 400
            
            logger.info(f"Update received: {update}")
            
            # মেসেজ ডেটা এক্সট্র্যাক্ট
            chat_id = None
            message_text = ''
            user_info = {}
            
            if 'message' in update:
                chat_id = update['message']['chat']['id']
                message_text = update['message'].get('text', '')
                user_info = update['message'].get('from', {})
            else:
                return jsonify({'ok': True})

            if not chat_id:
                return jsonify({'error': 'Chat ID not found'}), 400

            # শুধুমাত্র /start কমান্ড হ্যান্ডেল
            if message_text.startswith('/start'):
                # ইউজারের তথ্য সংগ্রহ
                first_name = user_info.get('first_name', 'অজানা')
                last_name = user_info.get('last_name', '')
                username = user_info.get('username', 'অজানা')
                user_id = user_info.get('id', 'অজানা')
                language_code = user_info.get('language_code', 'অজানা')
                
                full_name = first_name
                if last_name:
                    full_name += f" {last_name}"
                
                profile_text = f"""
🤖 *আপনার প্রোফাইল তথ্য*

👤 *ব্যক্তিগত তথ্য:*
• *পূর্ণ নাম:* {full_name}
• *ইউজারনেম:* @{username}
• *ইউজার আইডি:* `{user_id}`
• *ভাষা:* {language_code}

💬 *চ্যাট তথ্য:*
• *চ্যাট আইডি:* `{chat_id}`

📞 *যোগাযোগ:* 
আপনার ইউজারনেম @{username} এর মাধ্যমে যোগাযোগ করা যাবে।
                """
                
                return jsonify(send_telegram_message(
                    chat_id=chat_id,
                    text=profile_text
                ))

            # অন্য সব মেসেজের জন্য
            else:
                return jsonify(send_telegram_message(
                    chat_id=chat_id,
                    text="আপনার প্রোফাইল দেখতে /start কমান্ড ব্যবহার করুন"
                ))

    except Exception as e:
        logger.error(f'Error: {e}')
        return jsonify({'error': 'Processing failed'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)