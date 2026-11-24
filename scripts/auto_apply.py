"""
Playwright Job Auto-Applier Engine
===================================
Automates job applications across LinkedIn Easy Apply, Indeed, and external ATS portals
with human-in-the-loop pause on CAPTCHAs, skill review per application,
dynamic resume & cover letter generation, and conservative rate limiting.
"""

import os
import sys
import re
import json
import random
import asyncio
import platform
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Optional

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.db import Database
from scripts.resume_builder import ResumeBuilder
from scripts.llm_assistant import LLMAssistant

# Platform specific notifications
def send_desktop_notification(title: str, message: str) -> None:
    """Trigger a desktop toast notification and audio chime."""
    try:
        if platform.system() == "Windows":
            # Audio alert
            try:
                import winsound
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            except Exception:
                pass

            # Safe parameterized PowerShell toast notification (prevents command injection)
            ps_script = """
            param([string]$toastTitle, [string]$toastMessage)
            [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
            $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
            $textNodes = $template.GetElementsByTagName("text")
            $textNodes.Item(0).AppendChild($template.CreateTextNode($toastTitle)) > $null
            $textNodes.Item(1).AppendChild($template.CreateTextNode($toastMessage)) > $null
            $toast = [Windows.UI.Notifications.ToastNotification::new($template)]
            [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("crwlr Auto-Apply").Show($toast)
            """
            subprocess.Popen(
                ["powershell", "-NoProfile", "-Command", ps_script, str(title), str(message)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except Exception as e:
        print(f"[notification warning] Could not show desktop toast: {e}")


class AutoApplyEngine:
    """Coordinates Playwright browser sessions, skill reviews, and application workflows."""

    def __init__(self, db: Database | None = None, profile_path: str | Path | None = None):
        self.db = db or Database()
        self.resume_builder = ResumeBuilder(profile_path)
        self.profile = self.resume_builder.profile
        self.llm = LLMAssistant(self.profile)
        self.session_id: Optional[int] = None

        # State tracking & synchronization
        self.status: str = "idle" # idle | running | paused_skill_review | paused_captcha | completed | stopped
        self.current_job: Optional[dict[str, Any]] = None
        self.pause_event = asyncio.Event()
        self.pause_event.set() # Set means not paused
        self.user_decision: Optional[dict[str, Any]] = None
        self.stop_requested: bool = False

    async def log(self, event_type: str, message: str, job_id: Optional[int] = None, metadata: Optional[dict] = None):
        """Append log to database and console."""
        print(f"[auto_apply:{event_type}] {message}")
        try:
            self.db.add_auto_apply_log(
                session_id=self.session_id,
                job_id=job_id,
                event_type=event_type,
                message=message,
                metadata=json.dumps(metadata) if metadata else None,
            )
        except Exception as e:
            print(f"[auto_apply log error] {e}")

    async def pause_for_skill_review(self, job: dict[str, Any], match_data: dict[str, Any]) -> dict[str, Any]:
        """
        Pauses the workflow and alerts the user to review/adjust the matched skills
        before generating the tailored resume.
        """
        self.status = "paused_skill_review"
        self.current_job = job
        cover_letter = self.resume_builder.generate_cover_letter(
            job.get("title") or "Software Engineer",
            job.get("company") or "Company",
            match_data.get("matched_skills", []),
        )
        pause_data = {
            "type": "skill_review",
            "job_id": job["id"],
            "job_title": job.get("title"),
            "company": job.get("company"),
            "location": job.get("location"),
            "match_score": match_data.get("match_score"),
            "matched_skills": match_data.get("matched_skills"),
            "missing_skills": match_data.get("missing_skills"),
            "all_user_skills": match_data.get("all_user_skills"),
            "cover_letter": cover_letter,
            "apply_url": job.get("apply_url") or job.get("source_url"),
        }

        if self.session_id:
            self.db.update_auto_apply_session(
                self.session_id,
                status="paused_skill_review",
                current_job_id=job["id"],
                pause_data=json.dumps(pause_data),
            )

        await self.log("paused_skill_review", f"Waiting for user skill review on: {job.get('title')} at {job.get('company')}", job["id"], pause_data)
        send_desktop_notification("Skill Review Needed", f"{job.get('company')} — {job.get('title')}: {match_data.get('match_score')}% Match. Review skills in crwlr.")

        # Clear event and wait for user resume
        self.pause_event.clear()
        await self.pause_event.wait()

        decision = self.user_decision or {"action": "approve", "skills": match_data.get("matched_skills")}
        self.user_decision = None
        self.status = "running"
        return decision

    async def pause_for_captcha(self, job: dict[str, Any], details: str = "CAPTCHA detected") -> None:
        """
        Pauses the workflow and alerts the user when a CAPTCHA or bot check is encountered.
        """
        self.status = "paused_captcha"
        self.current_job = job
        pause_data = {
            "type": "captcha",
            "job_id": job["id"],
            "job_title": job.get("title"),
            "company": job.get("company"),
            "details": details,
        }

        if self.session_id:
            self.db.update_auto_apply_session(
                self.session_id,
                status="paused_captcha",
                current_job_id=job["id"],
                pause_data=json.dumps(pause_data),
            )

        await self.log("paused_captcha", f"Action required: Solve CAPTCHA in browser for {job.get('title')}", job["id"], pause_data)
        send_desktop_notification("CAPTCHA Detected!", f"Please solve CAPTCHA in the open Chrome window for {job.get('company')}")

        self.pause_event.clear()
        await self.pause_event.wait()

        decision = self.user_decision or {"action": "solved_captcha"}
        self.user_decision = None
        self.status = "running"
        return decision

    def resume_from_user(self, action: str, approved_skills: Optional[list[str]] = None):
        """Called by the API when user approves skills or confirms CAPTCHA solved."""
        self.user_decision = {
            "action": action, # approve | skip | solved_captcha
            "skills": approved_skills,
        }
        self.pause_event.set()

    def request_stop(self):
        """Signal engine to stop."""
        self.stop_requested = True
        self.pause_event.set()

    async def _setup_browser(self):
        """Launch headed Chromium with user-specified or isolated profile."""
        from playwright.async_api import async_playwright

        p = await async_playwright().start()

        settings = self.profile.get("settings", {})
        user_data_dir = settings.get("chrome_user_data_dir", "").strip()

        # If user did not provide a Chrome path, use default Windows Chrome User Data if exists
        if not user_data_dir and platform.system() == "Windows":
            default_chrome = Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data"
            if default_chrome.exists():
                user_data_dir = str(default_chrome)

        # Fallback to local profile directory if locked or not specified
        local_dir = _REPO_ROOT / ".browser_profile"
        local_dir.mkdir(exist_ok=True)

        context = None
        browser = None

        args = [
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--no-default-browser-check",
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ]

        if user_data_dir and os.path.exists(user_data_dir):
            try:
                # Try launching with Chrome profile
                context = await p.chromium.launch_persistent_context(
                    user_data_dir=user_data_dir,
                    headless=settings.get("browser_headless", False),
                    channel="chrome",
                    args=args,
                    viewport={"width": 1280, "height": 800},
                )
            except Exception as e:
                print(f"[auto_apply] Could not launch Chrome user data dir (may be open): {e}. Using isolated profile.")

        if not context:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=str(local_dir),
                headless=settings.get("browser_headless", False),
                args=args,
                viewport={"width": 1280, "height": 800},
            )

        return p, context

    async def apply_to_job(self, page, job: dict[str, Any]) -> str:
        """
        Execute full auto-apply pipeline for a single job.
        Returns: 'applied' | 'skipped' | 'failed'
        """
        job_id = job["id"]
        job_title = job.get("title") or "Software Engineer"
        company = job.get("company") or "Company"
        target_url = job.get("apply_url") or job.get("source_url") or ""

        if not target_url:
            await self.log("error", "No URL available for job", job_id)
            return "failed"

        # 1. Skill Matching
        match_data = self.resume_builder.match_job(job_title, job.get("description") or "")
        await self.log("info", f"Job match score: {match_data['match_score']}% for {job_title}", job_id)

        # 2. Pause for Skill Review (One-by-one user approval)
        decision = await self.pause_for_skill_review(job, match_data)
        if decision.get("action") == "skip":
            await self.log("skipped", f"User opted to skip job: {job_title}", job_id)
            self.db.update_job_apply_status(job_id, "skipped", notes="Skipped during skill review")
            return "skipped"

        approved_skills = decision.get("skills") or match_data["matched_skills"]
        if not approved_skills:
            approved_skills = match_data["all_user_skills"][:6]

        # 3. Generate Tailored Documents
        await self.log("info", "Generating tailored ATS resume and cover letter...", job_id)
        docs = await self.resume_builder.generate_documents(
            job_id=job_id,
            job_title=job_title,
            company=company,
            active_skills=approved_skills,
        )
        pdf_path = docs.get("pdf_path")
        cover_letter = docs.get("cover_letter")

        # 4. Navigate to Job URL
        await self.log("info", f"Navigating to {target_url}", job_id)
        try:
            await page.goto(target_url, timeout=45000, wait_until="domcontentloaded")
            await asyncio.sleep(2)
        except Exception as e:
            await self.log("error", f"Failed to load job page: {e}", job_id)
            return "failed"

        # 5. Determine platform & apply
        url_lower = page.url.lower()

        if "linkedin.com" in url_lower:
            return await self._handle_linkedin(page, job, pdf_path, cover_letter)
        elif "indeed.com" in url_lower:
            return await self._handle_indeed(page, job, pdf_path, cover_letter)
        else:
            return await self._handle_generic_ats(page, job, pdf_path, cover_letter)

    async def _handle_linkedin(self, page, job: dict[str, Any], pdf_path: str, cover_letter: str) -> str:
        """Handle LinkedIn Easy Apply flow."""
        job_id = job["id"]
        await self.log("info", "Scanning for LinkedIn Easy Apply...", job_id)

        # Check for CAPTCHA
        if await self._check_captcha(page):
            await self.pause_for_captcha(job, "LinkedIn Security Verification detected")

        # Find Easy Apply button
        easy_apply_btn = page.locator("button.jobs-apply-button:has-text('Easy Apply'), button:has-text('Easy Apply')").first
        has_easy_apply = await easy_apply_btn.is_visible(timeout=5000)

        if not has_easy_apply:
            await self.log("info", "No 'Easy Apply' button found on LinkedIn. Job requires external application.", job_id)
            self.db.update_job_apply_status(job_id, "skipped", notes="External apply only")
            return "skipped"

        await easy_apply_btn.click()
        await asyncio.sleep(2)

        # Step through Easy Apply modal steps
        modal = page.locator("div.jobs-easy-apply-modal, div[data-easy-apply-modal]").first
        if not await modal.is_visible(timeout=5000):
            await self.log("error", "Easy Apply modal failed to open", job_id)
            return "failed"

        step_count = 0
        max_steps = 8

        while step_count < max_steps:
            step_count += 1
            await asyncio.sleep(1)

            if await self._check_captcha(page):
                await self.pause_for_captcha(job, "LinkedIn CAPTCHA in application dialog")

            # Fill phone if empty
            phone_input = modal.locator("input[id*='phoneNumber'], input[id*='phone']").first
            if await phone_input.is_visible() and not (await phone_input.input_value()):
                phone_val = self.profile.get("personal", {}).get("phone", "")
                await phone_input.fill(phone_val)

            # Upload resume if file input is visible
            file_input = modal.locator("input[type='file']").first
            if await file_input.is_visible() and pdf_path and os.path.exists(pdf_path):
                try:
                    await file_input.set_input_files(pdf_path)
                    await self.log("info", "Attached tailored PDF resume", job_id)
                    await asyncio.sleep(1)
                except Exception as e:
                    print(f"[upload error] {e}")

            # Answer any visible questions
            await self._answer_visible_form_fields(modal, job)

            # Check for Submit button
            submit_btn = modal.locator("button:has-text('Submit application'), button[aria-label='Submit application']").first
            if await submit_btn.is_visible():
                await self.log("info", "Submitting application...", job_id)
                await submit_btn.click()
                await asyncio.sleep(3)
                self.db.update_job_apply_status(job_id, "applied", notes="Applied via LinkedIn Easy Apply")
                await self.log("applied", f"Successfully applied to {job.get('company')}!", job_id)
                return "applied"

            # Check for Next / Review button
            next_btn = modal.locator("button:has-text('Next'), button:has-text('Review')").first
            if await next_btn.is_visible():
                await next_btn.click()
                await asyncio.sleep(1.5)
            else:
                # No next button found; could be an unhandled required field
                break

        # If we exited loop without submit, pause for human assistance
        decision = await self.pause_for_captcha(job, "Unfilled custom question detected in LinkedIn modal")
        if decision.get("action") == "skip":
            self.db.update_job_apply_status(job_id, "skipped", notes="Skipped during modal review")
            return "skipped"
        self.db.update_job_apply_status(job_id, "applied", notes="Applied via LinkedIn Easy Apply with manual review")
        return "applied"

    async def _handle_indeed(self, page, job: dict[str, Any], pdf_path: str, cover_letter: str) -> str:
        """Handle Indeed Apply flow (native Indeed Apply or external redirect)."""
        job_id = job["id"]
        personal = self.profile.get("personal", {})
        await self.log("info", "Scanning Indeed job posting for application options...", job_id)

        # 1. Check for CAPTCHA on initial page
        if await self._check_captcha(page):
            await self.pause_for_captcha(job, "Indeed Security Verification detected")

        # 2. Check for Indeed Apply or Apply on Company Site
        indeed_apply_selectors = [
            "button#indeedApplyButton",
            "button:has-text('Apply now')",
            "a:has-text('Apply now')",
            "button:has-text('Easily apply')",
            "a:has-text('Easily apply')",
            "div.indeed-apply-widget button",
        ]
        external_apply_selectors = [
            "button:has-text('Apply on company site')",
            "a:has-text('Apply on company site')",
            "button:has-text('Apply on employer site')",
            "a:has-text('Apply on employer site')",
        ]

        apply_btn = None
        is_external = False

        for sel in indeed_apply_selectors:
            try:
                elem = page.locator(sel).first
                if await elem.is_visible(timeout=1500):
                    apply_btn = elem
                    break
            except Exception:
                pass

        if not apply_btn:
            for sel in external_apply_selectors:
                try:
                    elem = page.locator(sel).first
                    if await elem.is_visible(timeout=1500):
                        apply_btn = elem
                        is_external = True
                        break
                except Exception:
                    pass

        if not apply_btn:
            await self.log("info", "No apply button detected on Indeed page.", job_id)
            self.db.update_job_apply_status(job_id, "skipped", notes="No apply button found on Indeed")
            return "skipped"

        # 3. Click button (handling possible popup window / new tab)
        target_page = page
        try:
            async with page.context.expect_page(timeout=3500) as popup_info:
                await apply_btn.click()
            target_page = await popup_info.value
            await target_page.wait_for_load_state("domcontentloaded", timeout=10000)
        except Exception:
            # No new popup tab opened; stays on current page or modal opened
            await asyncio.sleep(2)

        # If it navigated to an external company site or ATS, delegate to generic ATS handler
        if is_external or ("indeed.com" not in target_page.url.lower() and not target_page.url.startswith("about:")):
            await self.log("info", f"Redirected to external ATS ({target_page.url[:45]}...). Delegating to ATS handler.", job_id)
            return await self._handle_generic_ats(target_page, job, pdf_path, cover_letter)

        # 4. Multi-step form completion (Indeed Apply dialog / page)
        await self.log("info", "Stepping through Indeed Apply form...", job_id)
        max_steps = 10
        step_count = 0

        while step_count < max_steps:
            step_count += 1
            await asyncio.sleep(1.5)

            # Check CAPTCHA on current step
            if await self._check_captcha(target_page):
                await self.pause_for_captcha(job, "Indeed CAPTCHA / Bot verification in application form")

            # Look for Indeed container / body
            container = target_page.locator("#ia-container, div[class*='ia-'], main, body").first

            # Fill Contact Information if visible
            name_inp = container.locator("input[id*='name'], input[name*='name'], input[id*='applicant.name']").first
            if await name_inp.is_visible() and not (await name_inp.input_value()):
                await name_inp.fill(personal.get("name", ""))

            first_name_inp = container.locator("input[id*='firstName'], input[name*='firstName']").first
            if await first_name_inp.is_visible() and not (await first_name_inp.input_value()):
                full_name = personal.get("name", "")
                parts = full_name.split(" ", 1)
                await first_name_inp.fill(parts[0])

            last_name_inp = container.locator("input[id*='lastName'], input[name*='lastName']").first
            if await last_name_inp.is_visible() and not (await last_name_inp.input_value()):
                full_name = personal.get("name", "")
                parts = full_name.split(" ", 1)
                await last_name_inp.fill(parts[1] if len(parts) > 1 else parts[0])

            email_inp = container.locator("input[type='email'], input[id*='email'], input[name*='email'], input[id*='applicant.email']").first
            if await email_inp.is_visible() and not (await email_inp.input_value()):
                await email_inp.fill(personal.get("email", ""))

            phone_inp = container.locator("input[type='tel'], input[id*='phone'], input[name*='phone'], input[id*='applicant.phoneNumber']").first
            if await phone_inp.is_visible() and not (await phone_inp.input_value()):
                await phone_inp.fill(personal.get("phone", ""))

            loc_inp = container.locator("input[id*='location'], input[name*='location'], input[id*='city'], input[name*='city']").first
            if await loc_inp.is_visible() and not (await loc_inp.input_value()):
                await loc_inp.fill(personal.get("location", ""))

            # Upload resume if file input is visible
            file_inp = container.locator("input[type='file']").first
            if await file_inp.is_visible() and pdf_path and os.path.exists(pdf_path):
                try:
                    await file_inp.set_input_files(pdf_path)
                    await self.log("info", "Attached tailored PDF resume to Indeed application", job_id)
                    await asyncio.sleep(1)
                except Exception as e:
                    print(f"[indeed upload error] {e}")

            # Answer any visible questions or selects
            await self._answer_visible_form_fields(container, job)

            # Check for Submit button
            submit_btn = container.locator(
                "button:has-text('Submit your application'), "
                "button:has-text('Submit application'), "
                "button:has-text('Submit'), "
                "button[aria-label*='Submit']"
            ).first
            if await submit_btn.is_visible():
                await self.log("info", "Submitting Indeed application...", job_id)
                await submit_btn.click()
                await asyncio.sleep(3)
                self.db.update_job_apply_status(job_id, "applied", notes="Applied via Indeed Apply")
                await self.log("applied", f"Successfully applied to {job.get('company')} on Indeed!", job_id)
                return "applied"

            # Check for Continue / Next / Review button
            continue_btn = container.locator(
                "button:has-text('Continue'), "
                "button:has-text('Next'), "
                "button:has-text('Review your application'), "
                "button:has-text('Review')"
            ).first

            if await continue_btn.is_visible():
                await continue_btn.click()
                await asyncio.sleep(1.5)
            else:
                # No forward button visible — reached an unrecognized step or finished
                break

        # If loop exited without submit, pause for human assistance
        decision = await self.pause_for_captcha(job, "Review and complete Indeed application in browser")
        if decision.get("action") == "skip":
            self.db.update_job_apply_status(job_id, "skipped", notes="Skipped during Indeed application review")
            return "skipped"

        self.db.update_job_apply_status(job_id, "applied", notes="Applied via Indeed Apply with user review")
        return "applied"

    async def _handle_generic_ats(self, page, job: dict[str, Any], pdf_path: str, cover_letter: str) -> str:
        """Handle standard ATS forms (Greenhouse, Lever, etc.)."""
        job_id = job["id"]
        personal = self.profile.get("personal", {})

        await self.log("info", "Detecting standard ATS input fields...", job_id)

        # Standard field autocompletion
        name_input = page.locator("input[name*='name'], input[id*='name']").first
        if await name_input.is_visible():
            await name_input.fill(personal.get("name", ""))

        email_input = page.locator("input[type='email'], input[name*='email']").first
        if await email_input.is_visible():
            await email_input.fill(personal.get("email", ""))

        phone_input = page.locator("input[type='tel'], input[name*='phone']").first
        if await phone_input.is_visible():
            await phone_input.fill(personal.get("phone", ""))

        # File upload
        file_input = page.locator("input[type='file']").first
        if await file_input.is_visible() and pdf_path and os.path.exists(pdf_path):
            await file_input.set_input_files(pdf_path)

        # Answer any visible questions
        await self._answer_visible_form_fields(page, job)

        # Ask user for final submission review on external forms
        decision = await self.pause_for_captcha(job, "Form auto-filled. Please review and click Submit in the browser.")
        if decision.get("action") == "skip":
            self.db.update_job_apply_status(job_id, "skipped", notes="Skipped during ATS review")
            return "skipped"
        self.db.update_job_apply_status(job_id, "applied", notes="Applied on company ATS")
        return "applied"

    async def _check_captcha(self, page) -> bool:
        """Detect CAPTCHAs or Cloudflare/Bot walls."""
        selectors = [
            "iframe[src*='captcha']",
            "iframe[src*='recaptcha']",
            "div.g-recaptcha",
            "#cf-turnstile",
            "div.cf-turnstile",
            "text='Verify you are human'",
            "text='Security Verification'",
        ]
        for sel in selectors:
            try:
                elem = page.locator(sel).first
                if await elem.is_visible(timeout=1000):
                    return True
            except Exception:
                pass
        return False

    async def _answer_visible_form_fields(self, container, job: dict[str, Any]):
        """Detect radio buttons, selects, and text inputs and provide LLM/heuristic answers."""
        try:
            # Handle text inputs
            inputs = await container.locator("input[type='text'], input[type='number'], textarea").all()
            for inp in inputs:
                if await inp.is_visible() and not (await inp.input_value()):
                    label = (await inp.get_attribute("aria-label")) or (await inp.get_attribute("placeholder")) or ""
                    if not label:
                        try:
                            label = await inp.evaluate("el => el.labels && el.labels[0] ? el.labels[0].innerText : (el.name || el.id || '')")
                        except Exception:
                            label = (await inp.get_attribute("name")) or ""
                    if label:
                        ans = await self.llm.answer_question(label, field_type="text", job_context=job)
                        await inp.fill(ans)

            # Handle selects
            selects = await container.locator("select").all()
            for sel in selects:
                if await sel.is_visible():
                    try:
                        options = await sel.locator("option").all()
                        if len(options) > 1:
                            val_to_select = None
                            for opt in options:
                                txt = (await opt.inner_text()).strip().lower()
                                val = await opt.get_attribute("value")
                                if "yes" in txt or "authorized" in txt:
                                    val_to_select = val
                                    break
                            if val_to_select is not None:
                                await sel.select_option(value=val_to_select)
                            else:
                                second_val = await options[1].get_attribute("value")
                                if second_val:
                                    await sel.select_option(value=second_val)
                    except Exception as se:
                        print(f"[select option warning] {se}")

            # Handle radio buttons
            radios = await container.locator("input[type='radio']").all()
            if radios:
                for r in radios:
                    r_label = await r.get_attribute("aria-label") or ""
                    if not r_label:
                        try:
                            r_label = await r.evaluate("el => el.labels && el.labels[0] ? el.labels[0].innerText : (el.parentElement ? el.parentElement.innerText : '')")
                        except Exception:
                            pass
                    if "yes" in r_label.lower():
                        await r.check()
                        break
        except Exception as e:
            print(f"[field filling warning] {e}")

    async def run_session(self, job_ids: list[int] | None = None, max_apps: int = 15) -> int:
        """
        Run an auto-apply session across a list of target jobs.
        Includes rate-limiting delay between jobs and daily cap checks.
        """
        # Daily limit check
        applied_today = self.db.count_applications_today()
        daily_cap = self.profile.get("settings", {}).get("max_daily_applications", 15)
        if applied_today >= daily_cap:
            await self.log("error", f"Daily cap reached ({applied_today}/{daily_cap}). Halting to protect accounts.")
            return 0

        # Fetch candidate jobs
        if not job_ids:
            # Select unapplied jobs from DB
            candidate_rows = self.db.get_extracted_jobs(active_only=True, limit=50)
            jobs = [j for j in candidate_rows if j.get("apply_status", "unapplied") == "unapplied"][:max_apps]
        else:
            jobs = [self.db.get_extracted_job_by_id(jid) for jid in job_ids]
            jobs = [j for j in jobs if j]

        if not jobs:
            await self.log("info", "No unapplied jobs found to apply.")
            return 0

        self.session_id = self.db.create_auto_apply_session(total_jobs=len(jobs))
        self.status = "running"
        self.stop_requested = False

        await self.log("info", f"Starting Auto-Apply session #{self.session_id} for {len(jobs)} jobs")

        playwright_obj = None
        context = None

        applied_count = 0
        failed_count = 0
        skipped_count = 0

        try:
            playwright_obj, context = await self._setup_browser()
            page = await context.new_page()

            for idx, job in enumerate(jobs):
                if self.stop_requested:
                    await self.log("info", "Session stop requested by user.")
                    break

                if applied_today + applied_count >= daily_cap:
                    await self.log("info", f"Reached daily application limit ({daily_cap}). Ending session.")
                    break

                self.db.update_auto_apply_session(
                    self.session_id,
                    current_job_id=job["id"],
                    applied_jobs=applied_count,
                    failed_jobs=failed_count,
                    skipped_jobs=skipped_count,
                )

                result = await self.apply_to_job(page, job)
                if result == "applied":
                    applied_count += 1
                elif result == "skipped":
                    skipped_count += 1
                else:
                    failed_count += 1

                # Conservative rate limiting delay between jobs
                if idx < len(jobs) - 1 and not self.stop_requested:
                    min_delay = self.profile.get("settings", {}).get("min_delay_seconds", 60)
                    max_delay = self.profile.get("settings", {}).get("max_delay_seconds", 120)
                    delay = random.uniform(min_delay, max_delay)
                    await self.log("info", f"Safety delay: waiting {int(delay)}s before next job...")
                    await asyncio.sleep(delay)

        finally:
            self.status = "completed"
            if self.session_id:
                self.db.update_auto_apply_session(
                    self.session_id,
                    status="completed" if not self.stop_requested else "stopped",
                    applied_jobs=applied_count,
                    failed_jobs=failed_count,
                    skipped_jobs=skipped_count,
                    is_finished=True,
                )
            if context:
                try:
                    await context.close()
                except Exception:
                    pass
            if playwright_obj:
                try:
                    await playwright_obj.stop()
                except Exception:
                    pass

        await self.log("info", f"Session completed. Applied: {applied_count}, Skipped: {skipped_count}, Failed: {failed_count}")
        return applied_count
