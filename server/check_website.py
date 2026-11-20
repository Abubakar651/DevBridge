"""Explicit live HTTP check of the website API; does not test a browser or microphone."""

import argparse
from datetime import datetime
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import uuid
import wave
from zoneinfo import ZoneInfo

import httpx

from .config import PROJECT_ROOT


class CheckFailed(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def main(args):
    audio = Path(args.audio).read_bytes()
    if not (64 <= len(audio) <= 5 * 1024 * 1024 and audio[:4] == b"RIFF" and audio[8:12] == b"WAVE"):
        raise SystemExit("Provide a WAV recording under 5 MB containing the release-update test answer.")
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    origin = f"http://127.0.0.1:{port}"
    report = {"checkedAt": datetime.now(ZoneInfo("Asia/Karachi")).isoformat(), "method": "Live HTTP endpoints on a separate local server; no browser automation", "checks": []}
    process = subprocess.Popen([sys.executable, str(PROJECT_ROOT / "run.py")], cwd=PROJECT_ROOT,
        env={**os.environ, "HOST": "127.0.0.1", "PORT": str(port), "PYTHONUNBUFFERED": "1"},
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    def check(name, function):
        started = time.monotonic()
        try:
            result = function()
            entry = {"check": name, "status": "passed", **(result or {})}
        except (CheckFailed, httpx.HTTPError, AssertionError) as error:
            entry = {"check": name, "status": "failed", "code": getattr(error, "code", "CHECK_FAILED"), "message": str(error)}
        entry["seconds"] = round(time.monotonic() - started, 2)
        report["checks"].append(entry)
        print(json.dumps(entry), flush=True)
        return entry["status"] == "passed"

    with httpx.Client(base_url=origin, timeout=75, trust_env=False, headers={"Origin": origin}) as client:
        def request(method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            if not response.is_success:
                try:
                    error = response.json()["error"]
                except (ValueError, KeyError, TypeError):
                    error = {"code": "HTTP_ERROR", "message": f"HTTP {response.status_code}"}
                raise CheckFailed(error["code"], error["message"])
            return response

        def action(path, **fields):
            return request("POST", path, json={"requestId": str(uuid.uuid4()), **fields}).json()

        session_path = None
        try:
            deadline = time.monotonic() + 10
            while True:
                if process.poll() is not None:
                    raise CheckFailed("STARTUP_FAILED", "The verification server exited during startup.")
                try:
                    if client.get("/").status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                if time.monotonic() >= deadline:
                    raise CheckFailed("STARTUP_TIMEOUT", "The verification server did not become ready.")
                time.sleep(0.05)

            def assets():
                for path in ("/", "/app.js", "/api.js", "/audio.js", "/session.js", "/styles.css"):
                    assert request("GET", path).status_code == 200
                return {"resources": 6}
            check("Page and browser resources", assets)
            config = request("GET", "/api/config").json()
            report["configured"] = config["configured"]
            transcript = None

            def transcription():
                nonlocal transcript
                transcript = request("POST", "/api/transcribe", content=audio, headers={"Content-Type": "audio/wav"}).json()["text"]
                assert "search" in transcript.lower() and "friday" in transcript.lower() and "export" in transcript.lower(), "The transcript did not contain the test answer's key facts."
                return {"audioBytes": len(audio), "transcript": transcript}
            check("Synthetic voice input through website endpoint", transcription)

            def speech():
                response = request("POST", "/api/speak", json={"text": "DevBridge is ready for practice."})
                assert response.headers["content-type"] == "audio/wav"
                assert response.content[:4] == b"RIFF" and response.content[8:12] == b"WAVE"
                return {"audioBytes": len(response.content)}
            voice_available = check("Orpheus output through website endpoint", speech)

            def model_speech(text, label):
                segments = request("POST", "/api/speech/segments", json={"text": text}).json()["segments"]
                assert segments and all(0 < len(segment) <= 200 for segment in segments)
                frames, audio_bytes, parameters = [], 0, None
                for segment in segments:
                    response = request("POST", "/api/speak", json={"text": segment})
                    with wave.open(io.BytesIO(response.content), "rb") as recording:
                        current = recording.getparams()[:3]
                        assert parameters is None or current == parameters, "Speech segments returned inconsistent WAV formats."
                        parameters = current
                        frames.append(recording.readframes(recording.getnframes()))
                    audio_bytes += len(response.content)
                destination = None
                if args.audio_output:
                    directory = Path(args.audio_output)
                    directory.mkdir(parents=True, exist_ok=True)
                    destination = directory / (label + ".wav")
                    with wave.open(str(destination), "wb") as combined:
                        combined.setnchannels(parameters[0])
                        combined.setsampwidth(parameters[1])
                        combined.setframerate(parameters[2])
                        combined.writeframes(b"".join(frames))
                duration = sum(map(len, frames)) / (parameters[0] * parameters[1] * parameters[2])
                return {"segments": len(segments), "audioBytes": audio_bytes, "durationSeconds": round(duration, 2), "file": str(destination) if destination else None}

            practice = action("/api/practice", context=config["defaultContext"])
            session_path = "/api/practice/" + practice["sessionId"]
            snapshot = None

            def opening():
                nonlocal snapshot
                snapshot = action(session_path + "/advance")
                assert snapshot["playback"]["speaker"] == "Project manager"
                return {"reply": snapshot["playback"]["text"]}
            if check("Live stakeholder opening", opening) and transcript:
                if voice_available:
                    check("Speak the generated stakeholder opening", lambda: model_speech(snapshot["playback"]["text"], "stakeholder-opening"))
                def answer():
                    request_id = str(uuid.uuid4())
                    for _ in range(2):
                        accepted = request("POST", session_path + "/answer", json={"text": transcript, "requestId": request_id}).json()
                    count = sum(turn["role"] == "user" for turn in accepted["attempts"][0]["messages"])
                    assert count == 1, "A replayed answer was accepted twice."
                    return {"acceptedAnswers": count}
                if check("Submit transcript without duplicate answers", answer):
                    check("Live stakeholder follow-up", opening)
                    action(session_path + "/finish")

                    def feedback():
                        nonlocal snapshot
                        snapshot = action(session_path + "/advance")
                        notes = snapshot["attempts"][0]["feedback"]
                        assert notes and snapshot["playback"]["speaker"] == "Coach"
                        for quote in [notes["strength"]["quote"], *(item["quote"] for item in notes["improvements"])]:
                            assert " ".join(quote.casefold().split()) in " ".join(transcript.casefold().split())
                        return {"feedback": notes, "knownFacts": snapshot["context"]["knownFacts"]}
                    if check("Live coaching with grounded evidence", feedback):
                        if voice_available:
                            check("Speak the generated coaching summary", lambda: model_speech(snapshot["playback"]["text"], "coaching-summary"))
                            check("Speak the improved explanation", lambda: model_speech(snapshot["attempts"][0]["feedback"]["improvedMessage"], "improved-explanation"))
                        def retry():
                            result = action(session_path + "/retry")
                            assert result["context"] == config["defaultContext"]
                            assert len(result["attempts"]) == 2
                            assert result["attempts"][1]["messages"] == []
                            assert result["attempts"][0]["feedback"]
                            return {"sameFacts": True, "attempts": 2}
                        check("Retry with preserved facts and separate history", retry)
            if session_path:
                check("Reset temporary practice", lambda: {"httpStatus": request("DELETE", session_path).status_code})
                session_path = None
        finally:
            if session_path:
                try:
                    client.delete(session_path)
                except httpx.HTTPError:
                    pass
            process.terminate()
            try:
                logs = process.communicate(timeout=5)[0]
            except subprocess.TimeoutExpired:
                process.kill()
                logs = process.communicate()[0]
            report["serverLog"] = logs.splitlines()
            report["status"] = "passed" if report["checks"] and all(item["status"] == "passed" for item in report["checks"]) else "incomplete"
            if args.report:
                Path(args.report).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            print(json.dumps({"status": report["status"], "serverLog": report["serverLog"]}), flush=True)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", required=True, help="WAV test answer; no physical microphone is used.")
    parser.add_argument("--report", help="Optional JSON report path. Contains synthetic transcripts and safe server logs.")
    parser.add_argument("--audio-output", help="Optional directory for generated stakeholder/coach/example WAV files.")
    raise SystemExit(main(parser.parse_args()))
