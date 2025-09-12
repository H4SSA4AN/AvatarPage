import os
import asyncio
import base64
import json
from datetime import datetime
import logging
import aiohttp
from aiohttp import web, ClientSession
from openai import OpenAI
from dotenv import load_dotenv


# Load environment variables from .env (if present) before reading any env vars
load_dotenv()


# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Suppress noisy access logs for high-frequency endpoints
class _AccessPathFilter(logging.Filter):
    def __init__(self, suppressed_paths):
        super().__init__()
        self._suppressed_paths = tuple(suppressed_paths)

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            return True
        return not any(path in message for path in self._suppressed_paths)

# Hide access logs for /get_frame_buffer only (keep other endpoints visible)
logging.getLogger('aiohttp.access').addFilter(
    _AccessPathFilter(['/get_frame_buffer'])
)


# Storage
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Config
MAX_AUDIO_SIZE = 100 * 1024 * 1024  # 100MB
MUSETALK_URL = os.getenv('MUSETALK_URL', 'http://localhost:8085')

# State
frame_buffer = []
processing_complete = False
start_signal_received = False

# CORS middleware
@web.middleware
async def cors_middleware(request, handler):
    # Handle preflight
    if request.method == 'OPTIONS':
        resp = web.Response(status=200)
    else:
        resp = await handler(request)
    origin = request.headers.get('Origin', '*')
    resp.headers['Access-Control-Allow-Origin'] = origin
    resp.headers['Vary'] = 'Origin'
    resp.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    resp.headers['Access-Control-Allow-Credentials'] = 'false'
    return resp


async def index_handler(request: web.Request) -> web.Response:
    try:
        with open(os.path.join('templates', 'index.html'), 'r', encoding='utf-8') as f:
            html = f.read()
        return web.Response(text=html, content_type='text/html')
    except FileNotFoundError:
        return web.Response(text='index.html not found', status=404)


