import os
import argparse
from typing import Optional

import aiohttp
import asyncio
from dotenv import load_dotenv


async def stt_transcribe(client, audio_path: str, model: str) -> str:
	with open(audio_path, 'rb') as af:
		resp = client.audio.transcriptions.create(
			model=model,
			file=af,
		)
	text = getattr(resp, 'text', None) or str(resp)
	return text


def chat_infer(client, prompt_text: str, chat_model: str, system_prompt: Optional[str]) -> str:
	messages = []
	if system_prompt:
		messages.append({"role": "system", "content": system_prompt})
	messages.append({"role": "user", "content": prompt_text})
	resp = client.chat.completions.create(
		model=chat_model,
		messages=messages,
		temperature=0.7,
	)
	return resp.choices[0].message.content


def tts_synthesize(client, text: str, tts_model: str, voice: str, out_mp3_path: str) -> str:
	# Ensure output directory exists
	dirname = os.path.dirname(out_mp3_path) or '.'
	os.makedirs(dirname, exist_ok=True)
	# Stream MP3 to file
	with client.audio.speech.with_streaming_response.create(
		model=tts_model,
		voice=voice,
		input=text,
	) as resp:
		resp.stream_to_file(out_mp3_path)
	return out_mp3_path


async def post_to_musetalk(audio_path: str, musetalk_url: str, stream_url: str, fps: str, batch_size: str, bbox_shift: str = '0') -> dict:
	timeout = aiohttp.ClientTimeout(total=120)
	async with aiohttp.ClientSession(timeout=timeout) as session:
		form = aiohttp.FormData()
		form.add_field('audio', open(audio_path, 'rb'), filename=os.path.basename(audio_path), content_type='audio/mpeg')
		form.add_field('stream_url', stream_url)
		form.add_field('fps', str(fps))
		form.add_field('batch_size', str(batch_size))
		form.add_field('bbox_shift', str(bbox_shift))
		async with session.post(musetalk_url.rstrip('/') + '/process', data=form) as resp:
			text = await resp.text()
			return {'status': resp.status, 'text': text}


def normalize_base_url(url: str) -> str:
	u = (url or '').strip()
	if not u:
		raise ValueError('MuseTalk base URL is required')
	if u.endswith('/'):
		u = u[:-1]
	if not (u.startswith('http://') or u.startswith('https://')):
		u = 'http://' + u
	return u


def main() -> None:
	load_dotenv()

	api_key = os.getenv('OPENAI_API_KEY')
	if not api_key:
		print('ERROR: OPENAI_API_KEY is not set. Create AvatarPage/.env and set OPENAI_API_KEY=...')
		raise SystemExit(1)

	try:
		from openai import OpenAI
	except Exception:
		print('ERROR: openai package not installed. Run: pip install -r AvatarPage/requirements.txt')
		raise SystemExit(1)

	parser = argparse.ArgumentParser(description='Bridge: input.wav -> STT -> GPT -> TTS (MP3) -> MuseTalk /process')
	parser.add_argument('--input', '-i', default='uploads/input.wav', help='Input WAV path (from aio app)')
	parser.add_argument('--musetalk', '-u', default=os.getenv('MUSETALK_URL', 'http://localhost:8085'), help='MuseTalk base URL (e.g., http://localhost:8085)')
	parser.add_argument('--public-base', '-b', default=os.getenv('PUBLIC_BASE', 'http://localhost:5000'), help='Public base of this app for stream registration, e.g., http://host:5000')
	parser.add_argument('--fps', default=os.getenv('FPS', '15'), help='FPS for MuseTalk')
	parser.add_argument('--batch-size', default=os.getenv('BATCH_SIZE', '20'), help='Batch size for MuseTalk')
	parser.add_argument('--stt-model', default=os.getenv('TRANSCRIBE_MODEL', 'whisper-1'), help='STT model')
	parser.add_argument('--chat-model', default=os.getenv('CHAT_MODEL', 'gpt-4o-mini'), help='Chat model')
	parser.add_argument('--system', default=os.getenv('SYSTEM_PROMPT', 'You are a concise, helpful assistant.'), help='System prompt for chat')
	parser.add_argument('--tts-model', default=os.getenv('TTS_MODEL', 'tts-1'), help='TTS model')
	parser.add_argument('--voice', default=os.getenv('TTS_VOICE', 'alloy'), help='TTS voice')
	parser.add_argument('--out', default='uploads/answer.mp3', help='Output synthesized audio path (MP3)')
	args = parser.parse_args()

	in_wav = args.input
	if not os.path.isfile(in_wav):
		print(f'ERROR: input file not found: {in_wav}')
		raise SystemExit(1)

	client = OpenAI(api_key=api_key)

	print(f'[STT] Transcribing: {in_wav} using {args.stt_model} ...')
	try:
		transcript = asyncio.run(stt_transcribe(client, in_wav, args.stt_model))
	except Exception as e:
		print('STT failed:', e)
		raise SystemExit(1)

	print('--- Transcript ---')
	print(transcript)

	print(f'\n[CHAT] Using {args.chat_model} ...')
	try:
		answer_text = chat_infer(client, transcript, args.chat_model, args.system)
	except Exception as e:
		print('Chat inference failed:', e)
		raise SystemExit(1)

	print('--- Answer ---')
	print(answer_text)

	print(f'\n[TTS] Synthesizing to {args.out} using {args.tts_model} (voice: {args.voice}) ...')
	try:
		saved_mp3 = tts_synthesize(client, answer_text, args.tts_model, args.voice, args.out)
		print(f'[TTS] Saved: {saved_mp3}')
	except Exception as e:
		print('TTS failed:', e)
		raise SystemExit(1)

	# Build stream callback URL for MuseTalk
	public_base = (args.public_base or '').rstrip('/')
	stream_url = public_base + '/stream_frames'
	base = normalize_base_url(args.musetalk)

	print(f'\n[MUSETALK] Posting synthesized audio to {base}/process ...')
	try:
		res = asyncio.run(post_to_musetalk(saved_mp3, base, stream_url, args.fps, args.batch_size))
		print(f'[MUSETALK] Status: {res["status"]}')
		print(f'[MUSETALK] Body: {res["text"][:500]}...')
	except Exception as e:
		print('MuseTalk post failed:', e)
		raise SystemExit(1)


if __name__ == '__main__':
	main()
