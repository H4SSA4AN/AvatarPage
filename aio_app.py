import os
import asyncio
import base64
import json
from datetime import datetime
import logging
import aiohttp
from aiohttp import web, ClientSession


# Logging: mute all logs by default; we'll print only when frames arrive
logging.basicConfig(level=logging.CRITICAL)
logger = logging.getLogger(__name__)


# Storage
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Config
MAX_AUDIO_SIZE = 100 * 1024 * 1024  # 100MB

# State
frame_buffer = []  # entries hold raw bytes to minimize overhead: {'frame_number': int, 'frame_bytes': bytes, 'timestamp': str}
processing_complete = False
start_signal_received = False
initial_flush_pending = False
initial_buffer_received = False

# Buffer limits to avoid unbounded growth
MAX_BUFFER_FRAMES = 3000

# SSE clients (queues per connection)
sse_queues = []  # type: list

# Use MJPEG upstream ingest for fastest transmission from MuseTalk to aio_app
USE_MJPEG_INGEST = True

# MJPEG ingest task handle
_mjpeg_ingest_task = None


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
                # Optionally start MJPEG ingest (disabled by default)
                if USE_MJPEG_INGEST:
                    try:
                        base = musetalk_base_url
                        ingest_url = base + '/mjpeg_stream'
                        _start_mjpeg_ingest(ingest_url)
                    except Exception:
                        pass
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
    global frame_buffer, processing_complete, start_signal_received, initial_flush_pending, initial_buffer_received
    # Silent start

    try:
        peer = getattr(request, 'remote', None) or (request.transport and request.transport.get_extra_info('peername'))
        ctype_log = request.headers.get('Content-Type', '')
        print(f"Incoming POST /stream_frames from {peer} | Content-Type: {ctype_log}")
    except Exception:
        pass

    # Fast path: accept single-buffer JSON POSTs and log frames count
    try:
        ctype = (request.headers.get('Content-Type', '') or '').lower()
        if 'ndjson' not in ctype and 'json' in ctype:
            payload = await request.json()
            status = payload.get('status')
            if status == 'start':
                start_signal_received = True
                initial_flush_pending = True
                initial_buffer_received = False
                print('Start signal received from MuseTalk (JSON)')
                return web.json_response({'ok': True})
            if status == 'finished':
                processing_complete = True
                return web.json_response({'ok': True})

            frames = payload.get('frames', []) or []
            added = 0
            last_num = None
            for fr in frames:
                b64 = fr.get('frame_data')
                if not b64:
                    continue
                last_num = fr.get('frame_number', 0)
                try:
                    frame_bytes = base64.b64decode(b64)
                except Exception:
                    continue
                frame_buffer.append({
                    'frame_number': last_num,
                    'frame_bytes': frame_bytes,
                    'timestamp': datetime.now().isoformat(),
                })
                if len(frame_buffer) > MAX_BUFFER_FRAMES:
                    del frame_buffer[: len(frame_buffer) - MAX_BUFFER_FRAMES]
                # Per-frame log
                try:
                    print(f"Frame received (JSON POST) #{last_num} | buffer_size={len(frame_buffer)}")
                except Exception:
                    pass
                added += 1
            if initial_flush_pending:
                initial_flush_pending = False
                initial_buffer_received = True
            print(f"Batch POST received: frames={added} (last #{last_num}) | buffer_size={len(frame_buffer)}")
            return web.json_response({'ok': True, 'frames_added': added})
    except Exception:
        # Fall through to NDJSON streaming if JSON path fails
        pass

    buf = b''
    total_lines = 0
    total_frames_received = 0

    def sse_broadcast_sync(event: str, data: dict):
        # Non-awaiting broadcast: enqueue to all client queues
        for q in list(sse_queues):
            try:
                q.put_nowait({'event': event, 'data': data})
            except Exception:
                pass

    def process_line(line: str):
        nonlocal total_lines, total_frames_received
        total_lines += 1
        line = line.strip()
        if not line:
            return
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            # Ignore non-JSON lines silently
            return

        status = msg.get('status')
        if status == 'start':
            # Mark that a pre-start initial buffer should follow next
            start_signal_received = True
            initial_flush_pending = True
            initial_buffer_received = False
            print('Start signal received from MuseTalk (awaiting initial buffer flush)')
            return
        if status == 'finished':
            processing_complete = True
            try:
                sse_broadcast_sync('finished', {
                    'timestamp': datetime.now().isoformat()
                })
            except Exception:
                pass
            return

        frames = msg.get('frames', [])
        if frames:
            # When using MJPEG ingest, ignore NDJSON frame payloads to prevent duplicates
            if USE_MJPEG_INGEST:
                return
            added = 0
            last_num = None
            for fr in frames:
                b64 = fr.get('frame_data')
                if not b64:
                    continue
                last_num = fr.get('frame_number', 0)
                try:
                    frame_bytes = base64.b64decode(b64)
                except Exception:
                    continue
                frame_buffer.append({
                    'frame_number': last_num,
                    'frame_bytes': frame_bytes,
                    'timestamp': datetime.now().isoformat(),
                })
                # Enforce max buffer size (drop oldest)
                if len(frame_buffer) > MAX_BUFFER_FRAMES:
                    del frame_buffer[: len(frame_buffer) - MAX_BUFFER_FRAMES]
                added += 1
            total_frames_received += added
            # If we were expecting the initial flush, mark it received now
            if initial_flush_pending:
                initial_flush_pending = False
                initial_buffer_received = True
                print(f"Initial buffer received: +{added} frames | buffer_size={len(frame_buffer)}")
            # Only logging kept: frames received summary
            print(f"Frames received: +{added} (last #{last_num}) | buffer_size={len(frame_buffer)} | total={total_frames_received}")

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

        # Silent completion except a concise summary
        print(f"Frames received total: {total_frames_received} | lines={total_lines} | buffer_size={len(frame_buffer)}")
        return web.json_response({'ok': True, 'lines': total_lines, 'frames': total_frames_received})
    except Exception as e:
        # Silent on errors (only return JSON error)
        return web.json_response({'error': str(e)}, status=500)
    finally:
        pass