async def save_audio_handler(request: web.Request) -> web.Response:
    try:
        if request.content_length and request.content_length > MAX_AUDIO_SIZE:
            return web.json_response({'error': 'Request too large'}, status=413)

        data = await request.json()
        audio_data = data.get('audio_data')
        fps = str(data.get('fps', '25'))
        batch_size = str(data.get('batch_size', '20'))
        musetalk_base_url = MUSETALK_URL
        mode = (data.get('mode') or 'pipeline').strip().lower()

        if not audio_data:
            return web.json_response({'error': 'No audio data received'}, status=400)

        if audio_data.startswith('data:audio/wav;base64,'):
            audio_data = audio_data.split(',', 1)[1]

        try:
            audio_bytes = base64.b64decode(audio_data)
        except Exception as e:
            return web.json_response({'error': f'Invalid audio data: {e}'}, status=400)

        if len(audio_bytes) > MAX_AUDIO_SIZE:
            return web.json_response({'error': 'Audio file too large'}, status=413)

        filepath = os.path.join(UPLOAD_FOLDER, 'input.wav')
        with open(filepath, 'wb') as f:
            f.write(audio_bytes)
        saved_at = datetime.now().isoformat()

        # === Mode selection ===
        openai_api_key = os.getenv('OPENAI_API_KEY')
        if not openai_api_key:
            return web.json_response({'error': 'OPENAI_API_KEY not set on server'}, status=500)
        client = OpenAI(api_key=openai_api_key)

        answer_mp3_path = os.path.join(UPLOAD_FOLDER, 'answer.mp3')
        transcript_text = ''
        answer_text = ''
        answer_filename = 'answer.mp3'
        answer_content_type = 'audio/mpeg'

        if mode == 'pipeline':
            def _transcribe(path: str) -> str:
                with open(path, 'rb') as af:
                    resp = client.audio.transcriptions.create(
                        model=os.getenv('TRANSCRIBE_MODEL', 'whisper-1'),
                        file=af,
                    )
                return getattr(resp, 'text', None) or str(resp)

            def _chat(question_text: str) -> str:
                resp = client.chat.completions.create(
                    model=os.getenv('CHAT_MODEL', 'gpt-4o-mini'),
                    messages=[
                        {"role": "system", "content": os.getenv('SYSTEM_PROMPT', 'You are a concise, helpful assistant.')},
                        {"role": "user", "content": question_text},
                    ],
                    temperature=0.7,
                )
                return resp.choices[0].message.content

            def _tts_to_mp3(text: str, out_path: str) -> None:
                voice = os.getenv('TTS_VOICE', 'alloy')
                model = os.getenv('TTS_MODEL', 'tts-1')
                with client.audio.speech.with_streaming_response.create(
                    model=model,
                    voice=voice,
                    input=text,
                ) as resp:
                    resp.stream_to_file(out_path)

            transcript_text = await asyncio.to_thread(_transcribe, filepath)
            answer_text = await asyncio.to_thread(_chat, transcript_text)
            await asyncio.to_thread(_tts_to_mp3, answer_text, answer_mp3_path)
            answer_saved_at = datetime.now().isoformat()
            answer_filename = 'answer.mp3'
            answer_content_type = 'audio/mpeg'
        elif mode == 'realtime':
            # realtime: use one-shot audio->audio to get direct answer audio; also request a brief text summary
            # Note: using Responses API compatible call via python SDK
            # Attach input audio and request audio output
            try:
                from openai import OpenAI as _Client
                _c = client
                with open(filepath, 'rb') as af:
                    audio_bytes = af.read()
                # Build input as base64 data URL for audio
                b64 = base64.b64encode(audio_bytes).decode('ascii')
                data_url = f"data:audio/wav;base64,{b64}"
                # Ask the model to produce audio (mp3) and a short text answer
                result = _c.responses.create(
                    model=os.getenv('REALTIME_MODEL', 'gpt-4o-mini-tts'),
                    input=[
                        {"role": "user", "content": [
                            {"type": "input_text", "text": os.getenv('SYSTEM_PROMPT', 'You are a concise, helpful assistant. Please respond to the user audio.')},
                            {"type": "input_audio", "audio": {"data": data_url}},
                        ]}
                    ],
                    modalities=["text", "audio"],
                    audio={"voice": os.getenv('TTS_VOICE', 'alloy'), "format": "mp3"}
                )
                # Extract audio and text from response
                audio_parts = []
                text_parts = []
                for out in getattr(result, 'output', []) or []:
                    if getattr(out, 'type', '') == 'output_audio':
                        # base64-encoded audio
                        enc = getattr(out, 'audio', {}).get('data') if hasattr(out, 'audio') else None
                        if enc:
                            audio_parts.append(enc)
                    elif getattr(out, 'type', '') == 'output_text':
                        text_parts.append(getattr(out, 'content', ''))
                if audio_parts:
                    mp3_bytes = base64.b64decode(''.join(audio_parts))
                    with open(answer_mp3_path, 'wb') as outf:
                        outf.write(mp3_bytes)
                    answer_saved_at = datetime.now().isoformat()
                else:
                    answer_saved_at = datetime.now().isoformat()
                answer_text = ' '.join([t for t in text_parts if t])
                transcript_text = ''
                answer_filename = 'answer.mp3'
                answer_content_type = 'audio/mpeg'
            except Exception as e:
                logger.exception('realtime mode failed; falling back to pipeline')
                # fallback to pipeline if realtime not available
                def _transcribe(path: str) -> str:
                    with open(path, 'rb') as af:
                        resp = client.audio.transcriptions.create(
                            model=os.getenv('TRANSCRIBE_MODEL', 'whisper-1'),
                            file=af,
                        )
                    return getattr(resp, 'text', None) or str(resp)
                def _chat(question_text: str) -> str:
                    resp = client.chat.completions.create(
                        model=os.getenv('CHAT_MODEL', 'gpt-4o-mini'),
                        messages=[
                            {"role": "system", "content": os.getenv('SYSTEM_PROMPT', 'You are a concise, helpful assistant.')},
                            {"role": "user", "content": question_text},
                        ],
                        temperature=0.7,
                    )
                    return resp.choices[0].message.content
                def _tts_to_mp3(text: str, out_path: str) -> None:
                    voice = os.getenv('TTS_VOICE', 'alloy')
                    model = os.getenv('TTS_MODEL', 'tts-1')
                    with client.audio.speech.with_streaming_response.create(
                        model=model,
                        voice=voice,
                        input=text,
                    ) as resp:
                        resp.stream_to_file(out_path)
                transcript_text = await asyncio.to_thread(_transcribe, filepath)
                answer_text = await asyncio.to_thread(_chat, transcript_text)
                await asyncio.to_thread(_tts_to_mp3, answer_text, answer_mp3_path)
                answer_saved_at = datetime.now().isoformat()
                answer_filename = 'answer.mp3'
                answer_content_type = 'audio/mpeg'
        elif mode == 'user_audio':
            # Convert the recorded WAV to MP3 using ffmpeg if available; otherwise fall back to WAV
            import subprocess
            ffmpeg_bin = os.getenv('FFMPEG_PATH', 'ffmpeg')
            try:
                # Ensure any existing file is removed
                try:
                    os.remove(answer_mp3_path)
                except FileNotFoundError:
                    pass
                # Run ffmpeg conversion
                cmd = [ffmpeg_bin, '-y', '-i', filepath, '-codec:a', 'libmp3lame', '-q:a', '2', answer_mp3_path]
                result = await asyncio.to_thread(lambda: subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
                if result.returncode == 0 and os.path.exists(answer_mp3_path):
                    answer_saved_at = datetime.now().isoformat()
                    answer_filename = 'answer.mp3'
                    answer_content_type = 'audio/mpeg'
                    logger.info('User audio converted to MP3 via ffmpeg')
                else:
                    raise RuntimeError(f"ffmpeg failed: rc={result.returncode}, stderr={result.stderr[-400:]}" )
            except Exception as conv_err:
                logger.warning(f'FFmpeg conversion failed, sending WAV instead: {conv_err}')
                # Fall back to WAV: use input.wav as the audio to send
                answer_mp3_path = filepath
                answer_filename = 'input.wav'
                answer_content_type = 'audio/wav'
                answer_saved_at = datetime.now().isoformat()
            # No transcript or assistant answer for user_audio mode
            transcript_text = ''
            answer_text = ''
        else:
            return web.json_response({'error': f"Unknown mode '{mode}'"}, status=400)

        # Normalize MuseTalk base URL and build process endpoint
        musetalk_base_url = str(musetalk_base_url).strip()
        if musetalk_base_url.endswith('/'):
            musetalk_base_url = musetalk_base_url[:-1]
        if not (musetalk_base_url.startswith('http://') or musetalk_base_url.startswith('https://')):
            musetalk_base_url = 'http://' + musetalk_base_url
        musetalk_url = musetalk_base_url + '/process'

        # Build a public callback URL for MuseTalk to POST frames back to this app
        xf_proto = request.headers.get('X-Forwarded-Proto')
        xf_host = request.headers.get('X-Forwarded-Host')
        scheme = xf_proto or request.scheme
        host = xf_host or request.host
        stream_url = f"{scheme}://{host}/stream_frames"

        form = aiohttp.FormData()
        # Send audio to MuseTalk
        form.add_field('audio', open(answer_mp3_path, 'rb'), filename=answer_filename, content_type=answer_content_type)
        form.add_field('stream_url', stream_url)
        form.add_field('fps', fps)
        form.add_field('batch_size', batch_size)
        form.add_field('bbox_shift', '0')

        timeout = aiohttp.ClientTimeout(total=120)
        async with ClientSession(timeout=timeout) as session:
            async with session.post(musetalk_url, data=form) as resp:
                text = await resp.text()
                return web.json_response({
                    'success': resp.status == 200,
                    'message': 'Answer audio forwarded to MuseTalk',
                    'musetalk_response': text,
                    'stream_url': stream_url,
                    'saved_at': saved_at,
                    'transcript': transcript_text,
                    'answer': answer_text,
                    'answer_audio_path': answer_mp3_path,
                    'answer_saved_at': answer_saved_at,
                    'answer_audio_url': f"{scheme}://{host}/uploads/{answer_filename}",
                }, status=200 if resp.status == 200 else 502)

    except Exception as e:
        logger.exception('save_audio_handler error')
        return web.json_response({'error': str(e)}, status=500)


async def stream_frames_handler(request: web.Request) -> web.Response:
    """Persistent NDJSON (one JSON object per line) receiver from MuseTalk."""
    global frame_buffer, processing_complete, start_signal_received
    logger.info('=== stream_frames started ===')

    buf = b''
    total_lines = 0
    total_frames_received = 0

    def process_line(line: str):
        nonlocal total_lines, total_frames_received
        total_lines += 1
        line = line.strip()
        if not line:
            return
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            logger.warning('Non-JSON line received; ignoring')
            return

        status = msg.get('status')
        if status == 'start':
            start_signal_received = True
            logger.info('Start signal received')
            return
        if status == 'finished':
            processing_complete = True
            logger.info('Finished signal received')
            return

        frames = msg.get('frames', [])
        if frames:
            added = 0
            last_num = None
            for fr in frames:
                b64 = fr.get('frame_data')
                if not b64:
                    continue
                last_num = fr.get('frame_number', 0)
                frame_buffer.append({
                    'frame_number': last_num,
                    'frame_data': b64,
                    'timestamp': datetime.now().isoformat(),
                })
                added += 1
            total_frames_received += added
            logger.info(f"Received {added} frames (last #{last_num}); buffer size={len(frame_buffer)}; total_frames_received={total_frames_received}")

    try:
        async for chunk in request.content.iter_chunked(65536):
            if not chunk:
                continue
            buf += chunk
            while True:
                idx = buf.find(b"\n")
                if idx == -1:
                    break
                line_bytes = buf[:idx]
                buf = buf[idx+1:]
                process_line(line_bytes.decode('utf-8', errors='ignore'))

        if buf:
            process_line(buf.decode('utf-8', errors='ignore'))

        logger.info(f"=== stream_frames completed: lines={total_lines}, total_frames_received={total_frames_received}, buffer_size={len(frame_buffer)} ===")
        return web.json_response({'ok': True, 'lines': total_lines, 'frames': total_frames_received})
    except Exception as e:
        logger.exception('stream_frames error')
        return web.json_response({'error': str(e)}, status=500)
    finally:
        logger.info('=== stream_frames ended ===')


async def clear_buffer_handler(request: web.Request) -> web.Response:
    global frame_buffer, processing_complete, start_signal_received
    frame_buffer.clear()
    processing_complete = False
    start_signal_received = False
    return web.json_response({'success': True})


async def options_handler(request: web.Request) -> web.Response:
    return web.Response(status=200)


async def config_handler(request: web.Request) -> web.Response:
    try:
        return web.json_response({
            'musetalk_url': MUSETALK_URL,
        })
    except Exception as e:
        logger.exception('config_handler error')
        return web.json_response({'error': str(e)}, status=500)

async def probe_musetalk_handler(request: web.Request) -> web.Response:
    try:
        musetalk_base_url = MUSETALK_URL

        musetalk_base_url = str(musetalk_base_url).strip()
        if musetalk_base_url.endswith('/'):
            musetalk_base_url = musetalk_base_url[:-1]
        if not (musetalk_base_url.startswith('http://') or musetalk_base_url.startswith('https://')):
            musetalk_base_url = 'http://' + musetalk_base_url

        # Build health URL and include our public base for stream registration
        xf_proto = request.headers.get('X-Forwarded-Proto')
        xf_host = request.headers.get('X-Forwarded-Host')
        scheme = xf_proto or request.scheme
        host = xf_host or request.host
        public_base = f"{scheme}://{host}"
        url = musetalk_base_url + '/health' + f"?stream_base={public_base}"

        # Diagnostics: resolve host and attempt a quick TCP connect
        import socket
        from urllib.parse import urlparse
        parsed = urlparse(url)
        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == 'https' else 80)
        resolved_ips = []
        try:
            infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
            for family, _, _, _, sockaddr in infos:
                ip = sockaddr[0]
                if ip not in resolved_ips:
                    resolved_ips.append(ip)
        except Exception as e:
            logger.warning(f'DNS resolution failed for {host}: {e}')

        tcp_ok = False
        tcp_error = None
        try:
            # Prefer IPv4 for simplicity
            with socket.create_connection((host, port), timeout=2) as s:
                tcp_ok = True
        except Exception as e:
            tcp_error = str(e)

        # Attempt HTTP GET with tighter connect/read timeouts and IPv4 preference
        timeout = aiohttp.ClientTimeout(total=5, connect=2, sock_connect=2, sock_read=3)
        connector = aiohttp.TCPConnector(ssl=False, family=socket.AF_INET, force_close=True)
        async with ClientSession(timeout=timeout, connector=connector) as session:
            try:
                async with session.get(url, headers={'User-Agent': 'AvatarPageProbe/1.0'}) as resp:
                    ct = resp.headers.get('Content-Type', '')
                    try:
                        body = await resp.json()
                    except Exception:
                        body = await resp.text()
                    return web.json_response({
                        'success': resp.status == 200,
                        'status': resp.status,
                        'url': url,
                        'resolved_ips': resolved_ips,
                        'tcp_connect_ok': tcp_ok,
                        'tcp_error': tcp_error,
                        'content_type': ct,
                        'body': body,
                    }, status=200 if resp.status == 200 else 502)
            except Exception as e:
                logger.exception('HTTP probe to MuseTalk failed')
                return web.json_response({
                    'success': False,
                    'status': None,
                    'url': url,
                    'resolved_ips': resolved_ips,
                    'tcp_connect_ok': tcp_ok,
                    'tcp_error': tcp_error,
                    'error': str(e),
                }, status=504)
    except Exception as e:
        logger.exception('probe_musetalk error')
        return web.json_response({'success': False, 'error': str(e)}, status=500)


