import os
import asyncio
import base64
import json
from datetime import datetime
import logging
import aiohttp
from aiohttp import web, ClientSession


# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Storage
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Config
MAX_AUDIO_SIZE = 100 * 1024 * 1024  # 100MB

# State
frame_buffer = []
processing_complete = False
start_signal_received = False


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
        musetalk_base_url = data.get('musetalk_url') or os.environ.get('MUSETALK_URL', 'http://localhost:8085')

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
        form.add_field('audio', open(filepath, 'rb'), filename='input.wav', content_type='audio/wav')
        form.add_field('stream_url', stream_url)
        form.add_field('fps', fps)
        form.add_field('batch_size', batch_size)
        form.add_field('bbox_shift', '0')

        timeout = aiohttp.ClientTimeout(total=60)
        async with ClientSession(timeout=timeout) as session:
            async with session.post(musetalk_url, data=form) as resp:
                text = await resp.text()
                return web.json_response({
                    'success': resp.status == 200,
                    'message': 'Audio forwarded to MuseTalk',
                    'musetalk_response': text,
                    'musetalk_url': musetalk_url,
                    'stream_url': stream_url,
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
    app = web.Application(client_max_size=MAX_AUDIO_SIZE)
    app.router.add_get('/', index_handler)
    app.router.add_post('/save_audio', save_audio_handler)
    app.router.add_post('/stream_frames', stream_frames_handler)
    app.router.add_get('/clear_buffer', clear_buffer_handler)
    app.router.add_get('/get_frame_buffer', get_frame_buffer_handler)
    app.router.add_get('/mjpeg_stream', mjpeg_stream_handler)
    return app


if __name__ == '__main__':
    app = create_app()
    web.run_app(app, host='0.0.0.0', port=5000)


