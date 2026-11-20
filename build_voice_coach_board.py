"""Build the Voice Coach PWA MVP & System Architecture Board on Miro.

Reads MIRO_ACCESS_TOKEN and MIRO_BOARD_ID from the workspace .env file,
clears existing canvas clutter (optional flag, enabled by default for clean rebuilds),
validates layout bounds and non-overlap before posting, and constructs 6 structured
architectural frames with native Miro shapes, sticky notes, texts, and connectors.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from miro_client import MiroClient


@dataclass
class Box:
    """Axis-aligned bounding box inside a frame for overlap/bounds verification."""

    label: str
    x: float
    y: float
    w: float
    h: float

    @property
    def left(self) -> float:
        return self.x - self.w / 2

    @property
    def right(self) -> float:
        return self.x + self.w / 2

    @property
    def top(self) -> float:
        return self.y - self.h / 2

    @property
    def bottom(self) -> float:
        return self.y + self.h / 2


class LayoutGuard:
    """Ensures every item placed inside a frame stays within margins and never overlaps."""

    def __init__(
        self, frame_name: str, width: float, height: float, margin: float = 25.0
    ) -> None:
        self.frame_name = frame_name
        self.width = width
        self.height = height
        self.margin = margin
        self.boxes: list[Box] = []

    def register(
        self, label: str, x: float, y: float, w: float, h: float, pad: float = 4.0
    ) -> None:
        box = Box(label=label, x=x, y=y, w=w, h=h)
        if (
            box.left < self.margin
            or box.right > self.width - self.margin
            or box.top < self.margin
            or box.bottom > self.height - self.margin
        ):
            raise ValueError(
                f"[{self.frame_name}] '{label}' ({box.left:.0f}..{box.right:.0f}, "
                f"{box.top:.0f}..{box.bottom:.0f}) exceeds frame bounds ({self.width}x{self.height})"
            )
        for other in self.boxes:
            overlap_x = (box.left + pad) < other.right and (
                box.right - pad
            ) > other.left
            overlap_y = (box.top + pad) < other.bottom and (
                box.bottom - pad
            ) > other.top
            if overlap_x and overlap_y:
                raise ValueError(
                    f"[{self.frame_name}] Overlap detected between '{label}' and '{other.label}'"
                )
        self.boxes.append(box)


def p(text: str) -> str:
    """Wrap paragraph safely for Miro HTML content."""
    return f"<p>{text}</p>"


def hbox(title: str, body: str) -> str:
    """Format a card-like shape with bold title + body lines."""
    return f"<p><strong>{title}</strong></p><p>{body}</p>"


class BoardBuilder:
    """Declarative builder for the 6-frame Voice Coach PWA planning board."""

    # Palette constants
    SLATE_DARK = "#0F172A"
    SLATE_SUB = "#1E293B"
    TEXT_DARK = "#0F172A"
    TEXT_MUTED = "#334155"
    TEXT_LIGHT = "#F8FAFC"

    INDIGO_FILL = "#EEF2FF"
    INDIGO_BORDER = "#4F46E5"

    EMERALD_FILL = "#ECFDF5"
    EMERALD_BORDER = "#059669"

    SKY_FILL = "#E0F2FE"
    SKY_BORDER = "#0284C7"

    AMBER_FILL = "#FEF3C7"
    AMBER_BORDER = "#D97706"

    CRIMSON_FILL = "#FEF2F2"
    CRIMSON_BORDER = "#DC2626"

    VIOLET_FILL = "#F5F3FF"
    VIOLET_BORDER = "#7C3AED"

    NEUTRAL_FILL = "#F8FAFC"
    NEUTRAL_BORDER = "#64748B"

    def __init__(self, client: MiroClient) -> None:
        self.client = client
        self.created_items: list[dict[str, str]] = []

    def _track(self, kind: str, label: str, item: dict) -> str:
        item_id = item["id"]
        self.created_items.append({"type": kind, "label": label, "id": item_id})
        return item_id

    def add_frame(
        self, title: str, x: float, y: float, w: float, h: float, fill: str
    ) -> tuple[str, LayoutGuard]:
        res = self.client.create_frame(
            title=title, x=x, y=y, width=w, height=h, fill_color=fill
        )
        fid = self._track("frame", title, res)
        return fid, LayoutGuard(title, w, h)

    def add_shape(
        self,
        guard: LayoutGuard | None,
        parent_id: str | None,
        label: str,
        content: str,
        x: float,
        y: float,
        w: float,
        h: float,
        *,
        shape: str = "round_rectangle",
        fill: str = "#FFFFFF",
        border: str = "#CBD5E1",
        text_color: str = "#0F172A",
        font_size: str = "14",
        border_width: str = "2",
        border_style: str = "normal",
        text_align: str = "left",
        text_align_vertical: str = "middle",
    ) -> str:
        if guard is not None:
            guard.register(label, x, y, w, h)
        res = self.client.create_shape(
            content=content,
            x=x,
            y=y,
            width=w,
            height=h,
            shape=shape,
            fill_color=fill,
            border_color=border,
            text_color=text_color,
            font_size=font_size,
            border_width=border_width,
            border_style=border_style,
            text_align=text_align,
            text_align_vertical=text_align_vertical,
            parent_id=parent_id,
        )
        return self._track("shape", label, res)

    def add_sticky(
        self,
        guard: LayoutGuard,
        parent_id: str,
        label: str,
        content: str,
        x: float,
        y: float,
        *,
        width: float = 250,
        fill_color: str = "light_yellow",
    ) -> str:
        # Miro square sticky height is ~1.145 * width; validate against generous 1.18 * width.
        guard.register(label, x, y, width, width * 1.18)
        res = self.client.create_sticky(
            content=content,
            x=x,
            y=y,
            width=width,
            fill_color=fill_color,
            shape="square",
            text_align="left",
            text_align_vertical="top",
            parent_id=parent_id,
        )
        return self._track("sticky_note", label, res)

    def add_subheader(
        self,
        guard: LayoutGuard,
        parent_id: str,
        title: str,
        x: float,
        y: float,
        w: float,
        accent: str,
    ) -> str:
        return self.add_shape(
            guard,
            parent_id,
            f"subheader:{title}",
            p(f"<strong>{title}</strong>"),
            x,
            y,
            w,
            46,
            shape="rectangle",
            fill=accent,
            border=accent,
            text_color=self.TEXT_LIGHT,
            font_size="16",
            border_width="1",
            text_align="center",
        )

    def connect(
        self,
        start_id: str,
        end_id: str,
        *,
        caption: str = "",
        start_snap: str = "auto",
        end_snap: str = "auto",
        start_pos: tuple[str, str] | None = None,
        end_pos: tuple[str, str] | None = None,
        shape: str = "elbowed",
        color: str = "#334155",
        style: str = "normal",
        width: str = "2",
    ) -> str:
        res = self.client.create_connector(
            start_id=start_id,
            end_id=end_id,
            caption=caption,
            start_snap=start_snap,
            end_snap=end_snap,
            start_pos=start_pos,
            end_pos=end_pos,
            shape=shape,
            stroke_color=color,
            stroke_width=width,
            stroke_style=style,
            end_cap="stealth",
        )
        return self._track("connector", f"{start_id}->{end_id}", res)

    def build_banner(self) -> None:
        """Create top header banner and color legend above Row 1 frames."""
        # Main Title Background
        self.add_shape(
            None,
            None,
            "banner_bg",
            "",
            x=-860,
            y=-1110,
            w=3400,
            h=250,
            shape="round_rectangle",
            fill=self.SLATE_DARK,
            border="#38BDF8",
            border_width="3",
        )
        title_item = self.client.create_text(
            content="<p><strong>VOICE COACH PWA · 2-DAY SPRINT MVP &amp; SYSTEM ARCHITECTURE</strong></p>",
            x=-860,
            y=-1155,
            width=3240,
            font_size="44",
            color="#F8FAFC",
            text_align="left",
        )
        self._track("text", "banner_title", title_item)

        subtitle_item = self.client.create_text(
            content=(
                "<p>High-Pressure Technical Mock Interviewer (Associate SWE: OOP &amp; Databases) · "
                "100% Vanilla HTML/CSS/JS PWA · Web Speech STT · Gemini 1.5 · ElevenLabs / Web Speech TTS · Anti-Echo FSM</p>"
            ),
            x=-860,
            y=-1065,
            width=3240,
            font_size="20",
            color="#E2E8F0",
            text_align="left",
        )
        self._track("text", "banner_subtitle", subtitle_item)

        # Legend Container on the top-right
        self.add_shape(
            None,
            None,
            "legend_bg",
            "",
            x=1730,
            y=-1110,
            w=1660,
            h=250,
            shape="round_rectangle",
            fill="#FFFFFF",
            border="#CBD5E1",
            border_width="2",
        )
        legend_title = self.client.create_text(
            content="<p><strong>ARCHITECTURE COLOR KEY</strong></p>",
            x=1730,
            y=-1195,
            width=1580,
            font_size="18",
            color="#0F172A",
            text_align="left",
        )
        self._track("text", "legend_title", legend_title)

        pills = [
            (
                "AI Brain / Gemini 1.5",
                self.INDIGO_FILL,
                self.INDIGO_BORDER,
                1185,
                -1125,
            ),
            (
                "Voice Input (STT) / Listening",
                self.EMERALD_FILL,
                self.EMERALD_BORDER,
                1730,
                -1125,
            ),
            (
                "Voice Output (TTS) / Speaking",
                self.SKY_FILL,
                self.SKY_BORDER,
                2275,
                -1125,
            ),
            (
                "Decision Gate / Thinking",
                self.AMBER_FILL,
                self.AMBER_BORDER,
                1185,
                -1045,
            ),
            (
                "Anti-Echo Guard / Risk",
                self.CRIMSON_FILL,
                self.CRIMSON_BORDER,
                1730,
                -1045,
            ),
            ("PWA Shell & Cache", self.VIOLET_FILL, self.VIOLET_BORDER, 2275, -1045),
        ]
        for label, fill, border, px, py in pills:
            self.add_shape(
                None,
                None,
                f"legend:{label}",
                p(f"<strong>{label}</strong>"),
                x=px,
                y=py,
                w=510,
                h=56,
                shape="round_rectangle",
                fill=fill,
                border=border,
                text_color=self.TEXT_DARK,
                font_size="16",
                text_align="center",
            )

    def build_frame_01(self) -> None:
        fid, g = self.add_frame(
            "01 · Problem Statement, MVP Goals & Sprint Scope",
            x=-1760,
            y=-160,
            w=1600,
            h=1340,
            fill="#FFF9F8",
        )
        self.add_shape(
            g,
            fid,
            "f1_summary",
            hbox(
                "CORE MISSION · 48-HOUR VOICE-TO-VOICE INTERVIEW COACH",
                "Eliminate technical interview freeze by putting an installable, zero-echo AI interviewer in the candidate's pocket using 100% Vanilla JS.",
            ),
            800,
            78,
            1500,
            86,
            fill=self.SLATE_SUB,
            border=self.SLATE_SUB,
            text_color=self.TEXT_LIGHT,
            font_size="15",
            text_align="center",
        )

        # Left column: Problem Statement + Scope Guardrails
        self.add_subheader(
            g, fid, "PROBLEM STATEMENT", 415, 165, 730, self.CRIMSON_BORDER
        )
        problems = [
            (
                "1. Interview Freeze Under Spoken Pressure",
                "Associate SWE candidates study OOP &amp; SQL passively, then freeze or ramble when asked to reason aloud under live interviewer follow-ups.",
                285,
            ),
            (
                "2. Text Chatbots Break Conversational Tempo",
                "Typing into chat tools removes verbal pacing, hides filler habits, and never trains the quick spoken recall needed in real interviews.",
                455,
            ),
            (
                "3. Mobile App Deliverable in 2 Days",
                "Must feel like a native mobile app via PWA (manifest.json + Service Worker) without spending sprint hours on React Native or app stores.",
                625,
            ),
        ]
        for title, body, py in problems:
            self.add_shape(
                g,
                fid,
                title,
                hbox(title, body),
                415,
                py,
                730,
                148,
                fill=self.CRIMSON_FILL,
                border=self.CRIMSON_BORDER,
                font_size="14",
            )

        self.add_subheader(
            g,
            fid,
            "SPRINT GUARDRAILS (IN vs OUT OF SCOPE)",
            415,
            760,
            730,
            self.SLATE_SUB,
        )
        self.add_shape(
            g,
            fid,
            "in_scope",
            (
                "<p><strong>IN-SCOPE (DAY 1–2 MVP)</strong></p>"
                "<p>• Domain selector: OOP &amp; Databases</p>"
                "<p>• Anti-echo onend STT ↔ TTS loop</p>"
                "<p>• Gemini 1.5 persona + history[]</p>"
                "<p>• Web Speech &amp; ElevenLabs toggle</p>"
                "<p>• Live transcript + debrief scorecard</p>"
                "<p>• PWA manifest.json + sw.js shell</p>"
            ),
            225,
            1040,
            350,
            460,
            fill=self.EMERALD_FILL,
            border=self.EMERALD_BORDER,
            font_size="15",
            text_align_vertical="middle",
        )
        self.add_shape(
            g,
            fid,
            "out_scope",
            (
                "<p><strong>OUT-OF-SCOPE (POST-MVP v2)</strong></p>"
                "<p>• Backend DB, auth, or user accounts</p>"
                "<p>• Full-duplex WebRTC interruption</p>"
                "<p>• Video / camera eye-contact scoring</p>"
                "<p>• Live collaborative code editor</p>"
                "<p>• Multi-language speech recognition</p>"
                "<p>• Native iOS / Android wrapper builds</p>"
            ),
            605,
            1040,
            350,
            460,
            fill=self.NEUTRAL_FILL,
            border=self.NEUTRAL_BORDER,
            border_style="dashed",
            font_size="15",
            text_align_vertical="middle",
        )

        # Right column: MVP Goals + Constraints
        self.add_subheader(
            g, fid, "MVP PROJECT GOALS", 1185, 165, 730, self.INDIGO_BORDER
        )
        goals = [
            (
                "Goal 1 · Deterministic Anti-Echo Voice Loop",
                "Strictly chain tts.onend → 200ms guard → stt.start() and stt.onend → Gemini → tts.speak() so the mic never hears the AI voice.",
                285,
                self.SKY_FILL,
                self.SKY_BORDER,
            ),
            (
                "Goal 2 · Installable Mobile-First PWA",
                "Ship manifest.json (standalone mode, 192/512 icons) and sw.js (app-shell cache) passing Chrome/Android installability.",
                455,
                self.VIOLET_FILL,
                self.VIOLET_BORDER,
            ),
            (
                "Goal 3 · Zero-Build Vanilla Velocity + TTS Swap",
                "Use zero-bundler ES modules with a clean TTS adapter interface: test rapidly on Web Speech API, then flip to ElevenLabs Turbo.",
                625,
                self.INDIGO_FILL,
                self.INDIGO_BORDER,
            ),
        ]
        for title, body, gy, fill, border in goals:
            self.add_shape(
                g,
                fid,
                title,
                hbox(title, body),
                1185,
                gy,
                730,
                148,
                fill=fill,
                border=border,
                font_size="14",
            )

        self.add_subheader(
            g, fid, "DESIGN & SPRINT CONSTRAINTS", 1185, 760, 730, self.AMBER_BORDER
        )
        self.add_sticky(
            g,
            fid,
            "sticky_timebox",
            "<p><strong>48-Hr Sprint Rule</strong></p><p>Zero React/Vite overhead. Core voice loop must work end-to-end by end of Day 1; Day 2 is ElevenLabs, PWA &amp; mobile QA.</p>",
            995,
            960,
            width=250,
            fill_color="yellow",
        )
        self.add_sticky(
            g,
            fid,
            "sticky_apikeys",
            "<p><strong>Client-Only MVP Keys</strong></p><p>Keys stored in runtime sessionStorage for demo speed. Production release requires a lightweight proxy endpoint.</p>",
            1375,
            960,
            width=250,
            fill_color="light_pink",
        )
        self.add_shape(
            g,
            fid,
            "f1_axiom",
            hbox(
                "ARCHITECTURAL AXIOM · SPOKEN BREVITY",
                "Prompt Gemini 1.5 to reply in max 2–3 spoken sentences + 1 sharp follow-up, stripped of Markdown symbols, to maximize realism and keep TTS latency low.",
            ),
            1185,
            1215,
            730,
            110,
            fill=self.AMBER_FILL,
            border=self.AMBER_BORDER,
            font_size="14",
        )

    def build_frame_02(self) -> None:
        fid, g = self.add_frame(
            "02 · Target Use Cases & Success Metrics",
            x=0,
            y=-160,
            w=1600,
            h=1340,
            fill="#F4FBF8",
        )
        self.add_shape(
            g,
            fid,
            "f2_summary",
            hbox(
                "PRIMARY PERSONA · ASSOCIATE SOFTWARE ENGINEER CANDIDATE",
                "Fresh graduates and junior engineers preparing for high-pressure technical phone/panel rounds covering OOP design and relational databases.",
            ),
            800,
            78,
            1500,
            86,
            fill=self.SLATE_SUB,
            border=self.SLATE_SUB,
            text_color=self.TEXT_LIGHT,
            font_size="15",
            text_align="center",
        )

        self.add_subheader(
            g, fid, "CORE TARGET USE CASES", 800, 165, 1500, self.EMERALD_BORDER
        )
        use_cases = [
            (
                "UC-1 · OOP Fundamentals & Design Probing",
                "Tests encapsulation, polymorphism, SOLID principles, and composition vs. inheritance. AI dynamically challenges vague definitions with 'Give me a concrete example.'",
                415,
                315,
                self.INDIGO_FILL,
                self.INDIGO_BORDER,
            ),
            (
                "UC-2 · Database & SQL Gauntlet",
                "Drills 1NF–BCNF normalization, ACID transactions, B-Tree index trade-offs, and join performance under realistic spoken time pressure.",
                1185,
                315,
                self.SKY_FILL,
                self.SKY_BORDER,
            ),
            (
                "UC-3 · Hands-Free Mobile PWA Practice",
                "Candidate launches the app from their phone Home Screen. One thumb-friendly Voice Orb displays real-time FSM state alongside readable captions.",
                415,
                545,
                self.VIOLET_FILL,
                self.VIOLET_BORDER,
            ),
            (
                "UC-4 · Structured 5-Turn Rubric Debrief",
                "Upon completing 5 turns (or tapping Finish), Gemini synthesizes an audio + visual scorecard: Technical Depth, Clarity, and Top Missed Concepts.",
                1185,
                545,
                self.EMERALD_FILL,
                self.EMERALD_BORDER,
            ),
        ]
        for title, body, ux, uy, fill, border in use_cases:
            self.add_shape(
                g,
                fid,
                title,
                hbox(title, body),
                ux,
                uy,
                730,
                200,
                fill=fill,
                border=border,
                font_size="14",
            )

        self.add_subheader(
            g,
            fid,
            "QUANTITATIVE MVP SUCCESS METRICS (KPIs)",
            800,
            705,
            1500,
            self.SLATE_SUB,
        )
        kpis = [
            (
                "KPI 1 · Turn Latency",
                "< 1.8 sec",
                "From stt.onend to first audible TTS playback using gemini-1.5-flash &amp; concise output budget.",
                225,
                self.SKY_FILL,
                self.SKY_BORDER,
            ),
            (
                "KPI 2 · Echo Loop Rate",
                "0.0% Echo",
                "Zero self-triggering turns across 20 consecutive speakerphone &amp; headset test cycles.",
                608,
                self.CRIMSON_FILL,
                self.CRIMSON_BORDER,
            ),
            (
                "KPI 3 · PWA Installability",
                "100% Pass",
                "Valid manifest.json, icons, HTTPS origin &amp; active sw.js passing Chrome Install prompt.",
                992,
                self.VIOLET_FILL,
                self.VIOLET_BORDER,
            ),
            (
                "KPI 4 · Full Loop Completion",
                "5-Turn Flow",
                "Complete Greet → 5 Technical Q&amp;As → Spoken Debrief under 8 minutes end-to-end.",
                1375,
                self.EMERALD_FILL,
                self.EMERALD_BORDER,
            ),
        ]
        for title, metric, desc, kx, fill, border in kpis:
            self.add_shape(
                g,
                fid,
                title,
                f"<p><strong>{title}</strong></p><p><strong>{metric}</strong></p><p>{desc}</p>",
                kx,
                890,
                345,
                265,
                fill=fill,
                border=border,
                font_size="14",
                text_align="center",
            )

        self.add_shape(
            g,
            fid,
            "f2_dod",
            hbox(
                "DEFINITION OF DONE · SPRINT ACCEPTANCE CHECKLIST",
                "1) Installable as standalone mobile PWA  ·  2) Web Speech ↔ ElevenLabs switchable via 1 config toggle  ·  3) Graceful recovery on mic denial, silence timeout, or API error  ·  4) End-of-session scorecard generated from Gemini history[].",
            ),
            800,
            1165,
            1500,
            180,
            fill="#FFFFFF",
            border=self.EMERALD_BORDER,
            font_size="15",
            text_align="center",
        )

    def build_frame_03(self) -> None:
        fid, g = self.add_frame(
            "03 · User Journey & Interview Loop Flowchart",
            x=1760,
            y=-160,
            w=1600,
            h=1340,
            fill="#F4F7FF",
        )
        self.add_shape(
            g,
            fid,
            "f3_summary",
            hbox(
                "END-TO-END CONVERSATIONAL USER JOURNEY",
                "Strict half-duplex turn-taking flow: user gesture unlocks mobile audio, then AI Speaking and User Listening alternate deterministically.",
            ),
            800,
            78,
            1500,
            86,
            fill=self.SLATE_SUB,
            border=self.SLATE_SUB,
            text_color=self.TEXT_LIGHT,
            font_size="15",
            text_align="center",
        )

        # Row A: Steps 1 -> 2 -> 3 -> 4 (145px horizontal gaps)
        s1 = self.add_shape(
            g,
            fid,
            "step_1",
            hbox(
                "1. Launch PWA",
                "Open Home Screen app; sw.js serves cached HTML/CSS/JS.",
            ),
            180,
            245,
            250,
            150,
            fill=self.VIOLET_FILL,
            border=self.VIOLET_BORDER,
            font_size="13",
        )
        s2 = self.add_shape(
            g,
            fid,
            "step_2",
            hbox(
                "2. Setup Track", "Pick OOP / DBMS, TTS Engine &amp; allow Mic access."
            ),
            575,
            245,
            250,
            150,
            fill=self.NEUTRAL_FILL,
            border=self.NEUTRAL_BORDER,
            font_size="13",
        )
        s3 = self.add_shape(
            g,
            fid,
            "step_3",
            hbox(
                "3. Tap Start", "User click unlocks AudioContext &amp; TTS on mobile."
            ),
            970,
            245,
            250,
            150,
            fill=self.AMBER_FILL,
            border=self.AMBER_BORDER,
            font_size="13",
        )
        s4 = self.add_shape(
            g,
            fid,
            "step_4",
            hbox("4. Gemini Q1", "System persona seeds history[] &amp; generates Q1."),
            1365,
            245,
            250,
            150,
            fill=self.INDIGO_FILL,
            border=self.INDIGO_BORDER,
            font_size="13",
        )

        # Row B: Step 7 <- Step 6 <- Step 5 (205-235px horizontal gaps)
        s5 = self.add_shape(
            g,
            fid,
            "step_5",
            hbox(
                "5. AI Speaks (SPEAKING)",
                "Mic forced ABORTED. TTS plays question; orb pulses blue.",
            ),
            1365,
            520,
            270,
            155,
            fill=self.SKY_FILL,
            border=self.SKY_BORDER,
            font_size="13",
        )
        s6 = self.add_shape(
            g,
            fid,
            "step_6",
            hbox(
                "6. Candidate Answers",
                "LISTENING: webkitSpeechRecognition captures final text.",
            ),
            845,
            520,
            300,
            155,
            fill=self.EMERALD_FILL,
            border=self.EMERALD_BORDER,
            font_size="13",
        )
        s7 = self.add_shape(
            g,
            fid,
            "step_7",
            hbox(
                "7. LLM Evaluates",
                "THINKING: Push user turn to history[]; Gemini probes.",
            ),
            340,
            520,
            300,
            155,
            fill=self.INDIGO_FILL,
            border=self.INDIGO_BORDER,
            font_size="13",
        )

        # Row C: Decision + Loop Node (210px gap)
        decision = self.add_shape(
            g,
            fid,
            "decision_turns",
            p("<strong>Turn &gt;= 5 or End?</strong>"),
            340,
            825,
            290,
            200,
            shape="rhombus",
            fill=self.AMBER_FILL,
            border=self.AMBER_BORDER,
            font_size="14",
            text_align="center",
        )
        s8a = self.add_shape(
            g,
            fid,
            "step_8a",
            hbox(
                "8A. Append Follow-Up",
                "Save model reply to history[]; prep next follow-up.",
            ),
            845,
            825,
            300,
            145,
            fill=self.INDIGO_FILL,
            border=self.INDIGO_BORDER,
            font_size="13",
        )

        # Row D: Final Debrief & Reset (190px gap)
        s8b = self.add_shape(
            g,
            fid,
            "step_8b",
            hbox(
                "8B. Debrief &amp; Scorecard",
                "AI speaks summary; UI shows Depth, Clarity &amp; Score/10.",
            ),
            340,
            1135,
            330,
            165,
            fill=self.EMERALD_FILL,
            border=self.EMERALD_BORDER,
            font_size="13",
        )
        s9 = self.add_shape(
            g,
            fid,
            "step_9",
            hbox(
                "9. Reset / New Track",
                "Clear history[] &amp; bump sessionGenId for next run.",
            ),
            845,
            1135,
            300,
            150,
            fill=self.NEUTRAL_FILL,
            border=self.NEUTRAL_BORDER,
            font_size="13",
        )

        # Side edge-case stickies
        self.add_sticky(
            g,
            fid,
            "sticky_autoplay",
            "<p><strong>Mobile Autoplay Fix</strong></p><p>iOS Safari &amp; Chrome block async Audio.play(). Step 3 click must unlock AudioContext &amp; play a silent utterance immediately.</p>",
            1375,
            840,
            width=245,
            fill_color="light_pink",
        )
        self.add_sticky(
            g,
            fid,
            "sticky_nospeech",
            "<p><strong>Silence / Mic Fallback</strong></p><p>If stt.onerror='no-speech' or permission denied, show 1-tap Re-arm Mic or Textbox fallback without dropping history[].</p>",
            1375,
            1145,
            width=245,
            fill_color="light_yellow",
        )

        # Connectors
        self.connect(s1, s2, start_snap="right", end_snap="left")
        self.connect(s2, s3, start_snap="right", end_snap="left")
        self.connect(
            s3,
            s4,
            caption="User Gesture",
            start_snap="right",
            end_snap="left",
            color=self.AMBER_BORDER,
        )
        self.connect(
            s4,
            s5,
            caption="Q1 Prompt",
            start_snap="bottom",
            end_snap="top",
            color=self.INDIGO_BORDER,
        )
        self.connect(
            s5,
            s6,
            caption="tts.onend + 200ms",
            start_snap="left",
            end_snap="right",
            color=self.SKY_BORDER,
        )
        self.connect(
            s6,
            s7,
            caption="stt.onend",
            start_snap="left",
            end_snap="right",
            color=self.EMERALD_BORDER,
        )
        self.connect(
            s7, decision, start_snap="bottom", end_snap="top", color=self.INDIGO_BORDER
        )
        self.connect(
            decision,
            s8a,
            caption="NO: Probe Deeper",
            start_snap="right",
            end_snap="left",
            color=self.INDIGO_BORDER,
        )
        self.connect(
            s8a,
            s5,
            caption="Next Q&A Turn",
            start_snap="top",
            end_snap="bottom",
            shape="elbowed",
            color=self.INDIGO_BORDER,
        )
        self.connect(
            decision,
            s8b,
            caption="YES: Wrap Up",
            start_snap="bottom",
            end_snap="top",
            color=self.EMERALD_BORDER,
        )
        self.connect(
            s8b,
            s9,
            caption="New Session",
            start_snap="right",
            end_snap="left",
            color=self.NEUTRAL_BORDER,
        )

    def build_frame_04(self) -> None:
        fid, g = self.add_frame(
            "04 · Technical Stack & Zero-Latency Architecture",
            x=-1760,
            y=1480,
            w=1600,
            h=1480,
            fill="#F8F5FF",
        )
        self.add_shape(
            g,
            fid,
            "f4_summary",
            hbox(
                "MODULAR VANILLA JS ARCHITECTURE · ZERO BUILD STEP",
                "4 decoupled layers keep PWA caching, anti-echo FSM orchestration, Gemini 1.5 reasoning, and swappable TTS providers cleanly isolated.",
            ),
            800,
            78,
            1500,
            86,
            fill=self.SLATE_SUB,
            border=self.SLATE_SUB,
            text_color=self.TEXT_LIGHT,
            font_size="15",
            text_align="center",
        )

        # Left-Margin Layer Badges (keeps vertical connector lanes 100% unobstructed)
        layer_badges = [
            ("LAYER 1<br/>PWA SHELL", 260, 170, self.VIOLET_BORDER),
            ("LAYER 2<br/>FSM &amp; STATE", 550, 170, self.SLATE_SUB),
            ("LAYER 3<br/>ADAPTERS", 845, 185, self.INDIGO_BORDER),
            ("LAYER 4<br/>TTS ENGINES", 1140, 175, self.SKY_BORDER),
        ]
        for label, ly, lh, accent in layer_badges:
            self.add_shape(
                g,
                fid,
                f"badge:{label}",
                p(f"<strong>{label}</strong>"),
                110,
                ly,
                136,
                lh,
                shape="round_rectangle",
                fill=accent,
                border=accent,
                text_color=self.TEXT_LIGHT,
                font_size="14",
                text_align="center",
            )

        # Layer 1
        l1a = self.add_shape(
            g,
            fid,
            "l1_ui",
            hbox(
                "index.html + styles.css",
                "Responsive mobile layout, animated FSM voice orb, live transcript feed, &amp; track/key settings drawer.",
            ),
            355,
            260,
            300,
            170,
            fill=self.VIOLET_FILL,
            border=self.VIOLET_BORDER,
            font_size="13",
        )
        l1b = self.add_shape(
            g,
            fid,
            "l1_manifest",
            hbox(
                "manifest.json",
                "display: standalone, orientation: portrait, theme_color, start_url: /, 192px &amp; 512px PNG icons.",
            ),
            700,
            260,
            300,
            170,
            fill=self.VIOLET_FILL,
            border=self.VIOLET_BORDER,
            font_size="13",
        )
        l1c = self.add_shape(
            g,
            fid,
            "l1_sw",
            hbox(
                "sw.js (Service Worker)",
                "Cache-First for static HTML/CSS/JS shell; Network-Only bypass for Gemini &amp; ElevenLabs API requests.",
            ),
            1045,
            260,
            300,
            170,
            fill=self.VIOLET_FILL,
            border=self.VIOLET_BORDER,
            font_size="13",
        )

        # Layer 2 (140px gap between FSM and Store for clean history[] label)
        l2a = self.add_shape(
            g,
            fid,
            "l2_fsm",
            hbox(
                "app.js · VoiceStateMachine",
                "Single source of truth for IDLE | SPEAKING | LISTENING | THINKING | ERROR, 200ms guard, &amp; sessionGenId token.",
            ),
            415,
            550,
            420,
            170,
            fill=self.AMBER_FILL,
            border=self.AMBER_BORDER,
            font_size="13",
        )
        l2b = self.add_shape(
            g,
            fid,
            "l2_store",
            hbox(
                "store.js · History[] &amp; Sanitizer",
                "Maintains Gemini contents[] array (capped at recent 10 turns), injects OOP/DBMS persona, strips Markdown before TTS.",
            ),
            980,
            550,
            430,
            170,
            fill=self.NEUTRAL_FILL,
            border=self.NEUTRAL_BORDER,
            font_size="13",
        )

        # Layer 3
        l3a = self.add_shape(
            g,
            fid,
            "l3_stt",
            hbox(
                "services/stt.js (Input)",
                "webkitSpeechRecognition with continuous=false, interimResults=true, explicit abort() hook.",
            ),
            355,
            845,
            300,
            185,
            fill=self.EMERALD_FILL,
            border=self.EMERALD_BORDER,
            font_size="13",
        )
        l3b = self.add_shape(
            g,
            fid,
            "l3_gemini",
            hbox(
                "services/gemini.js (Brain)",
                "Gemini 1.5 Flash generateContent REST API. Strict systemInstruction + maxOutputTokens (~160).",
            ),
            700,
            845,
            300,
            185,
            fill=self.INDIGO_FILL,
            border=self.INDIGO_BORDER,
            font_size="13",
        )
        l3c = self.add_shape(
            g,
            fid,
            "l3_tts",
            hbox(
                "services/tts.js (Adapter)",
                "Uniform speak(text, onEnd) &amp; stop() interface so providers swap cleanly with zero FSM changes.",
            ),
            1045,
            845,
            300,
            185,
            fill=self.SKY_FILL,
            border=self.SKY_BORDER,
            font_size="13",
        )

        # Layer 4
        l4a = self.add_shape(
            g,
            fid,
            "l4_webspeech",
            hbox(
                "Adapter A · Web Speech API (Day 1 Dev)",
                "window.speechSynthesis · Zero cost &amp; instant setup. Includes utterance keep-alive guard.",
            ),
            415,
            1140,
            420,
            175,
            fill=self.SKY_FILL,
            border=self.SKY_BORDER,
            font_size="13",
        )
        l4b = self.add_shape(
            g,
            fid,
            "l4_eleven",
            hbox(
                "Adapter B · ElevenLabs API (Day 2 Prod)",
                "eleven_turbo_v2_5 stream endpoint → audio/mpeg Blob → HTMLAudioElement.onended.",
            ),
            980,
            1140,
            430,
            175,
            fill=self.SKY_FILL,
            border=self.INDIGO_BORDER,
            font_size="13",
        )

        self.add_shape(
            g,
            fid,
            "l4_budget",
            hbox(
                "ZERO-LATENCY TURN BUDGET (< 1.8s PERCEIVED RESPONSE)",
                "stt.onend (0ms) → Gemini 1.5 Flash TTFT (~650–900ms) → ElevenLabs Turbo / Local TTS start (~200–700ms) → tts.onend + 200ms guard.",
            ),
            620,
            1355,
            1150,
            125,
            fill="#FFFFFF",
            border=self.INDIGO_BORDER,
            font_size="14",
            text_align="center",
        )

        # Right R&D Callout Column
        self.add_sticky(
            g,
            fid,
            "sticky_flash",
            "<p><strong>Why Gemini 1.5 Flash?</strong></p><p>Optimized for low TTFT in real-time voice loops. Capping answers to 2–3 sentences keeps TTS synthesis fast and natural.</p>",
            1390,
            295,
            width=250,
            fill_color="light_green",
        )
        self.add_sticky(
            g,
            fid,
            "sticky_sanitizer",
            "<p><strong>Strip Markdown!</strong></p><p>stripMarkdown() removes **, `, #, and bullets before TTS so speech synthesis never reads 'asterisk' aloud.</p>",
            1390,
            620,
            width=250,
            fill_color="cyan",
        )
        self.add_sticky(
            g,
            fid,
            "sticky_sw_rule",
            "<p><strong>Service Worker Rule</strong></p><p>Never cache POST API calls to Gemini or ElevenLabs inside sw.js; cache static shell assets only.</p>",
            1390,
            945,
            width=250,
            fill_color="light_blue",
        )
        self.add_shape(
            g,
            fid,
            "f4_security",
            hbox(
                "API KEY SECURITY",
                "MVP stores user-entered keys in sessionStorage. Add a serverless proxy before public release.",
            ),
            1390,
            1295,
            310,
            200,
            fill=self.CRIMSON_FILL,
            border=self.CRIMSON_BORDER,
            font_size="13",
        )

        # Connectors
        self.connect(
            l1a,
            l2a,
            caption="UI Actions",
            start_snap="bottom",
            end_snap="top",
            color=self.VIOLET_BORDER,
        )
        self.connect(
            l2a,
            l2b,
            caption="history[]",
            start_snap="right",
            end_snap="left",
            color=self.SLATE_SUB,
        )
        self.connect(
            l2a,
            l3a,
            caption="start/abort",
            start_snap="bottom",
            end_snap="top",
            color=self.EMERALD_BORDER,
        )
        self.connect(
            l2a,
            l3b,
            caption="generateTurn",
            start_snap="bottom",
            end_snap="top",
            color=self.INDIGO_BORDER,
        )
        self.connect(
            l2a,
            l3c,
            caption="speak(text)",
            start_snap="bottom",
            end_snap="top",
            color=self.SKY_BORDER,
        )
        self.connect(
            l3c,
            l4a,
            caption="Dev Mode",
            start_snap="bottom",
            end_snap="top",
            color=self.SKY_BORDER,
        )
        self.connect(
            l3c,
            l4b,
            caption="Prod Mode",
            start_snap="bottom",
            end_snap="top",
            color=self.INDIGO_BORDER,
        )

    def build_frame_05(self) -> None:
        fid, g = self.add_frame(
            "05 · Anti-Echo JavaScript State Machine (FSM)",
            x=0,
            y=1480,
            w=1600,
            h=1480,
            fill="#FFFDF2",
        )
        self.add_shape(
            g,
            fid,
            "f5_summary",
            hbox(
                "CORE ARCHITECTURAL CHALLENGE · ZERO-ECHO HALF-DUPLEX LOCK",
                "If STT stays active during TTS playback, the mic records the AI's own voice and triggers an infinite self-interview loop. Strict onend chaining eliminates this.",
            ),
            800,
            78,
            1500,
            86,
            fill=self.SLATE_SUB,
            border=self.SLATE_SUB,
            text_color=self.TEXT_LIGHT,
            font_size="15",
            text_align="center",
        )

        idle = self.add_shape(
            g,
            fid,
            "fsm_idle",
            hbox(
                "STATE: IDLE",
                "• Mic: OFF (stopped)<br/>• Audio: SILENT<br/>• Awaits Start button tap",
            ),
            220,
            285,
            310,
            170,
            fill="#F1F5F9",
            border="#475569",
            font_size="14",
        )
        speaking = self.add_shape(
            g,
            fid,
            "fsm_speaking",
            hbox(
                "STATE: SPEAKING",
                "• Entry: stt.abort() FIRST!<br/>• tts.speak(cleanText)<br/>• Mic strictly locked OFF",
            ),
            865,
            285,
            340,
            170,
            fill=self.SKY_FILL,
            border=self.SKY_BORDER,
            font_size="14",
        )
        listening = self.add_shape(
            g,
            fid,
            "fsm_listening",
            hbox(
                "STATE: LISTENING",
                "• Entered 200ms post-onend<br/>• stt.start() (continuous=false)<br/>• Live interim captions",
            ),
            1365,
            530,
            330,
            180,
            fill=self.EMERALD_FILL,
            border=self.EMERALD_BORDER,
            font_size="14",
        )
        thinking = self.add_shape(
            g,
            fid,
            "fsm_thinking",
            hbox(
                "STATE: THINKING",
                "• Mic OFF &amp; Audio OFF<br/>• fetch(Gemini 1.5) in flight<br/>• Guards stale genId",
            ),
            865,
            735,
            340,
            170,
            fill=self.AMBER_FILL,
            border=self.AMBER_BORDER,
            font_size="14",
        )
        error = self.add_shape(
            g,
            fid,
            "fsm_error",
            hbox(
                "STATE: ERROR",
                "• Mic denied / Network / 429<br/>• Preserves history[]<br/>• Offers Retry or Reset",
            ),
            220,
            795,
            310,
            170,
            fill=self.CRIMSON_FILL,
            border=self.CRIMSON_BORDER,
            font_size="14",
        )

        # FSM Transition Connectors (320px horizontal gap for parallel IDLE<->SPEAKING lanes; non-crossing curved error route)
        self.connect(
            idle,
            speaking,
            caption="1. Start Tap (Unlock + Q1)",
            start_pos=("100%", "72%"),
            end_pos=("0%", "72%"),
            shape="straight",
            color=self.SKY_BORDER,
        )
        self.connect(
            speaking,
            listening,
            caption="2. tts.onend + 200ms Guard",
            start_snap="right",
            end_snap="top",
            shape="curved",
            color=self.EMERALD_BORDER,
        )
        self.connect(
            listening,
            thinking,
            caption="3. stt.onend (non-empty text)",
            start_snap="left",
            end_snap="right",
            shape="elbowed",
            color=self.AMBER_BORDER,
        )
        self.connect(
            thinking,
            speaking,
            caption="4. Gemini 200 OK (Sanitized)",
            start_snap="top",
            end_snap="bottom",
            color=self.INDIGO_BORDER,
        )
        self.connect(
            speaking,
            idle,
            caption="Stop / Debrief Complete",
            start_pos=("0%", "28%"),
            end_pos=("100%", "28%"),
            shape="straight",
            style="dashed",
            color="#475569",
        )
        self.connect(
            thinking,
            error,
            caption="API Fail / Timeout",
            start_snap="left",
            end_snap="right",
            style="dashed",
            color=self.CRIMSON_BORDER,
        )
        self.connect(
            listening,
            error,
            caption="Mic Denied / Fatal STT",
            start_snap="bottom",
            end_snap="bottom",
            shape="elbowed",
            style="dashed",
            color=self.CRIMSON_BORDER,
        )
        self.connect(
            error,
            idle,
            caption="User Reset",
            start_snap="top",
            end_snap="bottom",
            style="dashed",
            color="#475569",
        )

        # 5 Ironclad Anti-Echo Invariants
        self.add_subheader(
            g,
            fid,
            "5 IRONCLAD ANTI-ECHO & CONCURRENCY INVARIANTS",
            800,
            1015,
            1500,
            self.CRIMSON_BORDER,
        )
        invariants = [
            (
                "1 · Mutual Exclusion",
                "stt.start() is forbidden unless state === 'LISTENING'. Entering SPEAKING always calls recognition.abort() synchronously first.",
                185,
            ),
            (
                "2 · Non-Continuous STT",
                "Set continuous = false so the browser releases the microphone automatically on utterance end instead of lingering open.",
                492,
            ),
            (
                "3 · 200ms Tail Guard",
                "Wait 200ms after tts.onend before starting STT to absorb room reverb, speaker decay, and Bluetooth HFP profile switch lag.",
                800,
            ),
            (
                "4 · Generation Token",
                "Increment sessionGenId on every Stop/Reset. Async tts.onend, stt.onend, and fetch callbacks discard stale generations.",
                1108,
            ),
            (
                "5 · Empty Input Guard",
                "If stt.onend returns blank transcript (no-speech), never call Gemini. Re-prompt gently or pause safely in IDLE.",
                1415,
            ),
        ]
        for title, body, ix in invariants:
            self.add_shape(
                g,
                fid,
                title,
                hbox(title, body),
                ix,
                1240,
                282,
                310,
                fill=self.CRIMSON_FILL,
                border=self.CRIMSON_BORDER,
                font_size="14",
                text_align_vertical="middle",
            )

    def build_frame_06(self) -> None:
        fid, g = self.add_frame(
            "06 · 2-Day Sprint Plan & Technical Risk Matrix",
            x=1760,
            y=1480,
            w=1600,
            h=1480,
            fill="#F4F8FA",
        )
        self.add_shape(
            g,
            fid,
            "f6_summary",
            hbox(
                "48-HOUR SPRINT ROADMAP & RISK MITIGATION",
                "Vertical slice playable on Day 1 (Web Speech + Gemini 1.5); ElevenLabs premium voice, PWA packaging, and mobile acoustic QA on Day 2.",
            ),
            800,
            78,
            1500,
            86,
            fill=self.SLATE_SUB,
            border=self.SLATE_SUB,
            text_color=self.TEXT_LIGHT,
            font_size="15",
            text_align="center",
        )

        # Day 1 & Day 2 Columns (240px wide center aisle between columns for clean handoff label)
        self.add_subheader(
            g,
            fid,
            "DAY 1 · CORE VOICE LOOP & GEMINI BRAIN",
            365,
            165,
            630,
            self.INDIGO_BORDER,
        )
        d1_1 = self.add_shape(
            g,
            fid,
            "d1_block1",
            hbox(
                "Hrs 1–3 · PWA Shell &amp; FSM Skeleton",
                "Create index.html, styles.css, mobile-first Voice Orb UI, transcript log, &amp; VoiceStateMachine.",
            ),
            365,
            290,
            630,
            155,
            fill=self.VIOLET_FILL,
            border=self.VIOLET_BORDER,
            font_size="14",
        )
        d1_2 = self.add_shape(
            g,
            fid,
            "d1_block2",
            hbox(
                "Hrs 4–6 · Anti-Echo onend Loop Proof",
                "Wire stt.js + Web Speech tts.js with 200ms tail guard &amp; generation token. Prove 0% echo loops.",
            ),
            365,
            475,
            630,
            155,
            fill=self.EMERALD_FILL,
            border=self.EMERALD_BORDER,
            font_size="14",
        )
        d1_3 = self.add_shape(
            g,
            fid,
            "d1_block3",
            hbox(
                "Hrs 7–10 · Gemini 1.5 Interviewer Brain",
                "Connect gemini-1.5-flash, OOP &amp; DBMS system prompts, rolling history[], &amp; Markdown stripper.",
            ),
            365,
            660,
            630,
            155,
            fill=self.INDIGO_FILL,
            border=self.INDIGO_BORDER,
            font_size="14",
        )

        self.add_subheader(
            g,
            fid,
            "DAY 2 · ELEVENLABS, PWA PACKAGING & MOBILE QA",
            1235,
            165,
            630,
            self.SKY_BORDER,
        )
        d2_1 = self.add_shape(
            g,
            fid,
            "d2_block1",
            hbox(
                "Hrs 11–14 · ElevenLabs TTS &amp; Debrief UI",
                "Plug in ElevenLabs Turbo v2.5 (audio.onended), TTS switcher, &amp; end-of-session scorecard.",
            ),
            1235,
            290,
            630,
            155,
            fill=self.SKY_FILL,
            border=self.SKY_BORDER,
            font_size="14",
        )
        d2_2 = self.add_shape(
            g,
            fid,
            "d2_block2",
            hbox(
                "Hrs 15–17 · PWA Manifest &amp; Service Worker",
                "Author manifest.json, 192/512 PNG icons, sw.js shell cache, HTTPS deploy &amp; Lighthouse audit.",
            ),
            1235,
            475,
            630,
            155,
            fill=self.VIOLET_FILL,
            border=self.VIOLET_BORDER,
            font_size="14",
        )
        d2_3 = self.add_shape(
            g,
            fid,
            "d2_block3",
            hbox(
                "Hrs 18–20 · Mobile Acoustic QA &amp; Demo",
                "Test Android Chrome &amp; iOS Safari on speakerphone vs Bluetooth buds; tune tail delay &amp; demo.",
            ),
            1235,
            660,
            630,
            155,
            fill=self.EMERALD_FILL,
            border=self.EMERALD_BORDER,
            font_size="14",
        )

        self.connect(
            d1_1, d1_2, start_snap="bottom", end_snap="top", color=self.INDIGO_BORDER
        )
        self.connect(
            d1_2, d1_3, start_snap="bottom", end_snap="top", color=self.INDIGO_BORDER
        )
        self.connect(
            d1_3,
            d2_1,
            caption="Day 1 Ready",
            start_snap="right",
            end_snap="left",
            color=self.INDIGO_BORDER,
        )
        self.connect(
            d2_1, d2_2, start_snap="bottom", end_snap="top", color=self.SKY_BORDER
        )
        self.connect(
            d2_2, d2_3, start_snap="bottom", end_snap="top", color=self.SKY_BORDER
        )

        # Risk Matrix
        self.add_subheader(
            g,
            fid,
            "TECHNICAL RISK MATRIX & MITIGATIONS",
            800,
            815,
            1500,
            self.CRIMSON_BORDER,
        )
        risks = [
            (
                "Risk 1 · Browser STT Gaps",
                "HIGH · webkitSpeechRecognition is absent in Firefox &amp; quirky on iOS Safari.<br/><strong>Mitigation:</strong> Feature-detect on load + seamless text-input fallback.",
                225,
            ),
            (
                "Risk 2 · Chrome 15s TTS Cutoff",
                "MED · Desktop speechSynthesis stalls on long strings.<br/><strong>Mitigation:</strong> Cap Gemini to 2–3 sentences + use ElevenLabs for prod.",
                608,
            ),
            (
                "Risk 3 · iOS Autoplay Block",
                "HIGH · Async Audio.play() fails without user gesture.<br/><strong>Mitigation:</strong> Unlock AudioContext inside initial Start click handler.",
                992,
            ),
            (
                "Risk 4 · Bluetooth HFP Lag",
                "MED · Earbuds take 150–400ms switching A2DP→Mic.<br/><strong>Mitigation:</strong> Tunable 250ms post-onend delay + visual mic-ready pulse.",
                1375,
            ),
        ]
        for title, body, rx in risks:
            self.add_shape(
                g,
                fid,
                title,
                hbox(title, body),
                rx,
                1045,
                345,
                310,
                fill=self.CRIMSON_FILL,
                border=self.CRIMSON_BORDER,
                font_size="14",
                text_align_vertical="middle",
            )

        self.add_shape(
            g,
            fid,
            "f6_tree",
            hbox(
                "TARGET MVP REPOSITORY STRUCTURE (100% VANILLA JS + PWA)",
                "/index.html  ·  /styles.css  ·  /app.js  ·  /store.js  ·  /manifest.json  ·  /sw.js  ·  /icons/icon-{192,512}.png  ·  /services/{stt.js, gemini.js, tts.js}",
            ),
            800,
            1335,
            1500,
            155,
            fill=self.SLATE_DARK,
            border="#38BDF8",
            text_color=self.TEXT_LIGHT,
            font_size="15",
            text_align="center",
        )

    def build_all(self, clear_existing: bool = True) -> dict:
        if clear_existing:
            deleted = self.client.clear_board()
            print(f"Cleared {deleted} existing board items.")

        self.client.update_board(
            name="Voice Coach PWA — MVP & System Architecture",
            description=(
                "2-Day Sprint MVP & Technical Architecture Board for Voice-to-Voice Mock Interviewer PWA "
                "(Vanilla JS, PWA manifest + Service Worker, Web Speech STT, Gemini 1.5, ElevenLabs TTS, Anti-Echo FSM)."
            ),
        )

        self.build_banner()
        self.build_frame_01()
        self.build_frame_02()
        self.build_frame_03()
        self.build_frame_04()
        self.build_frame_05()
        self.build_frame_06()

        board = self.client.get_board()
        summary = {
            "board_id": board.get("id"),
            "board_name": board.get("name"),
            "view_link": board.get("viewLink"),
            "total_created": len(self.created_items),
            "counts_by_type": {
                kind: sum(1 for it in self.created_items if it["type"] == kind)
                for kind in sorted({it["type"] for it in self.created_items})
            },
        }
        return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Populate Miro Voice Coach PWA planning board."
    )
    parser.add_argument(
        "--keep-existing",
        action="store_true",
        help="Do not delete existing items before creating the new board.",
    )
    parser.add_argument(
        "--manifest-out",
        type=Path,
        default=Path(__file__).resolve().parent / "outputs" / "board_manifest.json",
        help="Path to write JSON summary of created Miro items.",
    )
    args = parser.parse_args()

    client = MiroClient.from_env()
    builder = BoardBuilder(client)
    summary = builder.build_all(clear_existing=not args.keep_existing)
    args.manifest_out.parent.mkdir(parents=True, exist_ok=True)
    args.manifest_out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