async def get_frame_buffer_handler(request: web.Request) -> web.Response:
    """Return frames; supports incremental fetch via ?from_index=N"""
    try:
        from_index_q = request.rel_url.query.get('from_index')
        if from_index_q is not None:
            try:
                start = max(0, int(from_index_q))
            except ValueError:
                start = 0
            frames_slice = frame_buffer[start:]
            next_index = len(frame_buffer)
        else:
            frames_slice = frame_buffer
            next_index = len(frame_buffer)
        return web.json_response({
            'frames': frames_slice,
            'buffer_size': len(frame_buffer),
            'next_index': next_index,
            'processing_complete': processing_complete,
            'start_signal_received': start_signal_received,
        })
    except Exception as e:
        logger.exception('get_frame_buffer error')
        return web.json_response({'error': str(e)}, status=500)


async def mjpeg_stream_handler(request: web.Request) -> web.StreamResponse:
    boundary = b'--frame\r\n'
    response = web.StreamResponse(
        status=200,
        headers={
            'Content-Type': 'multipart/x-mixed-replace; boundary=frame',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
        },
    )

    transport = request.transport
    if transport is None or transport.is_closing():
        logger.info('MJPEG: client transport closing before prepare')
        return response

    try:
        await response.prepare(request)
    except (ConnectionResetError, asyncio.CancelledError) as e:
        logger.info(f'MJPEG: client disconnected during prepare: {e}')
        return response

    read_index = 0
    first_written = False
    try:
        # Wait for first frame to be available
        while read_index >= len(frame_buffer) and not processing_complete:
            await asyncio.sleep(0.02)

        while True:
            if read_index < len(frame_buffer):
                entry = frame_buffer[read_index]
                read_index += 1
                try:
                    frame_bytes = base64.b64decode(entry['frame_data'])
                except Exception:
                    continue
                try:
                    await response.write(boundary)
                    await response.write(b'Content-Type: image/jpeg\r\n\r\n')
                    await response.write(frame_bytes)
                    await response.write(b'\r\n')
                    if not first_written:
                        logger.info('MJPEG: first frame written to client')
                        first_written = True
                except (ConnectionResetError, asyncio.CancelledError, RuntimeError) as e:
                    logger.info(f'MJPEG: client disconnected during write: {e}')
                    break
            else:
                if processing_complete and read_index >= len(frame_buffer):
                    logger.info('MJPEG: finished and all buffered frames flushed')
                    break
                await asyncio.sleep(0.01)
    finally:
        try:
            await response.write(b'--frame--\r\n')
        except Exception:
            pass
        try:
            await response.write_eof()
        except Exception:
            pass
    return response


