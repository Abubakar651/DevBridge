"""Explicit, small live checks. Never run automatically at application startup."""

import argparse
import asyncio
import json
from dataclasses import replace
from pathlib import Path

from .config import load_settings
from .providers import Providers
from .models import Context
from .scenario import DEFAULT_CONTEXT


async def main(args):
    settings = load_settings()
    if args.model:
        settings = replace(settings, gemini_model=args.model)
    if args.groq_only:
        settings = replace(settings, gemini_key="")
    diagnostic = (lambda detail: print(json.dumps({"providerDiagnostic": detail}))) if args.diagnostic else None
    provider = Providers(settings, diagnostic=diagnostic, fallback_enabled=not args.gemini_only)
    results = []

    async def check(name, task):
        try:
            result = {"check": name, "status": "passed", **(await task())}
        except Exception as error:
            result = {"check": name, "status": "failed", "code": getattr(error, "code", "ERROR"), "message": str(error)}
        results.append(result)
        print(json.dumps(result), flush=True)

    if args.list_gemini_models:
        async def models():
            data = await provider.request("GET", "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000", headers={"x-goog-api-key": settings.gemini_key})
            return {"models": [model["name"] for model in data.get("models", []) if "generateContent" in model.get("supportedGenerationMethods", []) and any(word in model["name"] for word in ("flash", "hydrogen"))]}
        await check("Available Gemini models", models)
    elif args.whisper_audio:
        async def whisper():
            text = await provider.transcribe(Path(args.whisper_audio).read_bytes(), "audio/wav")
            if not any(word in text.lower() for word in ("voice", "coach", "practice")):
                raise ValueError("The transcript did not match the synthetic test sentence.")
            return {"transcription": text, "model": settings.stt_model}
        await check("Groq Whisper input", whisper)
    else:
        if not (args.gemini_only or args.groq_only or args.text_only):
            async def speech():
                audio = await provider.speak("DevBridge is ready for practice.")
                text = await provider.transcribe(audio, "audio/wav")
                if not any(word in text.lower() for word in ("voice", "coach", "practice")):
                    raise ValueError("The transcript did not match the test sentence.")
                return {"audioBytes": len(audio), "transcription": text, "ttsModel": settings.tts_model, "sttModel": settings.stt_model}
            await check("Groq speech round trip", speech)

        async def reasoning():
            context = Context.model_validate(DEFAULT_CONTEXT)
            opening = await provider.roleplay(context, [])
            history = [{"role": "assistant", "content": opening}, {"role": "user", "content": "Search is ready for Friday. PDF export needs two more working days. I recommend releasing search first. Which outcome is the priority?"}]
            feedback = await provider.coach(context, history)
            return {"reasoning": provider.reasoning_events, "evidenceChecked": True, "feedbackImprovements": len(feedback.improvements), "opening": opening, "improvedMessage": feedback.improved_message}
        if not args.voice_only:
            await check("Role-play and feedback", reasoning)
    return 0 if all(result["status"] == "passed" for result in results) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diagnostic", action="store_true", help="Show upstream error details with configured keys redacted.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--voice-only", action="store_true", help="Only test Orpheus output and Whisper input.")
    mode.add_argument("--text-only", action="store_true", help="Test Gemini role-play/coaching with automatic Groq fallback.")
    mode.add_argument("--gemini-only", action="store_true", help="Test Gemini without fallback or speech.")
    mode.add_argument("--groq-only", action="store_true", help="Test backup reasoning with Gemini deliberately unconfigured; no speech.")
    mode.add_argument("--list-gemini-models", action="store_true")
    mode.add_argument("--whisper-audio", help="WAV containing a short DevBridge practice test phrase.")
    parser.add_argument("--model", help="Test an alternate Gemini model without changing .env.")
    raise SystemExit(asyncio.run(main(parser.parse_args())))