async def clear_buffer_handler(request: web.Request) -> web.Response:
    global frame_buffer, processing_complete, start_signal_received, initial_flush_pending, initial_buffer_received
    frame_buffer.clear()
    processing_complete = False
    start_signal_received = False
    initial_flush_pending = False
    initial_buffer_received = False
    return web.json_response({'success': True})


async def options_handler(request: web.Request) -> web.Response:
    return web.Response(status=200)


async def probe_musetalk_handler(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        musetalk_base_url = data.get('musetalk_url')
        if not musetalk_base_url:
            return web.json_response({'success': False, 'error': 'musetalk_url missing'}, status=400)

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
        limit_q = request.rel_url.query.get('limit')
        if from_index_q is not None:
            try:
                start = max(0, int(from_index_q))
            except ValueError:
                start = 0
            try:
                limit = int(limit_q) if limit_q is not None else 200
                if limit < 0:
                    limit = 200
            except Exception:
                limit = 200
            if limit == 0:
                frames_slice = []
                next_index = start
            else:
                end = min(len(frame_buffer), start + limit)
                # Build JSON-friendly slice with base64 on-the-fly
                frames_slice = []
                for e in frame_buffer[start:end]:
                    if 'frame_bytes' in e:
                        b64 = base64.b64encode(e['frame_bytes']).decode('utf-8')
                    else:
                        b64 = e.get('frame_data', '')
                    frames_slice.append({
                        'frame_number': e.get('frame_number', 0),
                        'frame_data': b64,
                        'timestamp': e.get('timestamp'),
                    })
                next_index = end
        else:
            try:
                limit = int(limit_q) if limit_q is not None else 200
                if limit < 0:
                    limit = 200
            except Exception:
                limit = 200
            if limit == 0:
                frames_slice = []
                next_index = 0
            else:
                frames_slice = []
                for e in frame_buffer[:limit]:
                    if 'frame_bytes' in e:
                        b64 = base64.b64encode(e['frame_bytes']).decode('utf-8')
                    else:
                        b64 = e.get('frame_data', '')
                    frames_slice.append({
                        'frame_number': e.get('frame_number', 0),
                        'frame_data': b64,
                        'timestamp': e.get('timestamp'),
                    })
                next_index = min(len(frame_buffer), limit)
        return web.json_response({
            'frames': frames_slice,
            'buffer_size': len(frame_buffer),
            'next_index': next_index,
            'processing_complete': processing_complete,
            'start_signal_received': start_signal_received,
            'initial_buffer_received': initial_buffer_received,
        })
    except Exception as e:
        # Suppress GET logging to reduce console noise
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
        return response

    try:
        await response.prepare(request)
    except (ConnectionResetError, asyncio.CancelledError):
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
                        first_written = True
                except (ConnectionResetError, asyncio.CancelledError, RuntimeError):
                    break
            else:
                if processing_complete and read_index >= len(frame_buffer):
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


def _start_mjpeg_ingest(ingest_url: str) -> None:
    global _mjpeg_ingest_task
    if _mjpeg_ingest_task and not _mjpeg_ingest_task.done():
        return
    loop = asyncio.get_event_loop()
    _mjpeg_ingest_task = loop.create_task(_mjpeg_ingest_worker(ingest_url))


async def _mjpeg_ingest_worker(ingest_url: str):
    global frame_buffer, initial_buffer_received, initial_flush_pending
    timeout = aiohttp.ClientTimeout(total=None)
    try:
        async with ClientSession(timeout=timeout) as session:
            async with session.get(ingest_url) as resp:
                reader = resp.content
                # Improve TCP receive buffer for high-throughput MJPEG
                try:
                    transport = resp.connection and resp.connection.transport
                    if transport and hasattr(transport, 'get_extra_info'):
                        sock = transport.get_extra_info('socket')
                        if sock:
                            sock.setsockopt(__import__('socket').SOL_SOCKET, __import__('socket').SO_RCVBUF, 1 << 20)
                except Exception:
                    pass
                ctype = resp.headers.get('Content-Type', '')
                boundary_token = 'frame'
                if 'boundary=' in ctype:
                    try:
                        boundary_token = ctype.split('boundary=')[1].strip()
                    except Exception:
                        boundary_token = 'frame'
                boundary_line = ('--' + boundary_token).encode('utf-8')

                async def read_line() -> bytes:
                    return await reader.readline()

                next_frame_number = 0
                # Read stream: boundary -> headers -> blank line -> body
                while True:
                    line = await read_line()
                    if not line:
                        break
                    if boundary_line not in line:
                        continue
                    # Parse headers
                    content_length = None
                    # Default content type not strictly needed
                    while True:
                        hdr = await read_line()
                        if not hdr:
                            break
                        if hdr in (b'\r\n', b'\n'):
                            break
                        try:
                            lower = hdr.decode('latin1').strip().lower()
                            if lower.startswith('content-length:'):
                                content_length = int(lower.split(':', 1)[1].strip())
                        except Exception:
                            pass
                    if content_length is None:
                        # Fallback: skip this part if no length; avoid scanning
                        continue
                    try:
                        body = await reader.readexactly(content_length)
                        # Consume the trailing CRLF line after the body
                        _ = await reader.readline()
                    except Exception:
                        break
                    try:
                        frame_buffer.append({
                            'frame_number': next_frame_number,
                            'frame_bytes': body,
                            'timestamp': datetime.now().isoformat(),
                        })
                        if len(frame_buffer) > MAX_BUFFER_FRAMES:
                            del frame_buffer[: len(frame_buffer) - MAX_BUFFER_FRAMES]
                        if next_frame_number == 0:
                            initial_buffer_received = True
                            initial_flush_pending = False
                            print('MJPEG ingest: first frame appended, buffer_size=1 (initial buffer ready)')
                        # Per-frame log
                        print(f"Frame received (MJPEG) #{next_frame_number} | buffer_size={len(frame_buffer)}")
                        next_frame_number += 1
                    except Exception:
                        pass
    except Exception:
        return

async def sse_events_handler(request: web.Request) -> web.StreamResponse:
    """Server-Sent Events endpoint to push start/finished signals to the web page."""
    response = web.StreamResponse(
        status=200,
        headers={
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
        },
    )
    try:
        await response.prepare(request)
    except (ConnectionResetError, asyncio.CancelledError):
        return response

    queue = asyncio.Queue()
    sse_queues.append(queue)

    # Send initial comment to keep connection open
    try:
        await response.write(b": connected\n\n")
    except Exception:
        try:
            sse_queues.remove(queue)
        except ValueError:
            pass
        return response

    try:
        while True:
            try:
                message = await queue.get()
            except asyncio.CancelledError:
                break
            try:
                event = message.get('event', 'message')
                data = json.dumps(message.get('data', {}))
                await response.write(f"event: {event}\n".encode('utf-8'))
                await response.write(f"data: {data}\n\n".encode('utf-8'))
            except (ConnectionResetError, asyncio.CancelledError, RuntimeError):
                break
    finally:
        try:
            sse_queues.remove(queue)
        except ValueError:
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
    app.router.add_get('/clear_buffer', clear_buffer_handler)
    app.router.add_get('/get_frame_buffer', get_frame_buffer_handler)
    app.router.add_get('/mjpeg_stream', mjpeg_stream_handler)
    app.router.add_get('/events', sse_events_handler)
    return app


if __name__ == '__main__':
    app = create_app()
    web.run_app(app, host='0.0.0.0', port=5000)