def create_app() -> web.Application:
    app = web.Application(client_max_size=MAX_AUDIO_SIZE, middlewares=[cors_middleware])
    app.router.add_get('/', index_handler)
    # Generic OPTIONS for all routes (helps some proxies)
    app.router.add_route('OPTIONS', '/{tail:.*}', index_handler)
    app.router.add_post('/save_audio', save_audio_handler)
    app.router.add_post('/stream_frames', stream_frames_handler)
    app.router.add_post('/probe_musetalk', probe_musetalk_handler)
    app.router.add_get('/config', config_handler)
    app.router.add_get('/clear_buffer', clear_buffer_handler)
    app.router.add_get('/get_frame_buffer', get_frame_buffer_handler)
    app.router.add_get('/mjpeg_stream', mjpeg_stream_handler)
    # Serve uploads statically so the page can play answer.mp3
    app.router.add_static('/uploads/', path=UPLOAD_FOLDER, name='uploads')
    return app


async def main() -> None:
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    host = os.getenv('HOST', '0.0.0.0')
    port = int(os.getenv('PORT', '5000'))
    site = web.TCPSite(runner, host=host, port=port)
    try:
        await site.start()
        logger.info(f"Server started on http://{host}:{port}")
        # Wait until cancelled/terminated; cleanup in finally ensures port closes
        await asyncio.Event().wait()
    finally:
        logger.info('Shutting down server and closing port...')
        await runner.cleanup()
        logger.info('Server shutdown complete.')


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info('Interrupted by user; exiting.')
