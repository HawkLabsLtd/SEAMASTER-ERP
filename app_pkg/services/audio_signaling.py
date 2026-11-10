"""
Real-Time WebRTC Audio Signaling Service for Meetings
Provides thread-safe in-memory room state, participant presence, and signal exchange.
"""
import time
import threading
from typing import Dict, List, Any, Optional

_lock = threading.RLock()

# Data structure:
# _rooms = {
#     meeting_id: {
#         'participants': {
#             user_id: {
#                 'user_id': int,
#                 'user_name': str,
#                 'role': str,
#                 'is_muted': bool,
#                 'is_speaking': bool,
#                 'joined_at': float,
#                 'last_seen': float,
#             }
#         },
#         'signals': {
#             user_id: [
#                 {
#                     'from_user_id': int,
#                     'from_user_name': str,
#                     'signal_data': Any,
#                     'timestamp': float
#                 }
#             ]
#         }
#     }
# }
_rooms: Dict[int, Dict[str, Any]] = {}

STALE_TIMEOUT_SECONDS = 15.0  # Auto-disconnect if no heartbeat received for 15 seconds


def _get_or_create_room(meeting_id: int) -> Dict[str, Any]:
    if meeting_id not in _rooms:
        _rooms[meeting_id] = {
            'participants': {},
            'signals': {}
        }
    return _rooms[meeting_id]


def cleanup_stale_participants(meeting_id: int) -> List[int]:
    """Remove participants who have not polled within STALE_TIMEOUT_SECONDS."""
    removed_ids = []
    now = time.time()
    with _lock:
        if meeting_id not in _rooms:
            return []
        room = _rooms[meeting_id]
        participants = room['participants']
        for uid, pdata in list(participants.items()):
            if now - pdata.get('last_seen', 0) > STALE_TIMEOUT_SECONDS:
                removed_ids.append(uid)
                participants.pop(uid, None)
                room['signals'].pop(uid, None)
        # If room is completely empty, clean it up
        if not participants:
            _rooms.pop(meeting_id, None)
    return removed_ids


def join_room(meeting_id: int, user_id: int, user_name: str, role: str = 'member') -> Dict[str, Any]:
    """Register a user in the meeting audio room."""
    with _lock:
        cleanup_stale_participants(meeting_id)
        room = _get_or_create_room(meeting_id)
        now = time.time()
        
        participant = {
            'user_id': user_id,
            'user_name': user_name,
            'role': role,
            'is_muted': False,
            'is_speaking': False,
            'joined_at': now,
            'last_seen': now
        }
        room['participants'][user_id] = participant
        if user_id not in room['signals']:
            room['signals'][user_id] = []
            
        # Return all OTHER active participants in the room
        other_participants = [
            p for uid, p in room['participants'].items() if uid != user_id
        ]
        return {
            'status': 'joined',
            'user_id': user_id,
            'participant': participant,
            'other_participants': other_participants,
            'all_participants': list(room['participants'].values())
        }


def leave_room(meeting_id: int, user_id: int) -> bool:
    """Remove a user from the meeting audio room."""
    with _lock:
        if meeting_id not in _rooms:
            return False
        room = _rooms[meeting_id]
        room['participants'].pop(user_id, None)
        room['signals'].pop(user_id, None)
        if not room['participants']:
            _rooms.pop(meeting_id, None)
        return True


def send_signal(meeting_id: int, from_user_id: int, from_user_name: str, to_user_id: Optional[int], signal_data: Any) -> bool:
    """Send a WebRTC signal (Offer, Answer, ICE Candidate) to a target user or broadcast."""
    with _lock:
        if meeting_id not in _rooms:
            return False
        room = _rooms[meeting_id]
        now = time.time()
        
        # Update sender heartbeat
        if from_user_id in room['participants']:
            room['participants'][from_user_id]['last_seen'] = now
            
        signal_item = {
            'from_user_id': from_user_id,
            'from_user_name': from_user_name,
            'signal_data': signal_data,
            'timestamp': now
        }
        
        if to_user_id is not None:
            # Targeted signal
            if to_user_id in room['signals']:
                room['signals'][to_user_id].append(signal_item)
                return True
            elif to_user_id in room['participants']:
                room['signals'][to_user_id] = [signal_item]
                return True
            return False
        else:
            # Broadcast to all other participants
            for uid in room['participants']:
                if uid != from_user_id:
                    if uid not in room['signals']:
                        room['signals'][uid] = []
                    room['signals'][uid].append(signal_item)
            return True


def poll_signals(meeting_id: int, user_id: int) -> Dict[str, Any]:
    """Retrieve pending signals for a user and update heartbeat."""
    with _lock:
        cleanup_stale_participants(meeting_id)
        if meeting_id not in _rooms:
            return {
                'status': 'not_in_room',
                'signals': [],
                'participants': []
            }
        room = _rooms[meeting_id]
        now = time.time()
        
        if user_id not in room['participants']:
            return {
                'status': 'not_in_room',
                'signals': [],
                'participants': list(room['participants'].values())
            }
            
        # Update heartbeat
        room['participants'][user_id]['last_seen'] = now
        
        # Pop pending signals
        signals = room['signals'].pop(user_id, [])
        room['signals'][user_id] = []
        
        return {
            'status': 'ok',
            'signals': signals,
            'participants': list(room['participants'].values())
        }


def update_status(meeting_id: int, user_id: int, is_muted: Optional[bool] = None, is_speaking: Optional[bool] = None) -> Optional[Dict[str, Any]]:
    """Update participant mute and speaking indicators."""
    with _lock:
        if meeting_id not in _rooms or user_id not in _rooms[meeting_id]['participants']:
            return None
        participant = _rooms[meeting_id]['participants'][user_id]
        participant['last_seen'] = time.time()
        if is_muted is not None:
            participant['is_muted'] = bool(is_muted)
        if is_speaking is not None:
            participant['is_speaking'] = bool(is_speaking)
        return participant


def get_room_participants(meeting_id: int) -> List[Dict[str, Any]]:
    """Return all active participants in a meeting room."""
    with _lock:
        cleanup_stale_participants(meeting_id)
        if meeting_id not in _rooms:
            return []
        return list(_rooms[meeting_id]['participants'].values())
