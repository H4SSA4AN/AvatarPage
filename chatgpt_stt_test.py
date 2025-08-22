import os
import argparse

from dotenv import load_dotenv


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

    parser = argparse.ArgumentParser(description='Transcribe audio with OpenAI and print transcript.')
    parser.add_argument('--audio', '-a', default='uploads/input.wav', help='Path to audio file (e.g., wav/mp3/webm)')
    parser.add_argument('--model', '-m', default=os.getenv('TRANSCRIBE_MODEL', 'whisper-1'),
                        help='Transcription model (default: whisper-1)')
    args = parser.parse_args()

    audio_path = args.audio
    if not os.path.isfile(audio_path):
        print(f'ERROR: audio file not found: {audio_path}')
        raise SystemExit(1)

    client = OpenAI(api_key=api_key)

    print(f'Transcribing: {audio_path} using model {args.model} ...')
    try:
        with open(audio_path, 'rb') as af:
            resp = client.audio.transcriptions.create(
                model=args.model,
                file=af,
            )
        text = getattr(resp, 'text', None) or str(resp)
        print('--- Transcript ---')
        print(text)
    except Exception as e:
        print('Transcription failed:', e)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
