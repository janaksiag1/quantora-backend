"""Bounded audio transcription. Recordings and transcripts are never logged or stored here."""
import httpx
from .config import settings

MAX_AUDIO_BYTES = 3 * 1024 * 1024
FORMATS = {'audio/webm': ('webm', b'\x1aE\xdf\xa3'), 'audio/ogg': ('ogg', b'OggS'), 'audio/wav': ('wav', b'RIFF'), 'audio/mp4': ('m4a', None), 'audio/mpeg': ('mp3', None)}

def validate_audio(data: bytes, content_type: str):
    mime = content_type.split(';')[0].lower().strip()
    if mime not in FORMATS or len(data) < 128 or len(data) > MAX_AUDIO_BYTES:
        raise ValueError('Use a short WebM, MP4, WAV, Ogg or MP3 recording under 3 MB.')
    extension, signature = FORMATS[mime]
    valid = data.startswith(signature) if signature else (data[4:8] == b'ftyp' if mime == 'audio/mp4' else data.startswith(b'ID3') or data[:2] in (b'\xff\xfb', b'\xff\xf3', b'\xff\xf2'))
    if mime == 'audio/wav': valid = valid and data[8:12] == b'WAVE'
    if not valid: raise ValueError('The recording format could not be read. Try recording again.')
    return mime, extension

async def transcribe_audio(data: bytes, content_type: str, language: str = 'auto'):
    mime, extension = validate_audio(data, content_type)
    key = settings.groq_api_key.get_secret_value()
    if not key: raise RuntimeError('Speech transcription is not configured. Typed chat remains available.')
    fields = {'model': 'whisper-large-v3-turbo', 'response_format': 'verbose_json', 'temperature': '0'}
    locale = language.split('-')[0].lower()
    if locale in ('en','hi','mr','bn','ta','te','gu','kn','ml','pa'): fields['language'] = locale
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post('https://api.groq.com/openai/v1/audio/transcriptions', headers={'Authorization': 'Bearer ' + key}, data=fields, files={'file': ('question.' + extension, data, mime)})
    if not response.is_success:
        raise RuntimeError('Speech service is busy or unavailable. Try a shorter recording, or type your question.')
    result = response.json()
    segments = result.get('segments') or []
    text = result.get('text')
    if not isinstance(text, str) or len(text.strip()) < 2 or (segments and all(isinstance(segment.get('no_speech_prob'), (int,float)) and segment['no_speech_prob'] > .8 for segment in segments)):
        raise ValueError('No clear speech was detected. Please speak closer to the microphone and try again.')
    return {'text': text.strip()[:4000], 'language': str(result.get('language') or locale)[:30]}
