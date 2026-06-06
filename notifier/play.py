"""Gemini TTS + afplay helper.

GEMINI_API_KEY 環境変数 必須。
voice デフォルト Charon (低め男声、 シリアス系)。
style_prefix で 「in a calm voice」 「urgently」 等のニュアンス制御。
"""
import os
import sys
import json
import base64
import struct
import subprocess
import urllib.request

URL_TMPL = ('https://generativelanguage.googleapis.com/v1beta/models/'
            'gemini-2.5-flash-preview-tts:generateContent?key={key}')


def speak(text, voice='Charon', style_prefix=None, save_to=None):
    """text を音声化して afplay 再生。 save_to 指定で wav保存も。"""
    key = os.environ.get('GEMINI_API_KEY')
    if not key:
        raise RuntimeError('GEMINI_API_KEY env var missing')

    prompt_text = f'{style_prefix}: "{text}"' if style_prefix else text
    data = {
        'contents': [{'parts': [{'text': prompt_text}]}],
        'generationConfig': {
            'responseModalities': ['AUDIO'],
            'speechConfig': {
                'voiceConfig': {'prebuiltVoiceConfig': {'voiceName': voice}}
            }
        }
    }
    req = urllib.request.Request(
        URL_TMPL.format(key=key),
        data=json.dumps(data).encode(),
        headers={'Content-Type': 'application/json'}
    )
    r = json.loads(urllib.request.urlopen(req, timeout=60).read())
    parts = r['candidates'][0]['content']['parts']
    pcm = base64.b64decode(parts[0]['inlineData']['data'])
    mime = parts[0]['inlineData']['mimeType']
    rate = int(mime.split('rate=')[1].split(';')[0]) if 'rate=' in mime else 24000

    ch, bits = 1, 16
    byte_rate = rate * ch * bits // 8
    block_align = ch * bits // 8
    data_size = len(pcm)
    header = (b'RIFF' + struct.pack('<I', 36 + data_size) + b'WAVE'
              + b'fmt ' + struct.pack('<IHHIIHH', 16, 1, ch, rate, byte_rate, block_align, bits)
              + b'data' + struct.pack('<I', data_size))
    wav_path = save_to or '/tmp/notifier_tts.wav'
    with open(wav_path, 'wb') as f:
        f.write(header + pcm)
    subprocess.run(['afplay', wav_path], check=True)
    return wav_path


if __name__ == '__main__':
    text = sys.argv[1] if len(sys.argv) > 1 else '通知システムテスト完了'
    speak(text)
