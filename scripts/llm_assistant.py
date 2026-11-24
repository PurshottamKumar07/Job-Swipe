"""
LLM Assistant Module
====================
Provides AI assistance for screening questions, form filling decisions,
and tailored resume generation using Hugging Face (Qwen2.5-3B-Instruct)
with smart local fallback heuristics and optional Gemini support.
"""

import os
import re
import json
from pathlib import Path
from typing import Any, Optional

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PROFILE_PATH = _REPO_ROOT / "profile.json"
DEFAULT_HF_MODEL = "Qwen/Qwen2.5-3B-Instruct"


class LLMAssistant:
    """
    Coordinates LLM completions for screening questions, resume customization,
    and cover letter generation using Qwen2.5-3B-Instruct via Hugging Face.
    """

    def __init__(
        self,
        profile: dict[str, Any] | None = None,
        model: str | None = None,
        hf_token: str | None = None,
    ):
        self.profile = profile or self._load_profile()
        self.qa_bank = self.profile.get("qa_bank", {})
        self.model = model or os.environ.get("HF_MODEL", DEFAULT_HF_MODEL)
        self.hf_token = hf_token or self._get_hf_token()
        self.gemini_key = self._get_gemini_key()

    def _load_profile(self) -> dict[str, Any]:
        if _PROFILE_PATH.exists():
            with open(_PROFILE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _get_hf_token(self) -> str | None:
        """Fetch Hugging Face token from environment or .env file."""
        for key_name in ("HF_TOKEN", "HUGGINGFACE_API_KEY", "HUGGING_FACE_HUB_TOKEN"):
            val = os.environ.get(key_name, "").strip()
            if val:
                return val

        env_path = _REPO_ROOT / ".env"
        if env_path.exists():
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    for key_name in ("HF_TOKEN", "HUGGINGFACE_API_KEY", "HUGGING_FACE_HUB_TOKEN"):
                        if line.startswith(f"{key_name}="):
                            token = line.split("=", 1)[1].strip().strip('"').strip("'")
                            if token:
                                return token
        return None

    def _get_gemini_key(self) -> str | None:
        key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not key:
            env_path = _REPO_ROOT / ".env"
            if env_path.exists():
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("GEMINI_API_KEY="):
                            key = line.split("=", 1)[1].strip().strip('"').strip("'")
                            break
        return key or None

    async def query_llm(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 512,
        temperature: float = 0.3,
    ) -> str | None:
        """
        Query Qwen2.5-3B-Instruct via Hugging Face Inference API router.
        Falls back to Gemini if configured, or None on failure.
        """
        import httpx

        # 1. Primary: Hugging Face Router (OpenAI-compatible)
        if self.hf_token:
            headers = {
                "Authorization": f"Bearer {self.hf_token}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }

            # Try Hugging Face OpenAI-compatible inference router
            url = "https://router.huggingface.co/hf-inference/v1/chat/completions"
            try:
                async with httpx.AsyncClient(timeout=25.0) as client:
                    resp = await client.post(url, headers=headers, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        choices = data.get("choices", [])
                        if choices:
                            return choices[0]["message"]["content"].strip()
            except Exception as e:
                print(f"[llm_assistant] HF router error ({self.model}): {e}")

            # Fallback to direct model inference endpoint
            legacy_url = f"https://api-inference.huggingface.co/models/{self.model}/v1/chat/completions"
            try:
                async with httpx.AsyncClient(timeout=25.0) as client:
                    resp = await client.post(legacy_url, headers=headers, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        choices = data.get("choices", [])
                        if choices:
                            return choices[0]["message"]["content"].strip()
            except Exception as e:
                print(f"[llm_assistant] HF legacy inference error: {e}")

        # 2. Secondary fallback: Gemini API if key is present
        if self.gemini_key:
            try:
                combined_prompt = "\n\n".join(
                    f"{m['role'].upper()}: {m['content']}" for m in messages
                )
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.gemini_key}"
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.post(
                        url,
                        json={
                            "contents": [{"parts": [{"text": combined_prompt}]}],
                            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
                        },
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
            except Exception as e:
                print(f"[llm_assistant] Gemini fallback error: {e}")

        return None

    # ------------------------------------------------------------------
    # Job Application Screening Q&A
    # ------------------------------------------------------------------

    async def answer_question(
        self,
        question_text: str,
        options: list[str] | None = None,
        field_type: str = "text",
        job_context: dict[str, Any] | None = None,
    ) -> str:
        """
        Produce a tailored answer for a form screening question.
        Checks QA bank first, then queries Qwen2.5-3B-Instruct,
        falling back to heuristics.
        """
        q_clean = question_text.lower().strip()

        # 1. Direct QA Bank Pattern Lookup
        for key, ans in self.qa_bank.items():
            k_clean = key.lower()
            if k_clean in q_clean or q_clean in k_clean:
                if options:
                    best_match = self._match_closest_option(ans, options)
                    if best_match:
                        return best_match
                return str(ans)

        # 2. Common HR heuristic rule matches
        if "authorized to work" in q_clean or "legally authorized" in q_clean:
            return self._choose_option(["Yes", "True", "I am authorized"], options) or "Yes"
        if "require sponsorship" in q_clean or "visa sponsorship" in q_clean:
            return self._choose_option(["No", "False", "I do not require sponsorship"], options) or "No"
        if "willing to relocate" in q_clean:
            return self._choose_option(["Yes", "True"], options) or "Yes"
        if "years of experience" in q_clean:
            for s in self.profile.get("skills", []):
                s_name = s.get("name", "").lower() if isinstance(s, dict) else str(s).lower()
                if s_name and s_name in q_clean:
                    return "2"
            return "2"

        # 3. Query Qwen2.5-3B-Instruct
        system_msg = (
            "You are an assistant answering job application form screening questions for an applicant. "
            "Output ONLY the exact answer without explanations, quotes, or conversational filler."
        )
        user_prompt = f"""Applicant Profile:
{json.dumps(self.profile, indent=2)}

Job Details:
{json.dumps(job_context or {}, indent=2)}

Question: {question_text}
Available Options: {options if options else 'Free text'}
Field Type: {field_type}

Instructions:
- If options are provided, select EXACTLY one of the provided options. Output ONLY that option.
- If it is a numeric question (e.g. years of experience), output ONLY the integer.
- If it is a short answer question, keep it concise, professional, and positive."""

        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_prompt},
        ]

        llm_reply = await self.query_llm(messages, max_tokens=100, temperature=0.1)
        if llm_reply:
            cleaned = llm_reply.strip()
            if options:
                matched = self._match_closest_option(cleaned, options)
                return matched or cleaned
            return cleaned

        # 4. Fallback default
        if options:
            return options[0]
        return "2" if "year" in q_clean else "Yes"

    # ------------------------------------------------------------------
    # Resume Tailoring (Qwen2.5-3B-Instruct)
    # ------------------------------------------------------------------

    async def tailor_summary(
        self,
        job_title: str,
        company: str,
        job_description: str,
        matched_skills: list[str],
    ) -> str:
        """
        Rewrite or enhance the professional summary for a target job.
        Uses Qwen2.5-3B-Instruct to highlight relevant skills.
        """
        base_summary = self.profile.get("summary", "")
        if not self.hf_token and not self.gemini_key:
            return base_summary

        system_msg = (
            "You are a professional resume writer. Write a concise, powerful 2-3 sentence "
            "professional summary tailored directly to the target job and company. "
            "Focus on the candidate's core strengths and matched technologies. Do not invent false experience. "
            "Output ONLY the summary paragraph with no preamble."
        )
        user_prompt = f"""Candidate Base Summary:
{base_summary}

Target Job Title: {job_title}
Target Company: {company}
Key Matched Skills: {', '.join(matched_skills[:8])}

Job Description Snippet:
{job_description[:1200] if job_description else 'N/A'}

Write an impactful 2-sentence summary targeting this position:"""

        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_prompt},
        ]

        tailored = await self.query_llm(messages, max_tokens=150, temperature=0.3)
        return tailored if tailored else base_summary

    async def tailor_experience_bullets(
        self,
        job_title: str,
        company: str,
        job_description: str,
        matched_skills: list[str],
        experience_items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Tailor work experience bullet points using Qwen2.5-3B-Instruct
        to emphasize keywords and technologies relevant to the role.
        """
        if not experience_items or (not self.hf_token and not self.gemini_key):
            return experience_items

        system_msg = (
            "You are an ATS resume optimizer. Optimize the candidate's work experience bullet points "
            "to emphasize technologies and accomplishments relevant to the target job description. "
            "Maintain professional action verbs (e.g., Architected, Optimized, Led). "
            "Return the output as a valid JSON array of objects with 'company' and 'bullets' (list of strings). "
            "Return ONLY valid JSON."
        )

        input_data = [
            {"company": exp.get("company"), "role": exp.get("role"), "bullets": exp.get("bullets", [])}
            for exp in experience_items
        ]

        user_prompt = f"""Target Role: {job_title} at {company}
Matched Skills: {', '.join(matched_skills[:8])}
Job Description:
{job_description[:1000] if job_description else 'N/A'}

Candidate Experience to Optimize:
{json.dumps(input_data, indent=2)}

Return optimized JSON with the same structure:"""

        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_prompt},
        ]

        reply = await self.query_llm(messages, max_tokens=600, temperature=0.2)
        if reply:
            try:
                # Strip any markdown fences
                clean_json = re.sub(r"^```(?:json)?\s*|\s*```$", "", reply.strip())
                parsed = json.loads(clean_json)
                if isinstance(parsed, list):
                    # Merge optimized bullets back into original experience objects
                    updated = []
                    for i, orig in enumerate(experience_items):
                        copy_exp = dict(orig)
                        if i < len(parsed) and "bullets" in parsed[i]:
                            copy_exp["bullets"] = parsed[i]["bullets"]
                        updated.append(copy_exp)
                    return updated
            except Exception as e:
                print(f"[llm_assistant] Failed to parse tailored bullets JSON: {e}")

        return experience_items

    async def generate_cover_letter(
        self,
        job_title: str,
        company: str,
        job_description: str,
        matched_skills: list[str],
    ) -> str:
        """
        Generate a compelling, personalized cover letter using Qwen2.5-3B-Instruct.
        """
        personal = self.profile.get("personal", {})
        candidate_name = personal.get("name", "Applicant")
        candidate_email = personal.get("email", "")
        candidate_phone = personal.get("phone", "")

        if not self.hf_token and not self.gemini_key:
            # Deterministic fallback
            top_skills = ", ".join(matched_skills[:5])
            return f"""Dear Hiring Team at {company},

I am writing to express my enthusiastic interest in the {job_title} position. With my background in modern software engineering and hands-on proficiency in {top_skills}, I am well prepared to deliver immediate value to your team.

Throughout my experience, I have focused on building performant, reliable systems, writing test-driven code, and collaborating on end-to-end features. The engineering challenges at {company} align closely with my technical foundation and professional drive.

I look forward to discussing how my experience with {top_skills} can support your technical objectives. Thank you for your time and consideration.

Sincerely,
{candidate_name}
{candidate_phone} | {candidate_email}
"""

        system_msg = (
            "You are an expert career advisor. Write a concise, professional 3-paragraph cover letter "
            "for the applicant targeting the specified role and company. "
            "Highlight their matched skills and explain how they can solve challenges for the company. "
            "Do not include placeholders like '[Insert Date]'. Output ONLY the cover letter text."
        )

        user_prompt = f"""Candidate Profile:
Name: {candidate_name}
Email: {candidate_email}
Phone: {candidate_phone}
Core Skills: {', '.join(matched_skills[:8])}
Summary: {self.profile.get('summary', '')}

Target Job Title: {job_title}
Target Company: {company}
Job Description:
{job_description[:1000] if job_description else 'N/A'}

Generate the cover letter:"""

        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_prompt},
        ]

        reply = await self.query_llm(messages, max_tokens=450, temperature=0.3)
        return reply.strip() if reply else ""

    # ------------------------------------------------------------------
    # Utility Helpers
    # ------------------------------------------------------------------

    def _match_closest_option(self, target: str, options: list[str]) -> str | None:
        target_lower = str(target).lower().strip()
        for opt in options:
            if opt.lower().strip() == target_lower:
                return opt
        for opt in options:
            if target_lower in opt.lower() or opt.lower() in target_lower:
                return opt
        return options[0] if options else None

    def _choose_option(self, candidates: list[str], options: list[str] | None) -> str | None:
        if not options:
            return candidates[0] if candidates else None
        for c in candidates:
            match = self._match_closest_option(c, options)
            if match:
                return match
        return None
