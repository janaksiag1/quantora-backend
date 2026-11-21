import pytest
from app.voice import validate_audio, MAX_AUDIO_BYTES

@pytest.mark.parametrize('mime,data', [('audio/webm',b'\x1aE\xdf\xa3'+b'x'*200),('audio/ogg',b'OggS'+b'x'*200),('audio/wav',b'RIFF'+b'0000WAVE'+b'x'*200),('audio/mp4',b'0000ftyp'+b'x'*200)])
def test_valid_audio_signatures(mime,data):
    assert validate_audio(data,mime)[0] == mime

@pytest.mark.parametrize('mime,data',[('audio/wav',b'RIFF'+b'x'*200),('audio/webm',b'<script>'+b'x'*200),('text/html',b'x'*200),('audio/ogg',b'OggS'),('audio/ogg',b'OggS'+b'x'*MAX_AUDIO_BYTES)])
def test_invalid_or_oversized_audio_rejected(mime,data):
    with pytest.raises(ValueError): validate_audio(data,mime)
