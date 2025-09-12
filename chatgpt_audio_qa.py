import os
import argparse
from typing import Optional

from dotenv import load_dotenv


def transcribe_audio(client, audio_path: str, model: str) -> str:
	with open(audio_path, 'rb') as af:
		resp = client.audio.transcriptions.create(
			model=model,
			file=af,
		)
	text = getattr(resp, 'text', None) or str(resp)
	return text


def get_chat_answer(client, prompt_text: str, chat_model: str, system_prompt: Optional[str]) -> str:
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


def synthesize_tts(client, text: str, tts_model: str, voice: str, out_path: str) -> str:
	# Ensure directory exists
	dirname = os.path.dirname(out_path) or '.'
	os.makedirs(dirname, exist_ok=True)
	# If .wav requested, switch to .mp3 due to SDK's default output
	root, ext = os.path.splitext(out_path)
	if ext.lower() == '.wav':
		print('[TTS] WAV requested, saving MP3 instead (convert to WAV if needed).')
		out_path = root + '.mp3'
	# Stream audio to file (SDK defaults to audio/mpeg)
	with client.audio.speech.with_streaming_response.create(
		model=tts_model,
		voice=voice,
		input=text,
	) as resp:
		resp.stream_to_file(out_path)
	return out_path


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

	parser = argparse.ArgumentParser(description='Transcribe audio, ask GPT, print transcript + answer, and synthesize TTS to audio file.')
	parser.add_argument('--audio', '-a', default='uploads/input.wav', help='Path to audio file (wav/mp3/m4a/webm, etc.)')
	parser.add_argument('--stt-model', default=os.getenv('TRANSCRIBE_MODEL', 'whisper-1'), help='STT model (default: whisper-1)')
	parser.add_argument('--chat-model', default=os.getenv('CHAT_MODEL', 'gpt-4o-mini'), help='Chat model (default: gpt-4o-mini)')
	parser.add_argument('--system', default=os.getenv('SYSTEM_PROMPT', 'You are a concise, helpful assistant.'), help='System prompt')
	parser.add_argument('--tts-model', default=os.getenv('TTS_MODEL', 'tts-1'), help='TTS model (default: tts-1)')
	parser.add_argument('--voice', default=os.getenv('TTS_VOICE', 'alloy'), help='TTS voice (default: alloy)')
	parser.add_argument('--out-wav', default='uploads/answer.wav', help='Output audio path (".mp3" will be used if ".wav" unsupported)')
	args = parser.parse_args()

	audio_path = args.audio
	if not os.path.isfile(audio_path):
		print(f'ERROR: audio file not found: {audio_path}')
		raise SystemExit(1)

	client = OpenAI(api_key=api_key)

	print(f'[STT] Transcribing: {audio_path} using {args.stt_model if hasattr(args, "stt-model") else args.stt_model} ...')
	try:
		# argparse converts to stt_model attribute
		transcript = transcribe_audio(client, audio_path, args.stt_model)
	except Exception as e:
		print('Transcription failed:', e)
		raise SystemExit(1)

	print('--- Transcript ---')
	print(transcript)

	print(f'\n[CHAT] Querying {args.chat_model} ...')
	try:
		answer = get_chat_answer(client, transcript, args.chat_model, args.system)
	except Exception as e:
		print('Chat completion failed:', e)
		raise SystemExit(1)

	print('--- Answer ---')
	print(answer)

	print(f'\n[TTS] Synthesizing answer using {args.tts_model} (voice: {args.voice}) ...')
	try:
		saved_path = synthesize_tts(client, answer, args.tts_model, args.voice, args.out_wav)
		print(f'[TTS] Saved: {saved_path}')
	except Exception as e:
		print('TTS synthesis failed:', e)
		raise SystemExit(1)


if __name__ == '__main__':
	main()
