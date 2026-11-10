from flask import Blueprint, request, jsonify
from app_pkg.services.ai_service import chat_with_promaster

bp = Blueprint('ai', __name__)

@bp.route('/api/ai/chat', methods=['POST'])
def chat():  # login is enforced by the global before_request hook (app_pkg/auth.py)
    try:
        data = request.get_json() or {}
        message = data.get('message')
        history = data.get('history', [])
        
        if not message:
            return jsonify({'error': 'Message required'}), 400
            
        response_text = chat_with_promaster(message, history)
        return jsonify({'response': response_text})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
